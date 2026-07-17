from __future__ import annotations

import re

import httpx


class LogsTfClient:
    base_api = "https://logs.tf/api/v1"
    # Historical posts commonly contain the loogs.tf typo; only the numeric ID
    # matters because payloads are always fetched from the canonical API.
    log_url_pattern = re.compile(
        r"(?:https?://)?(?:www\.)?lo+gs\.tf/(?:json/)?(?P<log_id>\d+)",
        re.IGNORECASE,
    )

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

    def parse_log_ids(self, value: str) -> set[int]:
        ids = {int(match.group("log_id")) for match in self.log_url_pattern.finditer(value)}
        if value.strip().isdigit():
            ids.add(int(value.strip()))
        return ids
