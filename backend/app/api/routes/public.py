from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.db.session import get_db
from app.models.entities import Player
from app.schemas.common import HealthResponse
from app.schemas.match import LeaderboardEntry, MatchRead, RecentMatchListResponse
from app.schemas.player import PlayerAggregateRead, PlayerRead
from app.schemas.queue import QueueStateResponse
from app.services.match import MatchService
from app.services.queue import QueueService
from app.services.stats import StatsService

router = APIRouter(tags=["public"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", now=datetime.now(timezone.utc))


@router.get("/api/queue", response_model=QueueStateResponse)
def get_queue_state(db: Session = Depends(get_db)) -> QueueStateResponse:
    return QueueService(db).build_queue_state()


@router.get("/api/matches/current", response_model=MatchRead | None)
def get_current_match(db: Session = Depends(get_db)) -> MatchRead | None:
    match = MatchService(db).get_current_match()
    return MatchService.serialize(match) if match else None


@router.get("/api/matches/recent", response_model=RecentMatchListResponse)
def get_recent_matches(db: Session = Depends(get_db)) -> RecentMatchListResponse:
    matches = MatchService(db).get_recent_matches()
    return RecentMatchListResponse(matches=[MatchService.serialize(match) for match in matches])


@router.get("/api/players/{player_id}", response_model=PlayerRead)
def get_player(player_id: int, db: Session = Depends(get_db)) -> PlayerRead:
    player = db.scalar(
        select(Player).where(Player.id == player_id).options(joinedload(Player.aggregate))
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    aggregate = (
        PlayerAggregateRead.model_validate(player.aggregate, from_attributes=True)
        if player.aggregate
        else None
    )
    return PlayerRead(
        id=player.id,
        discord_user_id=player.discord_user_id,
        discord_username=player.discord_username,
        display_name=player.display_name,
        avatar_url=player.avatar_url,
        steam_id=player.steam_id,
        steam_name=player.steam_name,
        steam_connected=player.steam_connected,
        guild_role_ids=player.guild_role_ids,
        last_synced_at=player.last_synced_at,
        aggregate=aggregate,
    )


@router.get("/api/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> list[LeaderboardEntry]:
    rows = StatsService(db, settings).get_leaderboard()
    return [
        LeaderboardEntry(
            player_id=player.id,
            display_name=player.display_name,
            discord_username=player.discord_username,
            steam_name=player.steam_name,
            matches_played=aggregate.matches_played,
            wins=aggregate.wins,
            kills=aggregate.kills,
            deaths=aggregate.deaths,
            assists=aggregate.assists,
            damage=aggregate.damage,
            healing=aggregate.healing,
        )
        for player, aggregate in rows
    ]

