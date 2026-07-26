from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.clients.etf2l_client import Etf2lClient
from app.core.config import Settings
from app.models.entities import Player

AUTO_LABELS = ("fresh", "open", "low", "division 5", "division 6", "div 5", "div 6")
REVIEW_LABELS = (
    "prem",
    "high",
    "mid",
    "division 1",
    "division 2",
    "division 3",
    "division 4",
    "div 1",
    "div 2",
    "div 3",
    "div 4",
)


class Etf2lService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.client = Etf2lClient(settings.etf2l_api_base_url)

    async def refresh(self, player: Player, force: bool = False) -> Player:
        now = datetime.now(timezone.utc)
        if (
            not force
            and player.etf2l_checked_at
            and player.etf2l_checked_at > now - timedelta(hours=24)
        ):
            return player
        if not player.steam_id:
            raise ValueError("Player has no linked Steam ID.")

        try:
            profile_payload = await self.client.get_player(player.steam_id)
            profile = profile_payload.get("player", profile_payload if profile_payload else {})
            if not profile:
                self._apply(player, None, None, "fresh", "accepted", {"profile": None})
                return player

            results: list[dict] = []
            complete = False
            for page in range(1, self.settings.etf2l_history_page_limit + 1):
                payload = await self.client.get_results(player.steam_id, page)
                paginator = payload.get("results", payload)
                page_rows = paginator.get("data", []) if isinstance(paginator, dict) else []
                if not isinstance(page_rows, list):
                    raise ValueError("Malformed ETF2L results response.")
                results.extend(page_rows)
                last_page = int(paginator.get("last_page", page))
                if page >= last_page:
                    complete = True
                    break

            sixes = [
                row for row in results
                if str((row.get("competition") or {}).get("type", "")).lower() in {"6v6", "6on6"}
            ]
            divisions = [
                row.get("division") for row in sixes if isinstance(row.get("division"), dict)
            ]
            if sixes and len(divisions) != len(sixes):
                self._apply(player, None, None, "unknown", "manual_review", {
                    "profile": profile, "results": sixes, "complete": complete
                })
                return player
            if not sixes:
                self._apply(player, None, None, "fresh", "accepted", {
                    "profile": profile, "results": [], "complete": complete
                })
                return player
            if not complete:
                self._apply(player, None, None, "unknown", "manual_review", {
                    "profile": profile, "results": sixes, "complete": False
                })
                return player

            recent_name = str(divisions[0].get("name", "")).strip()
            ranked = sorted(divisions, key=self._division_rank, reverse=True)
            highest_name = str(ranked[0].get("name", "")).strip()
            band = self._classify(highest_name)
            decision = "accepted" if band == "lower" else "manual_review"
            self._apply(player, recent_name, highest_name, band, decision, {
                "profile": profile, "results": sixes, "complete": True
            })
            return player
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            self._apply(player, None, None, "unknown", "manual_review", {"error": str(exc)})
            return player

    def decide(self, player: Player, admin: Player, decision: str) -> Player:
        if decision not in {"accepted", "rejected", "automatic"}:
            raise ValueError("Decision must be accepted, rejected, or automatic.")
        if decision == "automatic":
            player.etf2l_decision = (
                "accepted" if player.etf2l_skill_band in {"fresh", "lower"} else "manual_review"
            )
            player.etf2l_reviewed_by_player_id = None
            player.etf2l_reviewed_at = None
        else:
            player.etf2l_decision = decision
            player.etf2l_reviewed_by_player_id = admin.id
            player.etf2l_reviewed_at = datetime.now(timezone.utc)
        self.db.commit()
        return player

    def _apply(
        self,
        player: Player,
        recent: str | None,
        highest: str | None,
        band: str,
        decision: str,
        evidence: dict,
    ) -> None:
        profile = evidence.get("profile") or {}
        player.etf2l_player_id = profile.get("id")
        urls = profile.get("urls") or {}
        player.etf2l_profile_url = urls.get("self") or urls.get("player")
        player.etf2l_recent_division = recent
        player.etf2l_highest_division = highest
        player.etf2l_skill_band = band
        if not player.etf2l_reviewed_at:
            player.etf2l_decision = decision
        player.etf2l_checked_at = datetime.now(timezone.utc)
        player.etf2l_evidence = evidence
        self.db.commit()

    @staticmethod
    def _classify(name: str) -> str:
        normalized = re.sub(r"\s+", " ", name.lower()).strip()
        if any(label in normalized for label in REVIEW_LABELS):
            return "review"
        if any(label in normalized for label in AUTO_LABELS):
            return "lower"
        return "unknown"

    @staticmethod
    def _division_rank(division: dict) -> int:
        name = str(division.get("name", ""))
        classification = Etf2lService._classify(name)
        if classification == "review":
            tier = division.get("tier")
            return 1000 - int(tier) if isinstance(tier, int) else 500
        if classification == "lower":
            return 100
        return 400
