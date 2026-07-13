from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.entities import Player
from app.services.queue import QueueService


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return factory()


def seed_player(db: Session, idx: int, steam: bool = True) -> Player:
    player = Player(
        discord_user_id=str(idx),
        discord_username=f"user{idx}",
        display_name=f"User {idx}",
        steam_connected=steam,
        steam_id=str(76561198000000000 + idx) if steam else None,
        guild_role_ids=[],
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def test_join_queue_rejects_duplicate_entries() -> None:
    db = make_session()
    service = QueueService(db)
    player = seed_player(db, 1)

    service.join_queue(player, ["scout"], "active")
    try:
        service.join_queue(player, ["soldier"], "active")
    except ValueError as exc:
        assert "already queued" in str(exc)
    else:
        raise AssertionError("Duplicate queue join should fail.")


def test_matchable_assignment_accepts_valid_12_player_pool() -> None:
    db = make_session()
    service = QueueService(db)
    classes = [
        ["scout"],
        ["scout"],
        ["scout", "soldier"],
        ["soldier"],
        ["soldier"],
        ["soldier", "scout"],
        ["demo"],
        ["demo", "soldier"],
        ["medic"],
        ["medic", "scout"],
        ["soldier"],
        ["scout"],
    ]

    for idx, prefs in enumerate(classes, start=1):
        player = seed_player(db, idx)
        service.join_queue(player, prefs, "active")

    assignment = service.find_matchable_assignment(service.get_entries("active"))
    assert assignment is not None
    assert len(assignment) == 12
    counts = {}
    for row in assignment:
        counts[row.assigned_class] = counts.get(row.assigned_class, 0) + 1
    assert counts == {"scout": 4, "soldier": 4, "demo": 2, "medic": 2}


def test_join_queue_requires_steam_connection() -> None:
    db = make_session()
    service = QueueService(db)
    player = seed_player(db, 99, steam=False)

    try:
        service.join_queue(player, ["medic"], "active")
    except ValueError as exc:
        assert "Steam connection" in str(exc)
    else:
        raise AssertionError("Non-Steam player should not join queue.")
