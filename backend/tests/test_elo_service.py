from __future__ import annotations

from app.models.entities import (
    Match,
    MatchLog,
    MatchSlot,
    PlayerMatchStat,
    PugRatingEvent,
)
from app.services.elo import PerformanceEvidence, PugRatingService
from tests.support import make_session, seed_player


def create_match(db, winner: str = "RED", red_rating: int = 1000, blu_rating: int = 1000):
    players = [seed_player(db, index) for index in range(1, 13)]
    match = Match(status="completed", winner=winner, map_candidates=[])
    db.add(match)
    db.flush()
    for index, player in enumerate(players):
        rating = red_rating if index < 6 else blu_rating
        player.pug_rating = rating
        player.elo_rating = rating
        db.add(
            MatchSlot(
                match_id=match.id,
                player_id=player.id,
                team="RED" if index < 6 else "BLU",
                assigned_class="scout",
                slot_order=index,
                rating_at_lock=rating,
                elo_at_lock=rating,
            )
        )
    db.add(MatchLog(match_id=match.id, log_id=999, log_url="https://logs.tf/999"))
    db.commit()
    db.refresh(match)
    return match, players


def class_row(class_name: str, damage: int, kills: int, seconds: int = 600) -> dict:
    return {
        class_name: {
            "kills": kills,
            "deaths": 0,
            "assists": 0,
            "damage": damage,
            "total_time": seconds,
        }
    }


def test_result_amounts_and_sign_guarantees() -> None:
    neutral = PerformanceEvidence()
    high = PerformanceEvidence(impact_modifier=4)
    low = PerformanceEvidence(impact_modifier=-4)

    assert PugRatingService._delta("win", 0.5, neutral) == (16, 16)
    assert PugRatingService._delta("loss", 0.5, neutral) == (-16, -16)
    assert PugRatingService._delta("draw", 0.9, high) == (0, 0)
    assert PugRatingService._delta("win", 0.9, high) == (13, 17)
    assert PugRatingService._delta("win", 0.1, low) == (19, 15)
    assert PugRatingService._delta("loss", 0.9, high) == (-19, -15)
    assert PugRatingService._delta("loss", 0.1, low) == (-13, -17)


def test_medic_has_static_result_and_no_performance_adjustment() -> None:
    medic = PerformanceEvidence(dominant_class="medic", impact_modifier=4)
    assert PugRatingService._delta("win", 0.95, medic) == (16, 16)
    assert PugRatingService._delta("loss", 0.05, medic) == (-16, -16)


def test_class_benchmark_increases_winner_and_reduces_loser_loss() -> None:
    db = make_session()
    match, players = create_match(db)
    for index in range(20):
        db.add(
            PlayerMatchStat(
                player_id=players[index % 12].id,
                log_id=100 + index,
                class_breakdown=class_row("scout", 3000, 5),
                result="win",
            )
        )
    db.add_all(
        [
            PlayerMatchStat(
                player_id=players[0].id,
                match_id=match.id,
                log_id=999,
                class_breakdown=class_row("scout", 6000, 10),
                result="win",
            ),
            PlayerMatchStat(
                player_id=players[6].id,
                match_id=match.id,
                log_id=999,
                class_breakdown=class_row("scout", 6000, 10),
                result="loss",
            ),
            PlayerMatchStat(
                player_id=players[1].id,
                match_id=match.id,
                log_id=999,
                class_breakdown=class_row("medic", 100, 0),
                result="win",
            ),
        ]
    )
    db.commit()

    assert PugRatingService(db).settle_match(match) is True
    winner = db.query(PugRatingEvent).filter_by(match_id=match.id, player_id=players[0].id).one()
    loser = db.query(PugRatingEvent).filter_by(match_id=match.id, player_id=players[6].id).one()
    medic = db.query(PugRatingEvent).filter_by(match_id=match.id, player_id=players[1].id).one()
    assert winner.impact_modifier == 4
    assert winner.delta == 20
    assert loser.impact_modifier == 4
    assert loser.delta == -12
    assert medic.delta == 16
    assert medic.impact_modifier == 0
    assert PugRatingService(db).settle_match(match) is False


def test_short_or_offclass_performance_has_no_modifier() -> None:
    db = make_session()
    match, players = create_match(db)
    db.add_all(
        [
            PlayerMatchStat(
                player_id=players[0].id,
                match_id=match.id,
                log_id=999,
                class_breakdown=class_row("scout", 6000, 10, seconds=299),
                result="win",
            ),
            PlayerMatchStat(
                player_id=players[1].id,
                match_id=match.id,
                log_id=999,
                class_breakdown=class_row("sniper", 6000, 10),
                result="win",
            ),
        ]
    )
    db.commit()
    PugRatingService(db).settle_match(match)
    events = {
        event.player_id: event
        for event in db.query(PugRatingEvent).filter_by(match_id=match.id).all()
    }
    assert events[players[0].id].impact_modifier == 0
    assert events[players[1].id].impact_modifier == 0
    assert events[players[0].id].delta == 16
    assert events[players[1].id].delta == 16
