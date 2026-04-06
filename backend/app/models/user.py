import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Encryption salts and per-user secrets.
    #
    # encryption_salt: random 32-byte hex value, unique per user.  Used as the
    #     KDF salt in both argon2id (Option A) and PBKDF2 (Option B) key
    #     derivation.  Safe to store in the DB — it is not secret.
    #
    # per_user_secret: random 32-byte hex value, unique per user.  Used ONLY
    #     in Option B (server deployments) as the KDF input material.  This
    #     means each user's key is independent; a server compromise reveals
    #     only the rows that were already readable, not a master key.  It is
    #     NOT a global server secret — never use the same value for two users.
    encryption_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    per_user_secret: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    memories: Mapped[list["Memory"]] = relationship(  # noqa: F821
        "Memory", back_populates="user", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(  # noqa: F821
        "Source", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
