import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Internal create schema ─────────────────────────────────────────────────────

class AnalyticsLogCreate(BaseModel):
    """Used internally when writing a new analytics record to the database."""
    user_id: uuid.UUID
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    platform: str
    model: str
    original_tokens: int = Field(ge=0)
    augmented_tokens: int = Field(ge=0)
    tokens_saved: int = Field(ge=0)
    cost_saved_usd: float = Field(ge=0.0)
    retrieval_hit_count: int = Field(ge=0, default=0)
    retrieval_latency_ms: int = Field(ge=0, default=0)
    compression_ratio: float = Field(ge=0.0, default=1.0)


# ── Public read schema ─────────────────────────────────────────────────────────

class AnalyticsLogRead(BaseModel):
    """Returned to callers when listing individual log entries."""
    id: uuid.UUID
    request_id: uuid.UUID
    platform: str
    model: str
    original_tokens: int
    augmented_tokens: int
    tokens_saved: int
    cost_saved_usd: float
    retrieval_hit_count: int
    retrieval_latency_ms: int
    compression_ratio: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Aggregate schemas ──────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    """Rolled-up economics for a user over a time window."""
    total_savings_usd: float = Field(description="Total USD saved over the window")
    total_tokens_saved: int = Field(description="Total tokens not sent to the provider")
    total_requests: int = Field(description="Number of context calls made")
    avg_compression_ratio: float = Field(
        description="Average ratio of original to augmented tokens"
    )
    avg_retrieval_latency_ms: float = Field(
        description="Average time in milliseconds for memory lookup"
    )
    days: int = Field(description="Number of days covered by this summary")
    # Full ROI fields
    total_retrieval_savings_usd: float = Field(
        default=0.0, description="Gross USD saved at retrieval time (same as total_savings_usd)"
    )
    total_ingestion_cost_usd: float = Field(
        default=0.0, description="Total LLM API cost incurred during memory ingestion"
    )
    net_savings_usd: float = Field(
        default=0.0, description="Net savings after subtracting ingestion cost"
    )
    break_even_retrievals: float = Field(
        default=0.0,
        description=(
            "Average number of retrievals needed for a memory to cover its ingestion cost. "
            "Values below 1.0 mean even a single retrieval more than pays for ingestion."
        ),
    )


class ROISummary(BaseModel):
    """Dedicated ROI breakdown returned by GET /analytics/roi."""
    total_retrieval_savings_usd: float
    total_ingestion_cost_usd: float
    net_savings_usd: float
    break_even_retrievals: float
    ingestion_model: str
    days: int


class AnalyticsTimeline(BaseModel):
    """Aggregated daily data point for the timeline chart."""
    date: date
    tokens_saved: int
    cost_saved_usd: float
    requests: int


class ProviderBreakdown(BaseModel):
    """Per-provider aggregate stats."""
    platform: str
    total_requests: int
    total_tokens_saved: int
    total_savings_usd: float
    avg_compression_ratio: float
    avg_retrieval_latency_ms: float
    most_used_model: Optional[str] = None
