import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models.memory import MemoryType, MemoryStatus


class TagRead(BaseModel):
    id: uuid.UUID
    name: str
    color: Optional[str] = None

    model_config = {"from_attributes": True}


class SourceCreate(BaseModel):
    platform: str
    source_url: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class SourceRead(BaseModel):
    id: uuid.UUID
    platform: str
    source_url: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Capture ────────────────────────────────────────────────────────────────────
class MemoryCaptureRequest(BaseModel):
    """Sent by browser extension or CLI to capture a raw interaction."""
    prompt: str = Field(description="The user's prompt/question")
    response: str = Field(description="The AI system's response")
    platform: str = Field(description="Source platform: chatgpt | claude | cursor | notion")
    source_url: Optional[str] = None
    session_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


# ── Create / Update ────────────────────────────────────────────────────────────
class MemoryCreate(BaseModel):
    content: str
    memory_type: MemoryType = MemoryType.SHORT_TERM
    source_platform: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    summary: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    tags: Optional[list[str]] = None
    importance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ── Read ───────────────────────────────────────────────────────────────────────
class MemoryRead(BaseModel):
    id: uuid.UUID
    content: str
    summary: Optional[str] = None
    extracted_facts: Optional[dict[str, Any]] = None
    memory_type: MemoryType
    status: MemoryStatus
    source_platform: Optional[str] = None
    importance_score: float
    access_count: int
    tags: list[TagRead] = []
    source: Optional[SourceRead] = None
    captured_at: datetime
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Search ─────────────────────────────────────────────────────────────────────
class MemorySearchRequest(BaseModel):
    query: str = Field(description="Natural language search query")
    limit: int = Field(default=10, ge=1, le=50)
    memory_types: Optional[list[MemoryType]] = None
    platforms: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class MemorySearchResult(BaseModel):
    memory: MemoryRead
    similarity_score: float
    relevance_rank: int


# ── Context Injection ──────────────────────────────────────────────────────────
class ContextRequest(BaseModel):
    prompt: str = Field(description="The current prompt being sent to an AI system")
    platform: Optional[str] = None
    max_tokens: int = Field(
        default=1000,
        description="Max tokens to use for injected context"
    )
    max_memories: int = Field(default=5, ge=1, le=20)
    # MSA-inspired adaptive features
    use_adaptive_k: bool = Field(
        default=True,
        description=(
            "When True, use adaptive top-k selection based on score gaps rather than "
            "a fixed k. Mirrors MSA's routing: inject only the tight relevant cluster."
        ),
    )
    use_multi_hop: bool = Field(
        default=False,
        description=(
            "When True, run a second retrieval hop using hop-1 summaries as queries "
            "to surface bridging memories (MSA Memory Interleave style)."
        ),
    )
    multi_hop_depth: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Number of retrieval hops when use_multi_hop is True.",
    )


class ContextResponse(BaseModel):
    original_prompt: str
    augmented_prompt: str
    injected_memories: list[MemorySearchResult]
    context_tokens_used: int


# ── Context Explain (debug) ────────────────────────────────────────────────────


class MemoryScoreBreakdown(BaseModel):
    """Per-memory score components for the /context/explain endpoint."""
    memory_id: uuid.UUID
    summary_snippet: str = Field(description="First 120 chars of the memory summary or content")
    cosine_score: float = Field(description="Raw cosine similarity from pgvector (0–1)")
    recency_score: float = Field(description="Exponential-decay recency component (0–1)")
    importance_score: float = Field(description="Stored importance_score field (0–1)")
    composite_score: float = Field(
        description="Weighted composite: 0.7*cosine + 0.2*recency + 0.1*importance"
    )
    hop: int = Field(
        default=1,
        description="Which retrieval hop surfaced this memory (1 = direct, 2 = bridging).",
    )


class ContextExplainResponse(BaseModel):
    """
    Debug view of what the context endpoint decided and why.
    Useful for users tuning their memory store or integration behaviour.
    """
    original_prompt: str
    # Score breakdown for every candidate memory (before k-cutoff)
    candidate_scores: list[MemoryScoreBreakdown]
    # The memories that were actually injected
    injected_memories: list[MemorySearchResult]
    # Adaptive-k diagnostics
    adaptive_k_used: bool
    adaptive_k_chosen: Optional[int] = Field(
        default=None,
        description="The k value adaptive_k() selected, or None if adaptive-k was off.",
    )
    # Multi-hop diagnostics
    multi_hop_used: bool
    hops_executed: int
    # Token accounting
    context_tokens_used: int
    augmented_prompt: str
