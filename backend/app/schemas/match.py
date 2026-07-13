from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MatchSlotRead(BaseModel):
    player_id: int
    display_name: str | None
    discord_username: str
    assigned_class: str
    team: str
    slot_order: int


class MatchRead(BaseModel):
    id: int
    status: str
    map_name: str | None
    winner: str | None
    score_red: int | None
    score_blu: int | None
    ready_check_expires_at: datetime | None
    created_at: datetime
    completed_at: datetime | None
    log_ids: list[int]
    slots: list[MatchSlotRead]


class MatchCreateRequest(BaseModel):
    map_name: str | None = None


class MatchStateUpdateRequest(BaseModel):
    status: str
    winner: str | None = None
    score_red: int | None = None
    score_blu: int | None = None


class AttachLogRequest(BaseModel):
    log_id: int | None = None
    log_url: str | None = None


class LeaderboardEntry(BaseModel):
    player_id: int
    display_name: str | None
    discord_username: str
    steam_name: str | None
    matches_played: int
    wins: int
    kills: int
    deaths: int
    assists: int
    damage: int
    healing: int


class RecentMatchListResponse(BaseModel):
    matches: list[MatchRead] = Field(default_factory=list)

