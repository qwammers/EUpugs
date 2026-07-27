from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.entities import Player


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
        elo_rating=1000,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player
