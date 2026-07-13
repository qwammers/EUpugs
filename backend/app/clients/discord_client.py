from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import Settings


class DiscordApiError(RuntimeError):
    pass


class DiscordOAuthClient:
    base_api = "https://discord.com/api/v10"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.discord_client_id,
                "scope": "identify guilds.members.read connections",
                "state": state,
                "redirect_uri": self.settings.discord_redirect_uri,
                "prompt": "consent",
            }
        )
        return f"https://discord.com/oauth2/authorize?{query}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_api}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.discord_redirect_uri,
                },
                auth=(self.settings.discord_client_id, self.settings.discord_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.is_error:
            raise DiscordApiError(f"Discord token exchange failed: {response.text}")
        return response.json()

    async def get_current_user(self, access_token: str) -> dict:
        return await self._get("/users/@me", access_token)

    async def get_guild_member(self, access_token: str) -> dict:
        return await self._get(
            f"/users/@me/guilds/{self.settings.discord_guild_id}/member", access_token
        )

    async def get_connections(self, access_token: str) -> list[dict]:
        return await self._get("/users/@me/connections", access_token)

    async def _get(self, path: str, access_token: str) -> dict | list[dict]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.base_api}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.is_error:
            raise DiscordApiError(f"Discord API request failed: {path} {response.text}")
        return response.json()

