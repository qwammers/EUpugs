from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.entities import Player
from app.services.auth import AuthService


def get_settings_dep() -> Settings:
    return get_settings()


def get_current_player(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Player:
    service = AuthService(db, settings)
    token = request.cookies.get(settings.session_cookie_name)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    player = service.get_player_for_session(token)
    if not player:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return player


def require_admin(
    player: Player = Depends(get_current_player),
    settings: Settings = Depends(get_settings_dep),
) -> Player:
    if not set(player.guild_role_ids).intersection(settings.admin_role_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    return player
