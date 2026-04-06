import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Float, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AnalyticsLog(Base):
    """Records token and cost savings for each context retrieval request."""
    __tablename__ = "analytics_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, nullable=False
    )

    # Provider info
    platform: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)

    # Token economics
    original_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    augmented_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_saved: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_saved_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Ingestion cost — LLM API expense incurred when processing this memory
    ingestion_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ingestion_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingestion_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Retrieval stats
    retrieval_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compression_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )

    __table_args__ = (
        Index("ix_analytics_logs_user_created", "user_id", "created_at"),
        Index("ix_analytics_logs_user_platform", "user_id", "platform"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnalyticsLog {self.id} platform={self.platform} "
            f"tokens_saved={self.tokens_saved} cost_saved={self.cost_saved_usd:.4f}>"
        )
