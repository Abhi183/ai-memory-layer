import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.memory import MemoryType
from app.schemas.memory import (
    MemoryCreate, MemoryRead, MemoryUpdate,
    MemorySearchRequest, MemorySearchResult,
    ContextRequest, ContextResponse,
    MemoryCaptureRequest,
)
from app.services.memory_service import memory_service
from app.services.retrieval_service import retrieval_service

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
    """
    return await retrieval_service.get_context(db, user, data)


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
