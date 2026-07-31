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
    MatchRead,
    MatchStateUpdateRequest,
    MatchSubstitutionRequest,
)
from app.schemas.player import (
    Etf2lDecisionRequest,
    PlayerAggregateRead,
    PlayerRead,
    PlayerUsernameUpdate,
)
from app.schemas.queue import QueueStateResponse
from app.services.etf2l import Etf2lService
from app.services.match import MatchService
from app.services.queue import QueueService
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
        pug_rating=player.pug_rating,
        elo_rating=player.pug_rating,
        elo_seed_source=player.elo_seed_source,
        aggregate=aggregate,
    )


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
    return MatchService(db).serialize(match, player)


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
    return match_service.serialize(refreshed, player)


@router.delete("/queue/players/{player_id}", response_model=QueueStateResponse)
def remove_queued_player(
    player_id: int,
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = QueueService(db, settings)
    service.remove_player(player_id)
    return service.build_queue_state(admin)


@router.post("/matches/{match_id}/substitute", response_model=MatchRead)
def substitute_player(
    match_id: int,
    payload: MatchSubstitutionRequest,
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MatchRead:
    service = MatchService(db)
    try:
        match = service.substitute(
            match_id, payload.outgoing_player_id, payload.incoming_player_id, admin
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.serialize(match, admin)


def _etf2l_summary(player: Player) -> dict:
    return {
        "player_id": player.id,
        "display_name": player.display_name or player.discord_username,
        "steam_id": player.steam_id,
        "etf2l_player_id": player.etf2l_player_id,
        "profile_url": player.etf2l_profile_url,
        "recent_division": player.etf2l_recent_division,
        "highest_division": player.etf2l_highest_division,
        "skill_band": player.etf2l_skill_band,
        "decision": player.etf2l_decision,
        "checked_at": player.etf2l_checked_at,
        "evidence": player.etf2l_evidence,
    }


@router.get("/etf2l/reviews")
def list_etf2l_reviews(
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    _ = admin
    players = db.scalars(
        select(Player)
        .where(Player.etf2l_decision == "manual_review")
        .order_by(Player.etf2l_checked_at.desc())
    )
    return [_etf2l_summary(player) for player in players]


@router.post("/players/{player_id}/etf2l/refresh")
async def refresh_etf2l(
    player_id: int,
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    _ = admin
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    return _etf2l_summary(await Etf2lService(db, settings).refresh(player, force=True))


@router.post("/players/{player_id}/etf2l/decision")
def decide_etf2l(
    player_id: int,
    payload: Etf2lDecisionRequest,
    admin: Player = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    try:
        result = Etf2lService(db, settings).decide(
            player, admin, payload.decision, payload.skill_tier
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _etf2l_summary(result)
