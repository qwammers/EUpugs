from __future__ import annotations

from app.models.entities import Match, MatchLog, MatchSlot
from app.services.elo import EloService
from backend.tests.test_queue_service import make_session, seed_player


def test_equal_team_elo_win_applies_once() -> None:
    db = make_session()
    players = [seed_player(db, index) for index in range(1, 13)]
    match = Match(status="completed", winner="RED", map_candidates=[])
    db.add(match)
    db.flush()
    for index, player in enumerate(players):
        db.add(MatchSlot(
            match_id=match.id,
            player_id=player.id,
            team="RED" if index < 6 else "BLU",
            assigned_class="scout",
            slot_order=index,
            elo_at_lock=1000,
        ))
    db.add(MatchLog(match_id=match.id, log_id=999, log_url="https://logs.tf/999"))
    db.commit()
    db.refresh(match)

    assert EloService(db).settle_match(match) is True
    assert [player.elo_rating for player in players[:6]] == [1016] * 6
    assert [player.elo_rating for player in players[6:]] == [984] * 6
    assert EloService(db).settle_match(match) is False
