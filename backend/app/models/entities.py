from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import JobStatus, MatchStatus, QueueBucket
from app.models.base import Base, TimestampMixin, utcnow


class GuildConfig(Base):
    __tablename__ = "guild_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(32), unique=True)
    log_channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    admin_role_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_user_id: Mapped[str] = mapped_column(String(32), unique=True)
    discord_username: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    username_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    name_frequencies: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steam_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    steam_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    steam_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    guild_role_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    etf2l_player_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etf2l_profile_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    etf2l_recent_division: Mapped[str | None] = mapped_column(String(100), nullable=True)
    etf2l_highest_division: Mapped[str | None] = mapped_column(String(100), nullable=True)
    etf2l_skill_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    etf2l_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    etf2l_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    etf2l_reviewed_by_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    etf2l_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    etf2l_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    elo_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elo_seed_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    elo_source_role_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    elo_seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    queue_entries: Mapped[list["QueueEntry"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    aggregate: Mapped["PlayerAggregate | None"] = relationship(
        back_populates="player", cascade="all, delete-orphan", uselist=False
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    player: Mapped[Player] = relationship(back_populates="sessions")


class QueueEntry(Base, TimestampMixin):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    queue_bucket: Mapped[str] = mapped_column(String(16), default=QueueBucket.ACTIVE.value)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_ready_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    player: Mapped[Player] = relationship(back_populates="queue_entries")
    preferences: Mapped[list["QueuePreference"]] = relationship(
        back_populates="queue_entry", cascade="all, delete-orphan"
    )


class QueuePreference(Base):
    __tablename__ = "queue_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_entry_id: Mapped[int] = mapped_column(ForeignKey("queue_entries.id"))
    class_name: Mapped[str] = mapped_column(String(16))
    is_flex: Mapped[bool] = mapped_column(Boolean, default=False)

    queue_entry: Mapped[QueueEntry] = relationship(back_populates="preferences")


class QueueCycle(Base):
    __tablename__ = "queue_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_bucket: Mapped[str] = mapped_column(String(16), unique=True)
    ready_check_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ready_check_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    map_candidates: Mapped[list[str]] = mapped_column(JSON, default=list)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    selected_player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QueueMapVote(Base):
    __tablename__ = "queue_map_votes"
    __table_args__ = (UniqueConstraint("queue_cycle_id", "player_id", name="uq_queue_map_vote_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_cycle_id: Mapped[int] = mapped_column(ForeignKey("queue_cycles.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    map_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default=MatchStatus.FORMING.value)
    created_by_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    map_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    map_candidates: Mapped[list[str]] = mapped_column(JSON, default=list)
    discord_setup: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teams_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score_red: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_blu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ready_check_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    slots: Mapped[list["MatchSlot"]] = relationship(back_populates="match", cascade="all, delete-orphan")
    logs: Mapped[list["MatchLog"]] = relationship(back_populates="match", cascade="all, delete-orphan")
    substitutions: Mapped[list["MatchSubstitution"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class MatchSlot(Base):
    __tablename__ = "match_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team: Mapped[str] = mapped_column(String(3))
    assigned_class: Mapped[str] = mapped_column(String(16))
    slot_order: Mapped[int] = mapped_column(Integer)
    elo_at_lock: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped[Match] = relationship(back_populates="slots")
    player: Mapped[Player] = relationship()


class MatchSubstitution(Base):
    __tablename__ = "match_substitutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    outgoing_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    incoming_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    created_by_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team: Mapped[str] = mapped_column(String(3))
    assigned_class: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    match: Mapped[Match] = relationship(back_populates="substitutions")
    outgoing_player: Mapped[Player] = relationship(foreign_keys=[outgoing_player_id])
    incoming_player: Mapped[Player] = relationship(foreign_keys=[incoming_player_id])


class MatchLog(Base):
    __tablename__ = "match_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    log_id: Mapped[int] = mapped_column(unique=True)
    log_url: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    map_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    match: Mapped[Match] = relationship(back_populates="logs")


class EloRatingEvent(Base):
    __tablename__ = "elo_rating_events"
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_elo_event_match_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team: Mapped[str] = mapped_column(String(3))
    result: Mapped[str] = mapped_column(String(8))
    old_rating: Mapped[int] = mapped_column(Integer)
    delta: Mapped[int] = mapped_column(Integer)
    new_rating: Mapped[int] = mapped_column(Integer)
    team_average: Mapped[int] = mapped_column(Integer)
    opponent_average: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportedLog(Base):
    __tablename__ = "imported_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_id: Mapped[int] = mapped_column(unique=True)
    log_url: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    map_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="bulk_import")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlayerMatchStat(Base):
    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    log_id: Mapped[int] = mapped_column(Integer)
    kills: Mapped[int] = mapped_column(Integer, default=0)
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    damage: Mapped[int] = mapped_column(Integer, default=0)
    healing: Mapped[int] = mapped_column(Integer, default=0)
    class_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    won: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str] = mapped_column(String(8), default="loss")
    combat_damage: Mapped[int] = mapped_column(Integer, default=0)
    combat_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    player: Mapped[Player] = relationship()
    match: Mapped[Match | None] = relationship()


class PlayerAggregate(Base):
    __tablename__ = "player_aggregates"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), unique=True)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    kills: Mapped[int] = mapped_column(Integer, default=0)
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    damage: Mapped[int] = mapped_column(Integer, default=0)
    healing: Mapped[int] = mapped_column(Integer, default=0)
    combat_damage: Mapped[int] = mapped_column(Integer, default=0)
    combat_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    player: Mapped[Player] = relationship(back_populates="aggregate")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.RUNNING.value)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
