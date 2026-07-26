from __future__ import annotations

import httpx


class Etf2lClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def get_player(self, steam_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/player/{steam_id}", headers={"Accept": "application/json"}
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()

    async def get_results(self, steam_id: str, page: int, limit: int = 50) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/player/{steam_id}/results",
                params={"page": page, "limit": limit},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
