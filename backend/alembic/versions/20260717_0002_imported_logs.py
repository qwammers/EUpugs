"""add historical imported logs

Revision ID: 20260717_0002
Revises: 20260713_0001
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260717_0002"
down_revision = "20260713_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imported_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("log_url", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("map_name", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("imported_logs")
