"""initial schema

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260713_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guild_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("log_channel_id", sa.String(length=32), nullable=True),
        sa.Column("admin_role_ids", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("discord_user_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("discord_username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("steam_id", sa.String(length=32), nullable=True, unique=True),
        sa.Column("steam_name", sa.String(length=100), nullable=True),
        sa.Column("steam_connected", sa.Boolean(), nullable=False),
        sa.Column("guild_role_ids", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=128), nullable=False, unique=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("map_name", sa.String(length=64), nullable=True),
        sa.Column("winner", sa.String(length=8), nullable=True),
        sa.Column("score_red", sa.Integer(), nullable=True),
        sa.Column("score_blu", sa.Integer(), nullable=True),
        sa.Column("ready_check_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "player_aggregates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False, unique=True),
        sa.Column("matches_played", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("kills", sa.Integer(), nullable=False),
        sa.Column("deaths", sa.Integer(), nullable=False),
        sa.Column("assists", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("healing", sa.Integer(), nullable=False),
        sa.Column("last_log_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("queue_bucket", sa.String(length=16), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_queue_entries_bucket_player", "queue_entries", ["queue_bucket", "player_id"], unique=True)
    op.create_table(
        "queue_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_entry_id", sa.Integer(), sa.ForeignKey("queue_entries.id"), nullable=False),
        sa.Column("class_name", sa.String(length=16), nullable=False),
    )
    op.create_table(
        "match_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("log_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("log_url", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("map_name", sa.String(length=64), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "match_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("team", sa.String(length=3), nullable=False),
        sa.Column("assigned_class", sa.String(length=16), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False),
    )
    op.create_table(
        "player_match_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=True),
        sa.Column("log_id", sa.Integer(), nullable=False),
        sa.Column("kills", sa.Integer(), nullable=False),
        sa.Column("deaths", sa.Integer(), nullable=False),
        sa.Column("assists", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("healing", sa.Integer(), nullable=False),
        sa.Column("class_breakdown", sa.JSON(), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_match_stats_player_log", "player_match_stats", ["player_id", "log_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_player_match_stats_player_log", table_name="player_match_stats")
    op.drop_table("player_match_stats")
    op.drop_table("match_slots")
    op.drop_table("match_logs")
    op.drop_table("queue_preferences")
    op.drop_index("ix_queue_entries_bucket_player", table_name="queue_entries")
    op.drop_table("queue_entries")
    op.drop_table("player_aggregates")
    op.drop_table("job_runs")
    op.drop_table("matches")
    op.drop_table("sessions")
    op.drop_table("players")
    op.drop_table("guild_config")

