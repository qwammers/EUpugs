from __future__ import annotations

import re

import httpx


class LogsTfClient:
    base_api = "https://logs.tf/api/v1"
    log_url_pattern = re.compile(r"logs\.tf/(?:json/)?(?P<log_id>\d+)")

    async def get_log(self, log_id: int) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.base_api}/log/{log_id}")
        response.raise_for_status()
        return response.json()

    async def search_logs_for_player(self, steam_id: str, limit: int = 20) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.base_api}/log",
                params={"player": steam_id, "limit": limit, "offset": 0},
            )
        response.raise_for_status()
        return response.json()

    def parse_log_id(self, value: str) -> int | None:
        if value.isdigit():
            return int(value)
        match = self.log_url_pattern.search(value)
        if match:
            return int(match.group("log_id"))
        return None

