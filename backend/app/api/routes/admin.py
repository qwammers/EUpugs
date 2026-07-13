from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
from app.services.match import MatchService
from app.services.stats import StatsService

router = APIRouter(prefix="/api/admin", tags=["admin"])


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

