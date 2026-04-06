import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, DateTime, ForeignKey, Table, Column,
    Float, Integer, Enum as SAEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import settings
import enum


class MemoryType(str, enum.Enum):
    SHORT_TERM = "short_term"   # Recent interactions, TTL-based
    LONG_TERM = "long_term"     # Persistent facts about the user
    SEMANTIC = "semantic"       # Conceptual knowledge, always embedded


class MemoryStatus(str, enum.Enum):
    PENDING = "pending"         # Captured, awaiting processing
    PROCESSING = "processing"   # In the pipeline
    ACTIVE = "active"           # Processed and searchable
    ARCHIVED = "archived"       # Too old or manually archived
    INACTIVE = "inactive"       # Superseded by a newer contradicting fact
    FAILED = "failed"           # Pipeline failure


# Many-to-many: memories <-> tags
memory_tags = Table(
    "memory_tags",
    Base.metadata,
    Column("memory_id", UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE")),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")),
)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    # Core content — stored AES-256 encrypted at rest
    content: Mapped[str] = mapped_column(Text, nullable=False)          # Encrypted raw content
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Encrypted summary
    extracted_facts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Key facts as JSON

    # Classification
    memory_type: Mapped[MemoryType] = mapped_column(
        SAEnum(MemoryType), default=MemoryType.SHORT_TERM, index=True
    )
    status: Mapped[MemoryStatus] = mapped_column(
        SAEnum(MemoryStatus), default=MemoryStatus.PENDING, index=True
    )
    source_platform: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # Metadata
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1, used for ranking
    access_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )  # None = no expiry

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memories")  # noqa: F821
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="memories")  # noqa: F821
    tags: Mapped[list["Tag"]] = relationship("Tag", secondary=memory_tags, back_populates="memories")  # noqa: F821
    embedding: Mapped[Optional["MemoryEmbedding"]] = relationship(
        "MemoryEmbedding", back_populates="memory", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index("ix_memories_user_type", "user_id", "memory_type"),
        Index("ix_memories_user_status", "user_id", "status"),
        Index("ix_memories_user_captured", "user_id", "captured_at"),
    )

    def __repr__(self) -> str:
        return f"<Memory {self.id} type={self.memory_type} status={self.status}>"


class MemoryEmbedding(Base):
    """Stores vector embeddings separately for efficient pgvector operations."""
    __tablename__ = "memory_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # The actual embedding vector — dimension matches config
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationship
    memory: Mapped["Memory"] = relationship("Memory", back_populates="embedding")

    __table_args__ = (
        # IVFFlat index for approximate nearest neighbor search
        # Tune lists= based on dataset size: sqrt(num_rows) is a good starting point
        Index(
            "ix_memory_embeddings_vector",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Source(Base):
    """Tracks which AI platform a memory originated from."""
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(100), nullable=False)  # chatgpt, claude, cursor, etc.
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sources")  # noqa: F821
    memories: Mapped[list["Memory"]] = relationship("Memory", back_populates="source")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # hex color

    # Relationships
    memories: Mapped[list["Memory"]] = relationship(
        "Memory", secondary=memory_tags, back_populates="tags"
    )
