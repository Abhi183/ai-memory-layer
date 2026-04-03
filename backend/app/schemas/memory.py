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


class ContextResponse(BaseModel):
    original_prompt: str
    augmented_prompt: str
    injected_memories: list[MemorySearchResult]
    context_tokens_used: int
