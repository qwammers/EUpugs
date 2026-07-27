from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import MatchStatus
from app.models.entities import EloRatingEvent, Match, MatchLog


class EloService:
    K_FACTOR = 32

    def __init__(self, db: Session) -> None:
        self.db = db

    def settle_match(self, match: Match) -> bool:
        if match.status != MatchStatus.COMPLETED.value:
            return False
        if not self.db.scalar(select(MatchLog.id).where(MatchLog.match_id == match.id)):
            return False
        if match.winner not in {"RED", "BLU", "DRAW"}:
            return False
        if self.db.scalar(select(EloRatingEvent.id).where(EloRatingEvent.match_id == match.id)):
            return False
        slots = list(match.slots)
        if len(slots) != 12:
            return False
        red = [slot for slot in slots if slot.team == "RED"]
        blu = [slot for slot in slots if slot.team == "BLU"]
        if len(red) != 6 or len(blu) != 6:
            return False
        red_average = round(sum(slot.elo_at_lock for slot in red) / 6)
        blu_average = round(sum(slot.elo_at_lock for slot in blu) / 6)
        expected_red = 1 / (1 + 10 ** ((blu_average - red_average) / 400))
        red_score = 0.5 if match.winner == "DRAW" else (1.0 if match.winner == "RED" else 0.0)
        red_delta = round(self.K_FACTOR * (red_score - expected_red))
        for slot in slots:
            old_rating = slot.player.elo_rating or slot.elo_at_lock
            delta = red_delta if slot.team == "RED" else -red_delta
            result = "draw" if match.winner == "DRAW" else (
                "win" if slot.team == match.winner else "loss"
            )
            slot.player.elo_rating = old_rating + delta
            self.db.add(EloRatingEvent(
                match_id=match.id,
                player_id=slot.player_id,
                team=slot.team,
                result=result,
                old_rating=old_rating,
                delta=delta,
                new_rating=old_rating + delta,
                team_average=red_average if slot.team == "RED" else blu_average,
                opponent_average=blu_average if slot.team == "RED" else red_average,
            ))
        self.db.commit()
        return True
