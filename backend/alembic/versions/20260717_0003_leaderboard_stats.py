"""add inferred usernames and leaderboard statistics

Revision ID: 20260717_0003
Revises: 20260717_0002
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260717_0003"
down_revision = "20260717_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("username_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("players", sa.Column("name_frequencies", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("player_match_stats", sa.Column("result", sa.String(length=8), nullable=False, server_default="loss"))
    op.add_column("player_match_stats", sa.Column("combat_damage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("player_match_stats", sa.Column("combat_time_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("player_aggregates", sa.Column("draws", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("player_aggregates", sa.Column("losses", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("player_aggregates", sa.Column("combat_damage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("player_aggregates", sa.Column("combat_time_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE player_match_stats SET result = CASE WHEN won THEN 'win' ELSE 'loss' END")
    op.execute(
        "UPDATE player_aggregates SET losses = GREATEST(matches_played - wins, 0)"
    )


def downgrade() -> None:
    op.drop_column("player_aggregates", "combat_time_seconds")
    op.drop_column("player_aggregates", "combat_damage")
    op.drop_column("player_aggregates", "losses")
    op.drop_column("player_aggregates", "draws")
    op.drop_column("player_match_stats", "combat_time_seconds")
    op.drop_column("player_match_stats", "combat_damage")
    op.drop_column("player_match_stats", "result")
    op.drop_column("players", "name_frequencies")
    op.drop_column("players", "username_locked")
