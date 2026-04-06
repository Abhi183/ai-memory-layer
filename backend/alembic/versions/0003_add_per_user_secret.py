"""add per_user_secret to users table

Revision ID: 0003_add_per_user_secret
Revises: 0002_add_analytics_log
Create Date: 2026-04-06

Why this column exists
----------------------
Option B of the new security model derives each user's AES-256-GCM key from
a *per-user* random secret rather than a global server env-var.  This means
even a full database dump does not yield a single master key that decrypts
all users' memories.  Existing rows receive a freshly generated random value
on upgrade; they will need to be re-encrypted with the new key if the server
deployment wishes to drop the legacy global SECRET_KEY path.  See
app/services/encryption_service.py for the full security model description.
"""

import os
import secrets

from alembic import op
import sqlalchemy as sa


revision = "0003_add_per_user_secret"
down_revision = "0002_add_analytics_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the column as nullable first so existing rows are not rejected.
    op.add_column(
        "users",
        sa.Column("per_user_secret", sa.String(64), nullable=True),
    )

    # Back-fill existing rows with a unique random secret each.
    # We use a raw SQL UPDATE so each row gets its own value via gen_random_bytes.
    op.execute(
        "UPDATE users SET per_user_secret = encode(gen_random_bytes(32), 'hex') "
        "WHERE per_user_secret IS NULL"
    )

    # Now tighten to NOT NULL.
    op.alter_column("users", "per_user_secret", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "per_user_secret")
