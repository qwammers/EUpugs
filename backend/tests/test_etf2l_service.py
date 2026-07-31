from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.etf2l import Etf2lService
from tests.support import make_session, seed_player


class FakeClient:
    def __init__(self, results: list[dict], profile: dict | None = None) -> None:
        self.results = results
        self.profile = profile or {"player": {"id": 42, "urls": {"self": "https://etf2l.org/forum/user/42"}}}

    async def get_player(self, steam_id: str) -> dict:
        _ = steam_id
        return self.profile

    async def get_results(self, steam_id: str, page: int, limit: int = 50) -> dict:
        _ = steam_id, page, limit
        return {"results": {"data": self.results, "last_page": 1}}


def make_service(results: list[dict]) -> tuple[Etf2lService, object]:
    db = make_session()
    player = seed_player(db, 1)
    settings = SimpleNamespace(
        etf2l_api_base_url="https://api-v2.etf2l.org",
        etf2l_history_page_limit=2,
    )
    service = Etf2lService(db, settings)  # type: ignore[arg-type]
    service.client = FakeClient(results)  # type: ignore[assignment]
    return service, player


def result(division: str, tier: int = 5, competition_type: str = "6v6") -> dict:
    return {
        "competition": {"type": competition_type, "name": "Season"},
        "division": {"name": division, "tier": tier},
        "time": 1,
    }


def test_etf2l_low_player_is_recommended_for_runner_review() -> None:
    service, player = make_service([result("Low")])
    asyncio.run(service.refresh(player, force=True))
    assert player.etf2l_skill_band == "lower"
    assert player.etf2l_decision == "manual_review"
    assert player.etf2l_evidence["recommended_tier"] == "sapphire"


def test_etf2l_highest_history_requires_review() -> None:
    service, player = make_service([result("Open"), result("Division 3", 3)])
    asyncio.run(service.refresh(player, force=True))
    assert player.etf2l_highest_division == "Division 3"
    assert player.etf2l_decision == "manual_review"


def test_etf2l_ignores_non_sixes_results() -> None:
    service, player = make_service([result("Premiership", 1, "Highlander")])
    asyncio.run(service.refresh(player, force=True))
    assert player.etf2l_skill_band == "pubber"
    assert player.etf2l_decision == "manual_review"


def test_runner_tier_does_not_reset_established_rating() -> None:
    service, player = make_service([])
    admin = seed_player(service.db, 2)
    player.pug_rating = 1127
    service.db.commit()

    service.decide(player, admin, "accepted", "obsidian")

    assert player.pug_rating == 1127
    assert player.elo_rating == 1000
