"""add analytics_log table

Revision ID: 0002_add_analytics_log
Revises: 0001_initial
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_add_analytics_log"
down_revision = None  # Set to previous migration ID if one exists
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_logs",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False, server_default="unknown"),
        sa.Column("original_tokens", sa.Integer(), nullable=False, server_default="15000"),
        sa.Column("augmented_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_saved_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("retrieval_hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compression_ratio", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_analytics_logs_user_created", "analytics_logs", ["user_id", "created_at"])
    op.create_index("ix_analytics_logs_user_platform", "analytics_logs", ["user_id", "platform"])


def downgrade() -> None:
    op.drop_index("ix_analytics_logs_user_platform")
    op.drop_index("ix_analytics_logs_user_created")
    op.drop_table("analytics_logs")
