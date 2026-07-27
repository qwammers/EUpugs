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
    elo_at_lock: int = 0
    elo_delta: int | None = None


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
    voice_channel_url: str | None = None
    substitutions: list["MatchSubstitutionRead"] = Field(default_factory=list)
    map_candidates: list[str] = Field(default_factory=list)
    discord_setup: int | None = None
    teams_locked_at: datetime | None = None
    team_average_elo: dict[str, float] = Field(default_factory=dict)


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
    losses: int
    win_percentage: float
    average_kills: float
    average_assists: float
    average_deaths: float
    kill_death_ratio: float
    damage_per_minute: float
    elo_rating: int | None = None


class RecentMatchListResponse(BaseModel):
    matches: list[MatchRead] = Field(default_factory=list)


class ActiveMatchListResponse(BaseModel):
    matches: list[MatchRead] = Field(default_factory=list)


class MatchSubstitutionRead(BaseModel):
    outgoing_player_id: int
    outgoing_name: str
    incoming_player_id: int
    incoming_name: str
    assigned_class: str
    team: str
    created_at: datetime


class MatchSubstitutionRequest(BaseModel):
    outgoing_player_id: int
    incoming_player_id: int
