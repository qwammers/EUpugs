"""add outcome-first PUG rating

Revision ID: 20260729_0006
Revises: 20260727_0005
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260729_0006"
down_revision = "20260727_0005"
branch_labels = None
depends_on = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "pug_rating" not in _columns(inspector, "players"):
        op.add_column("players", sa.Column("pug_rating", sa.Integer(), nullable=True))
    op.execute("UPDATE players SET pug_rating = elo_rating WHERE pug_rating IS NULL")

    if "rating_at_lock" not in _columns(inspector, "match_slots"):
        op.add_column(
            "match_slots",
            sa.Column("rating_at_lock", sa.Integer(), nullable=False, server_default="0"),
        )
    op.execute(
        "UPDATE match_slots SET rating_at_lock = elo_at_lock "
        "WHERE rating_at_lock = 0 AND elo_at_lock IS NOT NULL"
    )

    if "pug_rating_events" not in tables:
        op.create_table(
            "pug_rating_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("team", sa.String(length=3), nullable=False),
            sa.Column("result", sa.String(length=8), nullable=False),
            sa.Column("old_rating", sa.Integer(), nullable=False),
            sa.Column("result_component", sa.Integer(), nullable=False),
            sa.Column("impact_modifier", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("new_rating", sa.Integer(), nullable=False),
            sa.Column("dominant_class", sa.String(length=16), nullable=True),
            sa.Column("damage_per_minute", sa.Float(), nullable=True),
            sa.Column("kills_per_minute", sa.Float(), nullable=True),
            sa.Column("dpm_percentile", sa.Float(), nullable=True),
            sa.Column("kpm_percentile", sa.Float(), nullable=True),
            sa.Column("benchmark_sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("team_average", sa.Integer(), nullable=False),
            sa.Column("opponent_average", sa.Integer(), nullable=False),
            sa.Column("formula_version", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("match_id", "player_id", name="uq_pug_rating_match_player"),
        )

    if "elo_rating_events" in tables:
        op.execute("""
            INSERT INTO pug_rating_events (
                match_id, player_id, team, result, old_rating, result_component,
                impact_modifier, delta, new_rating, dominant_class, damage_per_minute,
                kills_per_minute, dpm_percentile, kpm_percentile, benchmark_sample_count,
                team_average, opponent_average, formula_version, created_at
            )
            SELECT
                legacy.match_id, legacy.player_id, legacy.team, legacy.result,
                legacy.old_rating, legacy.delta, 0, legacy.delta, legacy.new_rating,
                NULL, NULL, NULL, NULL, NULL, 0, legacy.team_average,
                legacy.opponent_average, 'legacy_elo', legacy.created_at
            FROM elo_rating_events AS legacy
            WHERE NOT EXISTS (
                SELECT 1 FROM pug_rating_events AS current
                WHERE current.match_id = legacy.match_id
                  AND current.player_id = legacy.player_id
            )
        """)


def downgrade() -> None:
    op.drop_table("pug_rating_events")
    op.drop_column("match_slots", "rating_at_lock")
    op.drop_column("players", "pug_rating")
