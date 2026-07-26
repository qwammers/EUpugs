from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlayerAggregateRead(BaseModel):
    matches_played: int
    wins: int
    draws: int
    losses: int
    kills: int
    deaths: int
    assists: int
    damage: int
    healing: int
    combat_damage: int
    combat_time_seconds: int
    last_log_id: int | None


class PlayerRead(BaseModel):
    id: int
    discord_user_id: str
    discord_username: str
    display_name: str | None
    username_locked: bool
    avatar_url: str | None
    steam_id: str | None
    steam_name: str | None
    steam_connected: bool
    guild_role_ids: list[str]
    last_synced_at: datetime | None
    aggregate: PlayerAggregateRead | None = None
    class_stats: list["PlayerClassStatsRead"] = Field(default_factory=list)
    etf2l_player_id: int | None = None
    etf2l_profile_url: str | None = None
    etf2l_recent_division: str | None = None
    etf2l_highest_division: str | None = None
    etf2l_skill_band: str | None = None
    etf2l_decision: str | None = None
    etf2l_checked_at: datetime | None = None


class PlayerClassStatsRead(BaseModel):
    class_name: str
    matches_played: int
    wins: int
    losses: int
    win_percentage: float
    kills: int
    deaths: int
    assists: int
    kill_death_ratio: float
    damage_per_minute: float


class MeResponse(BaseModel):
    player: PlayerRead
    is_admin: bool


class PlayerUsernameUpdate(BaseModel):
    username: str


class Etf2lDecisionRequest(BaseModel):
    decision: str
