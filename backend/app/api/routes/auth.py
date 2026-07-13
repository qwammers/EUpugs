from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_player, get_settings_dep
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.player import MeResponse, PlayerAggregateRead, PlayerRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/discord/start")
async def start_discord_login(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    service = AuthService(None, settings)  # type: ignore[arg-type]
    return RedirectResponse(url=service.discord.build_authorize_url(state), status_code=status.HTTP_302_FOUND)


@router.get("/discord/callback")
async def discord_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> RedirectResponse:
    expected_state = request.session.get("oauth_state")
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state.")

    service = AuthService(db, settings)
    _, session_token = await service.complete_discord_login(code)

    response = RedirectResponse(url=settings.frontend_origin, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.frontend_origin.startswith("https://"),
        samesite="none" if settings.frontend_origin.startswith("https://") else "lax",
    )
    request.session.clear()
    return response


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> MessageResponse:
    token = request.cookies.get(settings.session_cookie_name)
    AuthService(db, settings).logout(token)
    response.delete_cookie(settings.session_cookie_name)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=MeResponse)
@router.get("/api/me", response_model=MeResponse, include_in_schema=False)
def get_me(
    player=Depends(get_current_player),
    settings: Settings = Depends(get_settings_dep),
) -> MeResponse:
    aggregate = None
    if player.aggregate:
        aggregate = PlayerAggregateRead.model_validate(player.aggregate, from_attributes=True)
    return MeResponse(
        player=PlayerRead(
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
        ),
        is_admin=bool(set(player.guild_role_ids).intersection(settings.admin_role_ids)),
    )
