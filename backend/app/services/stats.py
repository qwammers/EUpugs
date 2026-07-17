from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.clients.logstf_client import LogsTfClient
from app.core.config import Settings
from app.models.entities import (
    ImportedLog,
    JobRun,
    Match,
    MatchLog,
    Player,
    PlayerAggregate,
    PlayerMatchStat,
)


class StatsService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.client = LogsTfClient()

    async def attach_log_to_match(self, match: Match, log_input: str | int) -> MatchLog:
        log_id = int(log_input) if str(log_input).isdigit() else self.client.parse_log_id(str(log_input))
        if not log_id:
            raise ValueError("Could not determine logs.tf log id.")

        existing = self.db.scalar(select(MatchLog).where(MatchLog.log_id == log_id))
        if existing:
            return existing

        payload = await self.client.get_log(log_id)
        match_log = MatchLog(
            match_id=match.id,
            log_id=log_id,
            log_url=f"https://logs.tf/{log_id}",
            title=payload.get("info", {}).get("title"),
            map_name=payload.get("info", {}).get("map"),
            raw_payload=payload,
        )
        self.db.add(match_log)
        self.db.flush()
        self._ingest_log_payload(payload, match.id)
        self.db.commit()
        self.db.refresh(match_log)
        return match_log

    async def sync_recent_history_for_player(self, player: Player) -> int:
        if not player.steam_id:
            return 0
        results = await self.client.search_logs_for_player(player.steam_id, self.settings.logstf_sync_limit)
        log_entries = results.get("logs", [])
        imported = 0
        for entry in log_entries:
            log_id = int(entry["id"])
            exists = self.db.scalar(
                select(PlayerMatchStat).where(
                    PlayerMatchStat.player_id == player.id, PlayerMatchStat.log_id == log_id
                )
            )
            if exists:
                continue
            payload = await self.client.get_log(log_id)
            self._ingest_log_payload(payload, None, player_filter={player.steam_id})
            imported += 1
        self.db.commit()
        return imported

    async def import_historical_log(self, log_id: int, source: str = "bulk_import") -> bool:
        existing = self.db.scalar(select(ImportedLog).where(ImportedLog.log_id == log_id))
        if existing:
            return False

        payload = await self.client.get_log(log_id)
        info = payload.get("info", {})
        self.db.add(
            ImportedLog(
                log_id=log_id,
                log_url=f"https://logs.tf/{log_id}",
                title=info.get("title"),
                map_name=info.get("map"),
                source=source,
                raw_payload=payload,
            )
        )
        self._ingest_log_payload(payload, None, create_missing_players=True)
        self.db.commit()
        return True

    def get_leaderboard(self, limit: int = 25) -> list[tuple[Player, PlayerAggregate]]:
        rows = self.db.execute(
            select(Player, PlayerAggregate)
            .join(PlayerAggregate, PlayerAggregate.player_id == Player.id)
            .order_by(desc(PlayerAggregate.wins), desc(PlayerAggregate.damage))
            .limit(limit)
        )
        return list(rows.all())

    def _ingest_log_payload(
        self,
        payload: dict,
        match_id: int | None,
        player_filter: set[str] | None = None,
        create_missing_players: bool = False,
    ) -> None:
        log_id = int(payload["info"]["logid"])
        players_blob = payload.get("players", {})
        teams = payload.get("teams", {})
        winning_team = None
        if teams.get("Red", {}).get("score", 0) > teams.get("Blue", {}).get("score", 0):
            winning_team = "Red"
        elif teams.get("Blue", {}).get("score", 0) > teams.get("Red", {}).get("score", 0):
            winning_team = "Blue"

        canonical_filter = {self._steam64(value) for value in player_filter} if player_filter else None
        for raw_steam_id, stats in players_blob.items():
            steam_id = self._steam64(raw_steam_id)
            if canonical_filter and steam_id not in canonical_filter:
                continue
            player = self.db.scalar(select(Player).where(Player.steam_id == steam_id))
            if not player and create_missing_players:
                steam_name = payload.get("names", {}).get(raw_steam_id) or steam_id
                player = Player(
                    discord_user_id=f"logstf:{steam_id}",
                    discord_username=steam_name,
                    display_name=steam_name,
                    steam_id=steam_id,
                    steam_name=steam_name,
                    steam_connected=False,
                    guild_role_ids=[],
                )
                self.db.add(player)
                self.db.flush()
            if not player:
                continue
            existing = self.db.scalar(
                select(PlayerMatchStat).where(
                    PlayerMatchStat.player_id == player.id, PlayerMatchStat.log_id == log_id
                )
            )
            if existing:
                continue

            team = stats.get("team")
            won = winning_team is not None and team == winning_team
            class_breakdown = {
                item.get("type", "unknown"): {
                    "kills": item.get("kills", 0),
                    "deaths": item.get("deaths", 0),
                    "assists": item.get("assists", 0),
                    "damage": item.get("dmg", 0),
                    "total_time": item.get("total_time", 0),
                }
                for item in stats.get("class_stats", [])
            }
            row = PlayerMatchStat(
                player_id=player.id,
                match_id=match_id,
                log_id=log_id,
                kills=stats.get("kills", 0),
                deaths=stats.get("deaths", 0),
                assists=stats.get("assists", 0),
                damage=stats.get("dmg", 0),
                healing=stats.get("heal", 0),
                class_breakdown=class_breakdown,
                won=won,
            )
            self.db.add(row)
            self._update_aggregate(player.id, row)

        self.db.add(
            JobRun(
                job_name="log_ingest",
                status="success",
                details={"log_id": log_id, "match_id": match_id},
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _steam64(value: str) -> str:
        steam3 = re.fullmatch(r"\[U:1:(\d+)\]", value)
        if steam3:
            return str(76561197960265728 + int(steam3.group(1)))
        steam2 = re.fullmatch(r"STEAM_[0-5]:([01]):(\d+)", value)
        if steam2:
            return str(76561197960265728 + int(steam2.group(2)) * 2 + int(steam2.group(1)))
        return value

    def _update_aggregate(self, player_id: int, stat: PlayerMatchStat) -> None:
        aggregate = self.db.scalar(select(PlayerAggregate).where(PlayerAggregate.player_id == player_id))
        if not aggregate:
            aggregate = PlayerAggregate(
                player_id=player_id,
                matches_played=0,
                wins=0,
                kills=0,
                deaths=0,
                assists=0,
                damage=0,
                healing=0,
            )
            self.db.add(aggregate)
        aggregate.matches_played += 1
        aggregate.wins += 1 if stat.won else 0
        aggregate.kills += stat.kills
        aggregate.deaths += stat.deaths
        aggregate.assists += stat.assists
        aggregate.damage += stat.damage
        aggregate.healing += stat.healing
        aggregate.last_log_id = stat.log_id
