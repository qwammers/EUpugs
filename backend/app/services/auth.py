from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.discord_client import DiscordOAuthClient
from app.core.config import Settings
from app.models.entities import Player, Session as PlayerSession


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.discord = DiscordOAuthClient(settings)

    async def complete_discord_login(self, code: str) -> tuple[Player, str]:
        token_response = await self.discord.exchange_code(code)
        access_token = token_response["access_token"]
        user = await self.discord.get_current_user(access_token)
        member = await self.discord.get_guild_member(access_token)
        connections = await self.discord.get_connections(access_token)

        steam_connection = next((item for item in connections if item.get("type") == "steam"), None)

        discord_user_id = str(user["id"])
        steam_id = steam_connection.get("id") if steam_connection else None
        player = self.db.scalar(select(Player).where(Player.discord_user_id == discord_user_id))
        provisional = None
        if steam_id:
            provisional = self.db.scalar(select(Player).where(Player.steam_id == steam_id))
        if not player and provisional and provisional.discord_user_id.startswith("logstf:"):
            player = provisional
            player.discord_user_id = discord_user_id
        if not player:
            player = Player(
                discord_user_id=discord_user_id,
                discord_username=user["username"],
            )
            self.db.add(player)
        elif provisional and provisional.id != player.id:
            raise ValueError("This Steam account is already linked to another Discord account.")

        avatar = user.get("avatar")
        player.discord_username = user["username"]
        player.display_name = user.get("global_name") or user["username"]
        player.avatar_url = (
            f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar}.png" if avatar else None
        )
        player.guild_role_ids = member.get("roles", [])
        player.steam_connected = steam_connection is not None
        player.steam_id = steam_id
        player.steam_name = steam_connection.get("name") if steam_connection else None
        player.last_synced_at = datetime.now(timezone.utc)

        session_token = secrets.token_urlsafe(48)
        session = PlayerSession(
            token=session_token,
            player=player,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self.settings.session_max_age_seconds),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(player)
        return player, session_token

    def get_player_for_session(self, token: str | None) -> Player | None:
        if not token:
            return None
        session = self.db.scalar(select(PlayerSession).where(PlayerSession.token == token))
        if not session:
            return None
        if session.expires_at <= datetime.now(timezone.utc):
            self.db.delete(session)
            self.db.commit()
            return None
        return session.player

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session = self.db.scalar(select(PlayerSession).where(PlayerSession.token == token))
        if session:
            self.db.delete(session)
            self.db.commit()
