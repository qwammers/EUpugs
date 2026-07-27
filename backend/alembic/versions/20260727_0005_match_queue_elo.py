"""add match-centric queue and Elo ratings

Revision ID: 20260727_0005
Revises: 20260726_0004
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260727_0005"
down_revision = "20260726_0004"
branch_labels = None
depends_on = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    player_columns = _columns(inspector, "players")
    for name, column in [
        ("elo_rating", sa.Column("elo_rating", sa.Integer(), nullable=True)),
        ("elo_seed_source", sa.Column("elo_seed_source", sa.String(length=32), nullable=True)),
        ("elo_source_role_id", sa.Column("elo_source_role_id", sa.String(length=32), nullable=True)),
        ("elo_seeded_at", sa.Column("elo_seeded_at", sa.DateTime(timezone=True), nullable=True)),
    ]:
        if name not in player_columns:
            op.add_column("players", column)

    match_columns = _columns(inspector, "matches")
    if "map_candidates" not in match_columns:
        op.add_column("matches", sa.Column("map_candidates", sa.JSON(), nullable=False, server_default="[]"))
    if "discord_setup" not in match_columns:
        op.add_column("matches", sa.Column("discord_setup", sa.Integer(), nullable=True))
    if "teams_locked_at" not in match_columns:
        op.add_column("matches", sa.Column("teams_locked_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("matches", "created_by_player_id", existing_type=sa.Integer(), nullable=True)

    entry_columns = _columns(inspector, "queue_entries")
    if "match_id" not in entry_columns:
        op.add_column("queue_entries", sa.Column("match_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_queue_entries_match_id", "queue_entries", "matches", ["match_id"], ["id"]
        )

    cycle_columns = _columns(inspector, "queue_cycles")
    if "match_id" not in cycle_columns:
        op.add_column("queue_cycles", sa.Column("match_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_queue_cycles_match_id", "queue_cycles", "matches", ["match_id"], ["id"]
        )
    if "selected_player_ids" not in cycle_columns:
        op.add_column(
            "queue_cycles", sa.Column("selected_player_ids", sa.JSON(), nullable=False, server_default="[]")
        )

    vote_columns = _columns(inspector, "queue_map_votes")
    if "match_id" not in vote_columns:
        op.add_column("queue_map_votes", sa.Column("match_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_queue_map_votes_match_id", "queue_map_votes", "matches", ["match_id"], ["id"]
        )

    slot_columns = _columns(inspector, "match_slots")
    if "elo_at_lock" not in slot_columns:
        op.add_column(
            "match_slots", sa.Column("elo_at_lock", sa.Integer(), nullable=False, server_default="0")
        )

    if "elo_rating_events" not in tables:
        op.create_table(
            "elo_rating_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
            sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
            sa.Column("team", sa.String(length=3), nullable=False),
            sa.Column("result", sa.String(length=8), nullable=False),
            sa.Column("old_rating", sa.Integer(), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("new_rating", sa.Integer(), nullable=False),
            sa.Column("team_average", sa.Integer(), nullable=False),
            sa.Column("opponent_average", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("match_id", "player_id", name="uq_elo_event_match_player"),
        )

    role_ratings = [
        ("1363181710463860826", 1600),
        ("1363181641014575425", 1400),
        ("1363181525939519709", 1200),
        ("1367534417303703703", 1000),
        ("1363541855668666459", 900),
        ("1375873812679364798", 800),
    ]
    if bind.dialect.name == "postgresql":
        for role_id, rating in role_ratings:
            op.execute(sa.text("""
                UPDATE players
                SET elo_rating = :rating, elo_seed_source = 'discord_role',
                    elo_source_role_id = :role_id, elo_seeded_at = NOW()
                WHERE elo_rating IS NULL
                  AND CAST(guild_role_ids AS jsonb) @> CAST(:roles AS jsonb)
            """).bindparams(rating=rating, role_id=role_id, roles=f'["{role_id}"]'))

    if bind.dialect.name == "postgresql":
        op.execute("""
            DELETE FROM queue_entries AS next_entry
            USING queue_entries AS active_entry
            WHERE next_entry.queue_bucket = 'next'
              AND active_entry.queue_bucket = 'active'
              AND next_entry.player_id = active_entry.player_id
        """)
    else:
        op.execute("""
            DELETE FROM queue_entries
            WHERE queue_bucket = 'next'
              AND player_id IN (
                SELECT player_id FROM queue_entries WHERE queue_bucket = 'active'
              )
        """)
    op.execute("UPDATE queue_entries SET queue_bucket = 'active' WHERE queue_bucket = 'next'")

    queued_count = bind.execute(sa.text("SELECT COUNT(*) FROM queue_entries")).scalar_one()
    if queued_count:
        forming_id = bind.execute(sa.text("""
            SELECT id FROM matches
            WHERE status IN ('forming', 'ready_check')
            ORDER BY created_at DESC LIMIT 1
        """)).scalar_one_or_none()
        if forming_id is None:
            forming_id = bind.execute(sa.text("""
                INSERT INTO matches (
                    status, created_by_player_id, map_name, winner, score_red, score_blu,
                    ready_check_expires_at, completed_at, created_at, updated_at,
                    map_candidates, discord_setup, teams_locked_at
                ) VALUES (
                    'forming', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    '["cp_sunshine","cp_process_f12","cp_gullywash_f9"]',
                    NULL, NULL
                ) RETURNING id
            """)).scalar_one()
        bind.execute(
            sa.text("UPDATE queue_entries SET match_id = :match_id WHERE match_id IS NULL"),
            {"match_id": forming_id},
        )
        bind.execute(
            sa.text("""
                UPDATE queue_cycles
                SET match_id = :match_id
                WHERE queue_bucket = 'active'
            """),
            {"match_id": forming_id},
        )
        bind.execute(
            sa.text("""
                UPDATE queue_map_votes
                SET match_id = :match_id
                WHERE match_id IS NULL
            """),
            {"match_id": forming_id},
        )
    op.execute("""
        UPDATE matches
        SET map_candidates = '["cp_sunshine","cp_process_f12","cp_gullywash_f9"]'
        WHERE status IN ('forming', 'ready_check')
          AND (map_candidates IS NULL OR CAST(map_candidates AS TEXT) IN ('[]', 'null'))
    """)


def downgrade() -> None:
    op.drop_table("elo_rating_events")
    op.drop_column("match_slots", "elo_at_lock")
    op.drop_column("queue_map_votes", "match_id")
    op.drop_column("queue_cycles", "selected_player_ids")
    op.drop_column("queue_cycles", "match_id")
    op.drop_column("queue_entries", "match_id")
    op.drop_column("matches", "teams_locked_at")
    op.drop_column("matches", "discord_setup")
    op.drop_column("matches", "map_candidates")
    op.drop_column("players", "elo_seeded_at")
    op.drop_column("players", "elo_source_role_id")
    op.drop_column("players", "elo_seed_source")
    op.drop_column("players", "elo_rating")
