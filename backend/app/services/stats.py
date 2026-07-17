from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import delete, desc, select
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
        self._ingest_log_payload(payload, match.id, log_id=log_id)
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
            self._ingest_log_payload(
                payload,
                None,
                player_filter={player.steam_id},
                log_id=log_id,
            )
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
        self._ingest_log_payload(
            payload,
            None,
            create_missing_players=True,
            log_id=log_id,
        )
        self.db.commit()
        return True

    def get_leaderboard(self, limit: int = 500) -> list[tuple[Player, PlayerAggregate]]:
        rows = self.db.execute(
            select(Player, PlayerAggregate)
            .join(PlayerAggregate, PlayerAggregate.player_id == Player.id)
            .order_by(desc(PlayerAggregate.wins), desc(PlayerAggregate.damage))
            .limit(limit)
        )
        return list(rows.all())

    def get_player_class_stats(self, player_id: int) -> list[dict[str, str | int | float]]:
        rows = self.db.scalars(
            select(PlayerMatchStat).where(PlayerMatchStat.player_id == player_id)
        )
        totals: dict[str, dict[str, int]] = {}
        for stat in rows:
            breakdown = stat.class_breakdown or {}
            if not breakdown:
                continue
            majority_class = max(
                breakdown,
                key=lambda name: (breakdown[name].get("total_time", 0), name),
            )
            for class_name, class_row in breakdown.items():
                total = totals.setdefault(
                    class_name,
                    {
                        "matches_played": 0,
                        "wins": 0,
                        "losses": 0,
                        "kills": 0,
                        "deaths": 0,
                        "assists": 0,
                        "damage": 0,
                        "time": 0,
                    },
                )
                total["kills"] += class_row.get("kills", 0)
                total["deaths"] += class_row.get("deaths", 0)
                total["assists"] += class_row.get("assists", 0)
                total["damage"] += class_row.get("damage", 0)
                total["time"] += class_row.get("total_time", 0)
                if class_name == majority_class:
                    total["matches_played"] += 1
                    total["wins"] += int(stat.result == "win")
                    total["losses"] += int(stat.result == "loss")

        result: list[dict[str, str | int | float]] = []
        for class_name, total in totals.items():
            decided = total["wins"] + total["losses"]
            result.append(
                {
                    "class_name": class_name,
                    "matches_played": total["matches_played"],
                    "wins": total["wins"],
                    "losses": total["losses"],
                    "win_percentage": total["wins"] / decided * 100 if decided else 0,
                    "kills": total["kills"],
                    "deaths": total["deaths"],
                    "assists": total["assists"],
                    "kill_death_ratio": (
                        total["kills"] / total["deaths"]
                        if total["deaths"]
                        else total["kills"]
                    ),
                    "damage_per_minute": (
                        total["damage"] / total["time"] * 60 if total["time"] else 0
                    ),
                }
            )
        return sorted(result, key=lambda row: (-int(row["matches_played"]), str(row["class_name"])))

    def rebuild_aggregates(self) -> int:
        stats = list(self.db.scalars(select(PlayerMatchStat).order_by(PlayerMatchStat.id)))
        self.db.execute(delete(PlayerAggregate))
        self.db.flush()
        for instance in list(self.db.identity_map.values()):
            if isinstance(instance, PlayerAggregate):
                self.db.expunge(instance)
        for stat in stats:
            stat.combat_damage, stat.combat_time_seconds = self._combat_totals(
                stat.class_breakdown or {}
            )
            self._update_aggregate(stat.player_id, stat)
        self.db.commit()
        return len(stats)

    def _ingest_log_payload(
        self,
        payload: dict,
        match_id: int | None,
        player_filter: set[str] | None = None,
        create_missing_players: bool = False,
        log_id: int | None = None,
    ) -> None:
        payload_log_id = payload.get("info", {}).get("logid")
        if log_id is None and payload_log_id is None:
            raise ValueError("The logs.tf payload did not include a log ID.")
        log_id = int(log_id if log_id is not None else payload_log_id)
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
            observed_name = payload.get("names", {}).get(raw_steam_id)
            if observed_name:
                self._record_name(player, observed_name)
            existing = self.db.scalar(
                select(PlayerMatchStat).where(
                    PlayerMatchStat.player_id == player.id, PlayerMatchStat.log_id == log_id
                )
            )
            if existing:
                continue

            team = stats.get("team")
            result = "draw" if winning_team is None else ("win" if team == winning_team else "loss")
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
            combat_damage, combat_time_seconds = self._combat_totals(class_breakdown)
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
                won=result == "win",
                result=result,
                combat_damage=combat_damage,
                combat_time_seconds=combat_time_seconds,
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

    @staticmethod
    def _record_name(player: Player, observed_name: str) -> None:
        name = observed_name.strip()[:100]
        if not name:
            return
        frequencies = dict(player.name_frequencies or {})
        frequencies[name] = frequencies.get(name, 0) + 1
        player.name_frequencies = frequencies
        if not player.username_locked:
            player.display_name = min(frequencies, key=lambda value: (-frequencies[value], value.lower()))

    @staticmethod
    def _combat_totals(class_breakdown: dict) -> tuple[int, int]:
        combat_classes = [
            row for class_name, row in class_breakdown.items() if class_name != "medic"
        ]
        return (
            sum(row.get("damage", 0) for row in combat_classes),
            sum(row.get("total_time", 0) for row in combat_classes),
        )

    def _update_aggregate(self, player_id: int, stat: PlayerMatchStat) -> None:
        aggregate = next(
            (
                row
                for row in self.db.new
                if isinstance(row, PlayerAggregate) and row.player_id == player_id
            ),
            None,
        )
        if not aggregate:
            aggregate = self.db.scalar(
                select(PlayerAggregate).where(PlayerAggregate.player_id == player_id)
            )
        if not aggregate:
            aggregate = PlayerAggregate(
                player_id=player_id,
                matches_played=0,
                wins=0,
                draws=0,
                losses=0,
                kills=0,
                deaths=0,
                assists=0,
                damage=0,
                healing=0,
                combat_damage=0,
                combat_time_seconds=0,
            )
            self.db.add(aggregate)
        aggregate.matches_played += 1
        aggregate.wins += 1 if stat.won else 0
        aggregate.draws += 1 if stat.result == "draw" else 0
        aggregate.losses += 1 if stat.result == "loss" else 0
        aggregate.kills += stat.kills
        aggregate.deaths += stat.deaths
        aggregate.assists += stat.assists
        aggregate.damage += stat.damage
        aggregate.healing += stat.healing
        aggregate.combat_damage += stat.combat_damage
        aggregate.combat_time_seconds += stat.combat_time_seconds
        aggregate.last_log_id = stat.log_id
