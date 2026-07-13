from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import MatchStatus, QueueBucket, TEAM_ORDER
from app.models.entities import Match, MatchSlot, Player, QueueEntry
from app.schemas.match import MatchRead, MatchSlotRead
from app.services.queue import QueueService


class MatchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.queue_service = QueueService(db)

    def create_match_from_active_queue(self, admin: Player, map_name: str | None = None) -> Match:
        active_entries = self.queue_service.get_entries(QueueBucket.ACTIVE.value)
        assignments = self.queue_service.find_matchable_assignment(active_entries)
        if not assignments:
            raise ValueError("Queue does not currently contain a valid 12-player 6s composition.")

        match = Match(
            status=MatchStatus.READY_CHECK.value,
            created_by_player_id=admin.id,
            map_name=map_name,
            ready_check_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        self.db.add(match)
        self.db.flush()

        team_slots: list[MatchSlot] = []
        class_counts = {team: {"scout": 0, "soldier": 0, "demo": 0, "medic": 0} for team in TEAM_ORDER}
        for slot_order, assignment in enumerate(assignments):
            preferred_team = TEAM_ORDER[0]
            for team in TEAM_ORDER:
                target = 2 if assignment.assigned_class in {"scout", "soldier"} else 1
                if class_counts[team][assignment.assigned_class] < target:
                    preferred_team = team
                    break
            class_counts[preferred_team][assignment.assigned_class] += 1
            team_slots.append(
                MatchSlot(
                    match_id=match.id,
                    player_id=assignment.player_id,
                    team=preferred_team,
                    assigned_class=assignment.assigned_class,
                    slot_order=slot_order,
                )
            )

        self.db.add_all(team_slots)

        selected_player_ids = {assignment.player_id for assignment in assignments}
        for entry in active_entries:
            if entry.player_id in selected_player_ids:
                self.db.delete(entry)
        self.db.commit()
        self.db.refresh(match)
        return match

    def get_current_match(self) -> Match | None:
        return (
            self.db.execute(
                select(Match)
                .where(
                    Match.status.in_(
                        [status.value for status in MatchStatus if status != MatchStatus.COMPLETED]
                    )
                )
                .options(joinedload(Match.slots).joinedload(MatchSlot.player), joinedload(Match.logs))
                .order_by(desc(Match.created_at))
            )
            .unique()
            .scalars()
            .first()
        )

    def get_recent_matches(self, limit: int = 10) -> list[Match]:
        return list(
            self.db.execute(
                select(Match)
                .options(joinedload(Match.slots).joinedload(MatchSlot.player), joinedload(Match.logs))
                .order_by(desc(Match.created_at))
                .limit(limit)
            )
            .unique()
            .scalars()
        )

    def get_match(self, match_id: int) -> Match | None:
        return (
            self.db.execute(
                select(Match)
                .where(Match.id == match_id)
                .options(joinedload(Match.slots).joinedload(MatchSlot.player), joinedload(Match.logs))
            )
            .unique()
            .scalars()
            .first()
        )

    def update_match_state(
        self,
        match_id: int,
        status: str,
        winner: str | None = None,
        score_red: int | None = None,
        score_blu: int | None = None,
    ) -> Match:
        match = self.get_match(match_id)
        if not match:
            raise ValueError("Match not found.")

        match.status = status
        match.winner = winner
        match.score_red = score_red
        match.score_blu = score_blu
        if status == MatchStatus.COMPLETED.value:
            match.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(match)
        return match

    @staticmethod
    def serialize(match: Match) -> MatchRead:
        return MatchRead(
            id=match.id,
            status=match.status,
            map_name=match.map_name,
            winner=match.winner,
            score_red=match.score_red,
            score_blu=match.score_blu,
            ready_check_expires_at=match.ready_check_expires_at,
            created_at=match.created_at,
            completed_at=match.completed_at,
            log_ids=[log.log_id for log in match.logs],
            slots=[
                MatchSlotRead(
                    player_id=slot.player_id,
                    display_name=slot.player.display_name,
                    discord_username=slot.player.discord_username,
                    assigned_class=slot.assigned_class,
                    team=slot.team,
                    slot_order=slot.slot_order,
                )
                for slot in sorted(match.slots, key=lambda item: item.slot_order)
            ],
        )
