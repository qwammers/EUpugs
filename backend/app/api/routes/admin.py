from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_settings_dep, require_admin
from app.core.config import Settings
from app.db.session import get_db
from app.models.entities import Player
from app.schemas.match import (
    AttachLogRequest,
    MatchCreateRequest,
    MatchRead,
    MatchStateUpdateRequest,
)
from app.schemas.player import PlayerAggregateRead, PlayerRead, PlayerUsernameUpdate
from app.services.match import MatchService
from app.services.stats import StatsService

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.patch("/players/{player_id}/username", response_model=PlayerRead)
def update_player_username(
    player_id: int,
    payload: PlayerUsernameUpdate,
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PlayerRead:
    _ = admin
    username = payload.username.strip()
    if not username or len(username) > 100:
        raise HTTPException(status_code=400, detail="Username must be between 1 and 100 characters.")
    player = db.scalar(
        select(Player).where(Player.id == player_id).options(joinedload(Player.aggregate))
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    player.display_name = username
    player.username_locked = True
    db.commit()
    db.refresh(player)
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
        username_locked=player.username_locked,
        avatar_url=player.avatar_url,
        steam_id=player.steam_id,
        steam_name=player.steam_name,
        steam_connected=player.steam_connected,
        guild_role_ids=player.guild_role_ids,
        last_synced_at=player.last_synced_at,
        aggregate=aggregate,
    )


@router.post("/matches/create", response_model=MatchRead)
def create_match(
    payload: MatchCreateRequest,
    player: Player = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MatchRead:
    try:
        match = MatchService(db).create_match_from_active_queue(player, payload.map_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MatchService.serialize(match)


@router.post("/matches/{match_id}/state", response_model=MatchRead)
def update_match_state(
    match_id: int,
    payload: MatchStateUpdateRequest,
    player: Player = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MatchRead:
    _ = player
    try:
        match = MatchService(db).update_match_state(
            match_id, payload.status, payload.winner, payload.score_red, payload.score_blu
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MatchService.serialize(match)


@router.post("/matches/{match_id}/attach-log", response_model=MatchRead)
async def attach_log(
    match_id: int,
    payload: AttachLogRequest,
    player: Player = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MatchRead:
    _ = player
    match_service = MatchService(db)
    match = match_service.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    log_value = payload.log_id or payload.log_url
    if not log_value:
        raise HTTPException(status_code=400, detail="A log id or URL is required.")

    try:
        await StatsService(db, settings).attach_log_to_match(match, log_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = match_service.get_match(match_id)
    return MatchService.serialize(refreshed)
