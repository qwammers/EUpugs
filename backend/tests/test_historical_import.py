from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import ImportedLog, Player, PlayerAggregate, PlayerMatchStat
from app.services.stats import StatsService


class FakeLogsClient:
    async def get_log(self, log_id: int) -> dict:
        return {
            "info": {"title": "Test PUG", "map": "cp_process_f12"},
            "names": {"[U:1:12345]": "Imported Player"},
            "teams": {"Red": {"score": 5}, "Blue": {"score": 2}},
            "players": {
                "[U:1:12345]": {
                    "team": "Red",
                    "kills": 20,
                    "deaths": 10,
                    "assists": 5,
                    "dmg": 6000,
                    "heal": 0,
                    "class_stats": [
                        {
                            "type": "scout",
                            "kills": 20,
                            "deaths": 10,
                            "assists": 5,
                            "dmg": 6000,
                            "total_time": 1200,
                        }
                    ],
                }
            },
        }


@pytest.mark.anyio
async def test_historical_import_creates_provisional_player_and_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        service = StatsService(db, SimpleNamespace())  # type: ignore[arg-type]
        service.client = FakeLogsClient()  # type: ignore[assignment]

        assert await service.import_historical_log(123, "test") is True
        assert await service.import_historical_log(123, "test") is False

        player = db.scalar(select(Player))
        assert player is not None
        assert player.discord_user_id == "logstf:76561197960278073"
        assert player.steam_id == "76561197960278073"
        assert player.display_name == "Imported Player"

        stat = db.scalar(select(PlayerMatchStat))
        assert stat is not None
        assert stat.kills == 20
        assert stat.won is True

        aggregate = db.scalar(select(PlayerAggregate))
        assert aggregate is not None
        assert aggregate.matches_played == 1
        assert aggregate.wins == 1
        assert aggregate.draws == 0
        assert aggregate.losses == 0
        assert aggregate.damage == 6000
        assert aggregate.combat_damage == 6000
        assert aggregate.combat_time_seconds == 1200
        assert db.scalar(select(ImportedLog).where(ImportedLog.log_id == 123)) is not None


def test_most_common_observed_name_changes_only_until_admin_lock() -> None:
    player = Player(
        discord_user_id="logstf:1",
        discord_username="Original",
        display_name="Original",
        username_locked=False,
        name_frequencies={},
        guild_role_ids=[],
    )

    StatsService._record_name(player, "First")
    StatsService._record_name(player, "Common")
    StatsService._record_name(player, "Common")
    assert player.display_name == "Common"

    player.username_locked = True
    StatsService._record_name(player, "Later")
    StatsService._record_name(player, "Later")
    StatsService._record_name(player, "Later")
    assert player.display_name == "Common"
