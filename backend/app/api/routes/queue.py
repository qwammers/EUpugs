from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_player, get_settings_dep
from app.core.config import Settings
from app.db.session import get_db
from app.models.entities import Player
from app.schemas.common import MessageResponse
from app.schemas.queue import (
    MapVoteRequest,
    QueueFlexRequest,
    QueueJoinRequest,
    QueuePrimaryRequest,
    QueueStateResponse,
)
from app.services.queue import QueueService

router = APIRouter(prefix="/api/queue", tags=["queue"])


def _service(db: Session, settings: Settings) -> QueueService:
    return QueueService(db, settings)


@router.put("/primary", response_model=QueueStateResponse)
def set_primary(
    payload: QueuePrimaryRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = _service(db, settings)
    try:
        service.upsert_primary(player, payload.primary_class, payload.flex_classes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.build_queue_state(player)


@router.patch("/flex", response_model=QueueStateResponse)
def set_flex(
    payload: QueueFlexRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = _service(db, settings)
    try:
        service.update_flex(player, payload.flex_classes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.build_queue_state(player)


@router.post("/join", response_model=QueueStateResponse)
def legacy_join(
    payload: QueueJoinRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    primary = payload.primary_class
    flex = payload.flex_classes
    if payload.classes:
        primary, flex = payload.classes[0], payload.classes[1:]
    if not primary:
        raise HTTPException(status_code=400, detail="A primary class is required.")
    return set_primary(QueuePrimaryRequest(primary_class=primary, flex_classes=flex), player, db, settings)


@router.post("/leave", response_model=QueueStateResponse)
def leave(
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = _service(db, settings)
    service.leave_queue(player)
    return service.build_queue_state(player)


@router.post("/pre-ready", response_model=QueueStateResponse)
def pre_ready(
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = _service(db, settings)
    try:
        service.set_pre_ready(player)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.build_queue_state(player)


@router.post("/ready", response_model=MessageResponse)
def ready(
    ready: bool,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MessageResponse:
    try:
        _service(db, settings).set_ready(player, ready)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message=f"Ready state updated to {ready}.")


@router.post("/map-vote", response_model=QueueStateResponse)
def map_vote(
    payload: MapVoteRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> QueueStateResponse:
    service = _service(db, settings)
    try:
        service.vote_map(player, payload.map_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.build_queue_state(player)
