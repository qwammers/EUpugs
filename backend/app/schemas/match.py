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
    rating_at_lock: int = 0
    rating_delta: int | None = None
    rating_result_component: int | None = None
    rating_impact_modifier: int | None = None
    rating_dominant_class: str | None = None
    rating_damage_per_minute: float | None = None
    rating_kills_per_minute: float | None = None
    rating_dpm_percentile: float | None = None
    rating_kpm_percentile: float | None = None
    rating_benchmark_samples: int | None = None
    rating_formula_version: str | None = None
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
    team_average_rating: dict[str, float] = Field(default_factory=dict)
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
    pug_rating: int | None = None
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
