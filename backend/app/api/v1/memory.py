import asyncio
import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.memory import MemoryType
from app.schemas.memory import (
    MemoryCreate, MemoryRead, MemoryUpdate,
    MemorySearchRequest, MemorySearchResult,
    ContextRequest, ContextResponse, ContextExplainResponse,
    MemoryCaptureRequest,
)
from app.services.memory_service import memory_service
from app.services.retrieval_service import retrieval_service
from app.services.analytics_service import analytics_service

log = structlog.get_logger()

# Conservative estimate of a full conversation context (tokens).
# Memory-augmented requests only need context_tokens_used; the rest is saved.
_DEFAULT_FULL_CONTEXT_TOKENS = 15_000

router = APIRouter(prefix="/memory", tags=["memory"])


# ── Capture (from browser extension / CLI) ─────────────────────────────────────
@router.post("/capture", response_model=MemoryRead, status_code=status.HTTP_202_ACCEPTED)
async def capture_memory(
    data: MemoryCaptureRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Capture a raw prompt+response interaction.
    The memory is saved immediately; processing (embedding, summarization) happens async.
    """
    return await memory_service.capture(db, user, data)


# ── CRUD ───────────────────────────────────────────────────────────────────────
@router.post("/", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    data: MemoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await memory_service.create(db, user, data)


@router.get("/", response_model=list[MemoryRead])
async def list_memories(
    memory_type: Optional[MemoryType] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await memory_service.list_memories(db, user.id, memory_type, platform, limit, offset)


@router.get("/search", response_model=list[MemorySearchResult])
async def search_memories(
    q: str = Query(description="Search query"),
    limit: int = Query(default=10, ge=1, le=50),
    threshold: float = Query(default=0.65, ge=0.0, le=1.0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Semantic similarity search over user memories."""
    request = MemorySearchRequest(query=q, limit=limit, similarity_threshold=threshold)
    return await retrieval_service.search(db, user.id, request)


@router.post("/context", response_model=ContextResponse)
async def get_context(
    data: ContextRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Given a prompt, return an augmented version with relevant memory context injected.
    Used by browser extensions and integrations before sending to an AI system.

    Supports MSA-inspired features via request body fields:
      - `use_adaptive_k`   (default True)  — dynamically selects k based on score gaps.
      - `use_multi_hop`    (default False) — two-pass retrieval for bridging memories.
      - `multi_hop_depth`  (default 2)     — number of hops when use_multi_hop is True.

    Also fires a background analytics log so the caller can track token / cost savings.
    """
    start_ms = time.monotonic_ns() // 1_000_000  # milliseconds

    context_response = await retrieval_service.get_context(db, user, data)

    latency_ms = (time.monotonic_ns() // 1_000_000) - start_ms

    # Token economics
    # original_tokens: conservative estimate of what a full conversation history costs.
    # augmented_tokens: only the injected memory context block.
    original_tokens = _DEFAULT_FULL_CONTEXT_TOKENS
    augmented_tokens = context_response.context_tokens_used

    platform = (data.platform or "unknown").lower()
    model = "default"  # ContextRequest does not expose the model; use default pricing

    hit_count = len(context_response.injected_memories)

    # Fire-and-forget — do not block the response on the DB write.
    asyncio.create_task(
        analytics_service.log_request(
            db=db,
            user_id=user.id,
            platform=platform,
            model=model,
            original_tokens=original_tokens,
            augmented_tokens=augmented_tokens,
            hit_count=hit_count,
            latency_ms=latency_ms,
        )
    )

    log.debug(
        "memory.context.served",
        user_id=str(user.id),
        platform=platform,
        hit_count=hit_count,
        latency_ms=latency_ms,
        tokens_used=augmented_tokens,
        adaptive_k=data.use_adaptive_k,
        multi_hop=data.use_multi_hop,
    )

    return context_response


@router.post("/context/explain", response_model=ContextExplainResponse)
async def explain_context(
    data: ContextRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug view of what the /context endpoint would inject and why.

    Returns a detailed breakdown for each candidate memory:
      - Cosine similarity, recency score, importance score, composite score
      - Which retrieval hop (1 = direct match, 2 = bridging) surfaced the memory
      - Whether adaptive-k was triggered and the k it chose
      - Total T_aug tokens that would be injected
      - The full augmented prompt that would have been returned

    Useful for tuning importance scores, understanding retrieval behaviour, or
    debugging why a specific memory was or wasn't included.
    """
    explain_response = await retrieval_service.get_context_explain(db, user, data)

    log.debug(
        "memory.context.explain",
        user_id=str(user.id),
        candidates=len(explain_response.candidate_scores),
        injected=len(explain_response.injected_memories),
        adaptive_k_chosen=explain_response.adaptive_k_chosen,
        hops=explain_response.hops_executed,
        tokens_used=explain_response.context_tokens_used,
    )

    return explain_response


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await memory_service.get(db, memory_id, user.id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: uuid.UUID,
    data: MemoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await memory_service.update(db, memory_id, user, data)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await memory_service.delete(db, memory_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
