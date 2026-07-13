from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_player
from app.db.session import get_db
from app.models.entities import Player
from app.schemas.common import MessageResponse
from app.schemas.queue import QueueJoinRequest, QueueLeaveRequest, QueueStateResponse
from app.services.queue import QueueService

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("/join", response_model=QueueStateResponse)
def join_queue(
    payload: QueueJoinRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
) -> QueueStateResponse:
    service = QueueService(db)
    try:
        service.join_queue(player, payload.classes, payload.queue_bucket)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.build_queue_state()


@router.post("/leave", response_model=QueueStateResponse)
def leave_queue(
    payload: QueueLeaveRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
) -> QueueStateResponse:
    service = QueueService(db)
    service.leave_queue(player, payload.queue_bucket)
    return service.build_queue_state()


@router.post("/ready", response_model=MessageResponse)
def set_ready(
    ready: bool,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        QueueService(db).set_ready(player, ready)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message=f"Ready state updated to {ready}.")
