from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.constants import MatchStatus
from app.models.entities import Match, MatchLog, PlayerMatchStat, PugRatingEvent

COMBAT_CLASSES = frozenset({"scout", "soldier", "demoman"})


@dataclass(frozen=True)
class PerformanceEvidence:
    dominant_class: str | None = None
    damage_per_minute: float | None = None
    kills_per_minute: float | None = None
    dpm_percentile: float | None = None
    kpm_percentile: float | None = None
    benchmark_sample_count: int = 0
    impact_modifier: int = 0


class PugRatingService:
    FORMULA_VERSION = "outcome_first_v1"
    BASE_RESULT = 16
    TEAM_STRENGTH_RANGE = 8
    MAX_IMPACT = 4
    MIN_CLASS_SECONDS = 300
    MIN_BENCHMARK_SAMPLES = 20
    MAX_BENCHMARK_SAMPLES = 100

    def __init__(self, db: Session) -> None:
        self.db = db

    def settle_match(self, match: Match) -> bool:
        if match.status != MatchStatus.COMPLETED.value:
            return False
        match_log = self.db.scalar(select(MatchLog).where(MatchLog.match_id == match.id))
        if not match_log or match.winner not in {"RED", "BLU", "DRAW"}:
            return False
        if self.db.scalar(select(PugRatingEvent.id).where(PugRatingEvent.match_id == match.id)):
            return False

        slots = list(match.slots)
        red = [slot for slot in slots if slot.team == "RED"]
        blu = [slot for slot in slots if slot.team == "BLU"]
        if len(slots) != 12 or len(red) != 6 or len(blu) != 6:
            return False

        red_average = round(sum(self._locked_rating(slot) for slot in red) / 6)
        blu_average = round(sum(self._locked_rating(slot) for slot in blu) / 6)
        expected_red = 1 / (1 + 10 ** ((blu_average - red_average) / 400))
        current_stats = {
            stat.player_id: stat
            for stat in self.db.scalars(
                select(PlayerMatchStat).where(
                    PlayerMatchStat.match_id == match.id,
                    PlayerMatchStat.log_id == match_log.log_id,
                )
            )
        }

        for slot in slots:
            old_rating = (
                slot.player.pug_rating
                if slot.player.pug_rating is not None
                else slot.player.elo_rating
                if slot.player.elo_rating is not None
                else self._locked_rating(slot)
            )
            result = (
                "draw"
                if match.winner == "DRAW"
                else "win"
                if slot.team == match.winner
                else "loss"
            )
            team_expected = expected_red if slot.team == "RED" else 1 - expected_red
            evidence = self._performance_evidence(
                current_stats.get(slot.player_id),
                match_log.log_id,
            )
            result_component, delta = self._delta(result, team_expected, evidence)
            new_rating = old_rating + delta
            slot.player.pug_rating = new_rating
            slot.player.elo_rating = new_rating
            self.db.add(
                PugRatingEvent(
                    match_id=match.id,
                    player_id=slot.player_id,
                    team=slot.team,
                    result=result,
                    old_rating=old_rating,
                    result_component=result_component,
                    impact_modifier=evidence.impact_modifier,
                    delta=delta,
                    new_rating=new_rating,
                    dominant_class=evidence.dominant_class,
                    damage_per_minute=evidence.damage_per_minute,
                    kills_per_minute=evidence.kills_per_minute,
                    dpm_percentile=evidence.dpm_percentile,
                    kpm_percentile=evidence.kpm_percentile,
                    benchmark_sample_count=evidence.benchmark_sample_count,
                    team_average=red_average if slot.team == "RED" else blu_average,
                    opponent_average=blu_average if slot.team == "RED" else red_average,
                    formula_version=self.FORMULA_VERSION,
                )
            )
        self.db.commit()
        return True

    def _performance_evidence(
        self,
        stat: PlayerMatchStat | None,
        current_log_id: int,
    ) -> PerformanceEvidence:
        if not stat:
            return PerformanceEvidence()
        dominant_class, row = self._dominant_class(stat.class_breakdown or {})
        if not dominant_class or not row:
            return PerformanceEvidence(dominant_class=dominant_class)
        seconds = self._number(row.get("total_time"))
        damage = self._number(row.get("damage"))
        kills = self._number(row.get("kills"))
        dpm = damage / seconds * 60 if seconds > 0 else None
        kpm = kills / seconds * 60 if seconds > 0 else None
        if (
            dominant_class not in COMBAT_CLASSES
            or seconds < self.MIN_CLASS_SECONDS
            or dpm is None
            or kpm is None
        ):
            return PerformanceEvidence(
                dominant_class=dominant_class,
                damage_per_minute=dpm,
                kills_per_minute=kpm,
            )

        benchmarks = self._benchmarks(dominant_class, current_log_id)
        if len(benchmarks) < self.MIN_BENCHMARK_SAMPLES:
            return PerformanceEvidence(
                dominant_class=dominant_class,
                damage_per_minute=dpm,
                kills_per_minute=kpm,
                benchmark_sample_count=len(benchmarks),
            )
        dpm_percentile = self._percentile(dpm, [item[0] for item in benchmarks])
        kpm_percentile = self._percentile(kpm, [item[1] for item in benchmarks])
        combined = 0.65 * dpm_percentile + 0.35 * kpm_percentile
        modifier = max(
            -self.MAX_IMPACT,
            min(self.MAX_IMPACT, round(self.MAX_IMPACT * 2 * (combined - 0.5))),
        )
        return PerformanceEvidence(
            dominant_class=dominant_class,
            damage_per_minute=dpm,
            kills_per_minute=kpm,
            dpm_percentile=dpm_percentile,
            kpm_percentile=kpm_percentile,
            benchmark_sample_count=len(benchmarks),
            impact_modifier=modifier,
        )

    def _benchmarks(self, class_name: str, current_log_id: int) -> list[tuple[float, float]]:
        output: list[tuple[float, float]] = []
        rows = self.db.scalars(
            select(PlayerMatchStat)
            .where(PlayerMatchStat.log_id != current_log_id)
            .order_by(desc(PlayerMatchStat.recorded_at), desc(PlayerMatchStat.id))
        )
        for stat in rows:
            dominant_class, class_row = self._dominant_class(stat.class_breakdown or {})
            if dominant_class != class_name or not class_row:
                continue
            seconds = self._number(class_row.get("total_time"))
            if seconds < self.MIN_CLASS_SECONDS:
                continue
            output.append(
                (
                    self._number(class_row.get("damage")) / seconds * 60,
                    self._number(class_row.get("kills")) / seconds * 60,
                )
            )
            if len(output) == self.MAX_BENCHMARK_SAMPLES:
                break
        return output

    @classmethod
    def _delta(
        cls,
        result: str,
        expected_score: float,
        evidence: PerformanceEvidence,
    ) -> tuple[int, int]:
        if result == "draw":
            return 0, 0
        if evidence.dominant_class == "medic":
            result_component = cls.BASE_RESULT if result == "win" else -cls.BASE_RESULT
            return result_component, result_component
        if result == "win":
            magnitude = round(
                cls.BASE_RESULT + cls.TEAM_STRENGTH_RANGE * (0.5 - expected_score)
            )
            result_component = magnitude
            delta = max(8, min(24, magnitude + evidence.impact_modifier))
        else:
            magnitude = round(
                cls.BASE_RESULT + cls.TEAM_STRENGTH_RANGE * (expected_score - 0.5)
            )
            result_component = -magnitude
            delta = max(-24, min(-8, -magnitude + evidence.impact_modifier))
        return result_component, delta

    @staticmethod
    def _locked_rating(slot) -> int:
        return slot.rating_at_lock or slot.elo_at_lock or 0

    @classmethod
    def _dominant_class(cls, breakdown: dict) -> tuple[str | None, dict | None]:
        valid = [
            (str(name).lower(), row)
            for name, row in breakdown.items()
            if isinstance(row, dict)
        ]
        if not valid:
            return None, None
        return max(
            valid,
            key=lambda item: (cls._number(item[1].get("total_time")), item[0]),
        )

    @staticmethod
    def _number(value: object) -> float:
        try:
            return max(0.0, float(value or 0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _percentile(value: float, samples: list[float]) -> float:
        below = sum(item < value for item in samples)
        equal = sum(item == value for item in samples)
        return (below + 0.5 * equal) / len(samples)


# Keep existing imports working during the compatibility period.
EloService = PugRatingService
