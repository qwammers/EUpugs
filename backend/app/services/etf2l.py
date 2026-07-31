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
                self._apply(player, None, None, "pubber", "manual_review", {
                    "profile": None, "recommended_tier": None
                })
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
                self._apply(player, None, None, "pubber", "manual_review", {
                    "profile": profile, "results": [], "complete": complete,
                    "recommended_tier": None,
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
            recommendation = self._recommend_tier(recent_name, highest_name)
            self._apply(player, recent_name, highest_name, band, "manual_review", {
                "profile": profile, "results": sixes, "complete": True,
                "recommended_tier": recommendation,
            })
            return player
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            self._apply(player, None, None, "unknown", "manual_review", {"error": str(exc)})
            return player

    def decide(
        self, player: Player, admin: Player, decision: str, skill_tier: str | None = None
    ) -> Player:
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
            if decision == "accepted" and skill_tier:
                tiers = {
                    "obsidian": ("1363181710463860826", 1600),
                    "sapphire": ("1363181641014575425", 1400),
                    "silver": ("1363181525939519709", 1200),
                    "bronze": ("1367534417303703703", 1000),
                    "steel": ("1363541855668666459", 900),
                    "iron": ("1375873812679364798", 800),
                }
                if skill_tier.lower() not in tiers:
                    raise ValueError("Unknown skill tier.")
                role_id, rating = tiers[skill_tier.lower()]
                if player.pug_rating is None:
                    player.pug_rating = rating
                    player.elo_rating = rating
                    player.elo_seed_source = "etf2l_review"
                    player.elo_source_role_id = role_id
                    player.elo_seeded_at = datetime.now(timezone.utc)
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

    @staticmethod
    def _recommend_tier(recent: str, highest: str) -> str | None:
        tiers = {"bronze": 1, "silver": 2, "sapphire": 3, "obsidian": 4}

        def recommendation(name: str) -> str | None:
            value = name.lower()
            if "division 4" in value or "div 4" in value or "top low" in value:
                return "obsidian"
            if "low" in value or "top open" in value:
                return "sapphire"
            if "open" in value:
                return "silver"
            if "fresh" in value:
                return "bronze"
            return None

        values = [value for value in (recommendation(recent), recommendation(highest)) if value]
        return max(values, key=lambda value: tiers[value]) if values else None
