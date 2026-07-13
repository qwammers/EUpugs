from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlayerAggregateRead(BaseModel):
    matches_played: int
    wins: int
    kills: int
    deaths: int
    assists: int
    damage: int
    healing: int
    last_log_id: int | None


class PlayerRead(BaseModel):
    id: int
    discord_user_id: str
    discord_username: str
    display_name: str | None
    avatar_url: str | None
    steam_id: str | None
    steam_name: str | None
    steam_connected: bool
    guild_role_ids: list[str]
    last_synced_at: datetime | None
    aggregate: PlayerAggregateRead | None = None


class MeResponse(BaseModel):
    player: PlayerRead
    is_admin: bool

