"""add queue cycles, substitutions, and ETF2L screening

Revision ID: 20260726_0004
Revises: 20260717_0003
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260726_0004"
down_revision = "20260717_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    preference_columns = {column["name"] for column in inspector.get_columns("queue_preferences")}
    if "is_flex" not in preference_columns:
        op.add_column(
            "queue_preferences",
            sa.Column("is_flex", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute(
            """
            UPDATE queue_preferences AS preference
            SET is_flex = true
            WHERE preference.id <> (
                SELECT MIN(first_preference.id)
                FROM queue_preferences AS first_preference
                WHERE first_preference.queue_entry_id = preference.queue_entry_id
            )
            """
        )

    entry_columns = {column["name"] for column in inspector.get_columns("queue_entries")}
    if "pre_ready_expires_at" not in entry_columns:
        op.add_column(
            "queue_entries",
            sa.Column("pre_ready_expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "queue_cycles" not in tables:
        op.create_table(
            "queue_cycles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("queue_bucket", sa.String(length=16), nullable=False, unique=True),
            sa.Column("ready_check_token", sa.String(length=36), nullable=True),
            sa.Column("ready_check_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("map_candidates", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "queue_map_votes" not in tables:
        op.create_table(
            "queue_map_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("queue_cycle_id", sa.Integer(), sa.ForeignKey("queue_cycles.id"), nullable=False),
            sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("map_name", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("queue_cycle_id", "player_id", name="uq_queue_map_vote_player"),
        )
    if "match_substitutions" not in tables:
        op.create_table(
            "match_substitutions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("outgoing_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("incoming_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("created_by_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("team", sa.String(length=3), nullable=False),
            sa.Column("assigned_class", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    player_columns = {column["name"] for column in inspector.get_columns("players")}
    for name, column in [
        ("etf2l_player_id", sa.Column("etf2l_player_id", sa.Integer(), nullable=True)),
        ("etf2l_profile_url", sa.Column("etf2l_profile_url", sa.String(length=255), nullable=True)),
        ("etf2l_recent_division", sa.Column("etf2l_recent_division", sa.String(length=100), nullable=True)),
        ("etf2l_highest_division", sa.Column("etf2l_highest_division", sa.String(length=100), nullable=True)),
        ("etf2l_skill_band", sa.Column("etf2l_skill_band", sa.String(length=32), nullable=True)),
        ("etf2l_decision", sa.Column("etf2l_decision", sa.String(length=32), nullable=True)),
        ("etf2l_checked_at", sa.Column("etf2l_checked_at", sa.DateTime(timezone=True), nullable=True)),
        (
            "etf2l_reviewed_by_player_id",
            sa.Column(
                "etf2l_reviewed_by_player_id",
                sa.Integer(),
                sa.ForeignKey("players.id"),
                nullable=True,
            ),
        ),
        ("etf2l_reviewed_at", sa.Column("etf2l_reviewed_at", sa.DateTime(timezone=True), nullable=True)),
        ("etf2l_evidence", sa.Column("etf2l_evidence", sa.JSON(), nullable=False, server_default="{}")),
    ]:
        if name not in player_columns:
            op.add_column("players", column)


def downgrade() -> None:
    for name in [
        "etf2l_evidence",
        "etf2l_reviewed_at",
        "etf2l_reviewed_by_player_id",
        "etf2l_checked_at",
        "etf2l_decision",
        "etf2l_skill_band",
        "etf2l_highest_division",
        "etf2l_recent_division",
        "etf2l_profile_url",
        "etf2l_player_id",
    ]:
        op.drop_column("players", name)
    op.drop_table("match_substitutions")
    op.drop_table("queue_map_votes")
    op.drop_table("queue_cycles")
    op.drop_column("queue_entries", "pre_ready_expires_at")
    op.drop_column("queue_preferences", "is_flex")
