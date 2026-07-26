from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import NamedTuple
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.constants import QUEUE_CLASS_LIMITS, QUEUE_CLASS_ORDER, QueueBucket
from app.models.entities import (
    Player,
    QueueCycle,
    QueueEntry,
    QueueMapVote,
    QueuePreference,
)
from app.schemas.queue import QueueBucketRead, QueuePlayerRead, QueueStateResponse


class QueueAssignment(NamedTuple):
    player_id: int
    assigned_class: str


class QueueService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings

    def blocked_classes(self, player: Player) -> list[str]:
        blocked: set[str] = set()
        restrictions = self.settings.class_restrictions if self.settings else {}
        for role_id in player.guild_role_ids:
            blocked.update(restrictions.get(str(role_id), []))
        return sorted(blocked)

    def join_queue(
        self,
        player: Player,
        primary_class: str | list[str],
        flex_classes: list[str] | str | None = None,
        queue_bucket: str = QueueBucket.ACTIVE.value,
    ) -> QueueEntry:
        if isinstance(primary_class, list):
            legacy_classes = primary_class
            if isinstance(flex_classes, str):
                queue_bucket = flex_classes
            primary_class = legacy_classes[0] if legacy_classes else ""
            flex_classes = legacy_classes[1:]
        flex_classes = flex_classes if isinstance(flex_classes, list) else []
        if not player.steam_connected:
            raise ValueError("A Steam connection is required before joining the queue.")
        if primary_class not in QUEUE_CLASS_ORDER:
            raise ValueError("A valid primary class is required.")
        flex_classes = [item for item in dict.fromkeys(flex_classes) if item != primary_class]
        invalid = [item for item in [primary_class, *flex_classes] if item not in QUEUE_CLASS_ORDER]
        if invalid:
            raise ValueError(f"Invalid classes: {', '.join(invalid)}")
        restricted = set(self.blocked_classes(player)).intersection([primary_class, *flex_classes])
        if restricted:
            raise ValueError(f"Your Discord roles restrict: {', '.join(sorted(restricted))}.")

        existing = self.db.scalar(
            select(QueueEntry).where(
                QueueEntry.player_id == player.id, QueueEntry.queue_bucket == queue_bucket
            )
        )
        if existing:
            raise ValueError(f"Player is already queued in {queue_bucket}.")

        entry = QueueEntry(player_id=player.id, queue_bucket=queue_bucket, ready=False)
        entry.preferences = [
            QueuePreference(class_name=primary_class, is_flex=False),
            *[QueuePreference(class_name=value, is_flex=True) for value in flex_classes],
        ]
        self.db.add(entry)
        self.db.commit()
        self._reconcile_ready_check()
        self.db.refresh(entry)
        return entry

    def leave_queue(self, player: Player, queue_bucket: str) -> None:
        entry = self.db.scalar(
            select(QueueEntry).where(
                QueueEntry.player_id == player.id, QueueEntry.queue_bucket == queue_bucket
            )
        )
        if entry:
            self.db.delete(entry)
            self.db.commit()
            if queue_bucket == QueueBucket.ACTIVE.value:
                self._reconcile_ready_check()

    def set_pre_ready(self, player: Player) -> None:
        entry = self._active_entry(player.id)
        if not entry:
            raise ValueError("Player is not in the active queue.")
        entry.pre_ready_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)
        cycle = self._cycle()
        if (
            cycle.ready_check_expires_at
            and self._aware(cycle.ready_check_expires_at) > datetime.now(timezone.utc)
        ):
            entry.ready = True
        self.db.commit()

    def set_ready(self, player: Player, ready: bool) -> None:
        entry = self._active_entry(player.id)
        cycle = self._cycle()
        now = datetime.now(timezone.utc)
        if not entry:
            raise ValueError("Player is not in the active queue.")
        if (
            not cycle.ready_check_expires_at
            or self._aware(cycle.ready_check_expires_at) <= now
        ):
            raise ValueError("There is no active ready check.")
        entry.ready = ready
        self.db.commit()

    def process_ready_check(self) -> list[int]:
        cycle = self._cycle()
        now = datetime.now(timezone.utc)
        if (
            not cycle.ready_check_expires_at
            or self._aware(cycle.ready_check_expires_at) > now
        ):
            return []
        entries = self.get_entries(QueueBucket.ACTIVE.value)
        removed = [entry.player_id for entry in entries if not entry.ready]
        for entry in entries:
            entry.ready = False
            if entry.player_id in removed:
                self.db.delete(entry)
        self._reset_cycle(cycle)
        self.db.commit()
        self._reconcile_ready_check()
        return removed

    def mark_announced(self) -> None:
        cycle = self._cycle()
        cycle.announced_at = datetime.now(timezone.utc)
        self.db.commit()

    def set_map_candidates(self, maps: list[str]) -> None:
        cleaned = [item.strip() for item in maps if item.strip()]
        if len(cleaned) != 3 or len(set(cleaned)) != 3:
            raise ValueError("Exactly three different maps are required.")
        cycle = self._cycle()
        cycle.map_candidates = cleaned
        self.db.execute(delete(QueueMapVote).where(QueueMapVote.queue_cycle_id == cycle.id))
        self.db.commit()

    def vote_map(self, player: Player, map_name: str) -> None:
        if not self._active_entry(player.id):
            raise ValueError("Only active queued players can vote.")
        cycle = self._cycle()
        if map_name not in cycle.map_candidates:
            raise ValueError("That map is not a current candidate.")
        vote = self.db.scalar(
            select(QueueMapVote).where(
                QueueMapVote.queue_cycle_id == cycle.id, QueueMapVote.player_id == player.id
            )
        )
        if vote:
            vote.map_name = map_name
        else:
            self.db.add(QueueMapVote(queue_cycle_id=cycle.id, player_id=player.id, map_name=map_name))
        self.db.commit()

    def winning_map(self) -> str | None:
        cycle = self._cycle()
        if not cycle.map_candidates:
            return None
        totals = self._vote_totals(cycle)
        return max(cycle.map_candidates, key=lambda item: totals.get(item, 0))

    def complete_cycle(self) -> None:
        cycle = self._cycle()
        self.db.execute(delete(QueueMapVote).where(QueueMapVote.queue_cycle_id == cycle.id))
        self._reset_cycle(cycle)
        cycle.map_candidates = []

    def clear_queue_bucket(self, queue_bucket: str) -> None:
        self.db.execute(delete(QueueEntry).where(QueueEntry.queue_bucket == queue_bucket))
        self.db.commit()

    def get_entries(self, queue_bucket: str) -> list[QueueEntry]:
        return list(
            self.db.execute(
                select(QueueEntry)
                .where(QueueEntry.queue_bucket == queue_bucket)
                .options(joinedload(QueueEntry.player), joinedload(QueueEntry.preferences))
                .order_by(QueueEntry.joined_at.asc())
            )
            .unique()
            .scalars()
        )

    def build_queue_state(self, player: Player | None = None) -> QueueStateResponse:
        self._reconcile_ready_check()
        active_entries = self.get_entries(QueueBucket.ACTIVE.value)
        next_entries = self.get_entries(QueueBucket.NEXT.value)
        assignment = self.find_matchable_assignment(active_entries)
        cycle = self._cycle()
        now = datetime.now(timezone.utc)
        active_check = bool(
            cycle.ready_check_expires_at and self._aware(cycle.ready_check_expires_at) > now
        )
        return QueueStateResponse(
            active=self._bucket_read(QueueBucket.ACTIVE.value, active_entries),
            next=self._bucket_read(QueueBucket.NEXT.value, next_entries),
            matchable=assignment is not None,
            needed_by_class=self.needed_by_class(active_entries),
            phase="ready_check" if active_check else "waiting",
            ready_check_id=cycle.ready_check_token if active_check else None,
            ready_check_expires_at=cycle.ready_check_expires_at if active_check else None,
            map_candidates=cycle.map_candidates,
            map_votes=self._vote_totals(cycle),
            blocked_classes=self.blocked_classes(player) if player else [],
        )

    def needed_by_class(self, entries: list[QueueEntry]) -> dict[str, int]:
        counts = Counter(self._primary(entry) for entry in entries)
        return {
            class_name: max(QUEUE_CLASS_LIMITS[class_name] - counts[class_name], 0)
            for class_name in QUEUE_CLASS_ORDER
        }

    def find_matchable_assignment(self, entries: list[QueueEntry]) -> list[QueueAssignment] | None:
        if len(entries) < 12:
            return None
        for candidate_entries in combinations(entries, 12):
            needed = dict(QUEUE_CLASS_LIMITS)
            chosen: list[QueueAssignment] = []

            def backtrack(index: int) -> bool:
                if index == len(candidate_entries):
                    return all(value == 0 for value in needed.values())
                entry = candidate_entries[index]
                primary = self._primary(entry)
                flex = [pref.class_name for pref in entry.preferences if pref.is_flex]
                options = [primary, *sorted(flex, key=lambda item: -needed[item])]
                for class_name in options:
                    if needed[class_name] <= 0:
                        continue
                    needed[class_name] -= 1
                    chosen.append(QueueAssignment(entry.player_id, class_name))
                    if backtrack(index + 1):
                        return True
                    chosen.pop()
                    needed[class_name] += 1
                return False

            if backtrack(0):
                return chosen
        return None

    def _active_entry(self, player_id: int) -> QueueEntry | None:
        return self.db.scalar(
            select(QueueEntry).where(
                QueueEntry.player_id == player_id,
                QueueEntry.queue_bucket == QueueBucket.ACTIVE.value,
            )
        )

    def _cycle(self) -> QueueCycle:
        cycle = self.db.scalar(
            select(QueueCycle).where(QueueCycle.queue_bucket == QueueBucket.ACTIVE.value)
        )
        if not cycle:
            cycle = QueueCycle(queue_bucket=QueueBucket.ACTIVE.value, map_candidates=[])
            self.db.add(cycle)
            self.db.flush()
        return cycle

    def _reconcile_ready_check(self) -> None:
        entries = self.get_entries(QueueBucket.ACTIVE.value)
        assignment = self.find_matchable_assignment(entries)
        cycle = self._cycle()
        now = datetime.now(timezone.utc)
        if assignment and not cycle.ready_check_expires_at:
            selected = {item.player_id for item in assignment}
            cycle.ready_check_token = str(uuid4())
            cycle.ready_check_expires_at = now + timedelta(seconds=45)
            cycle.announced_at = None
            for entry in entries:
                entry.ready = bool(
                    entry.player_id in selected
                    and entry.pre_ready_expires_at
                    and self._aware(entry.pre_ready_expires_at) > now
                )
            self.db.commit()
        elif not assignment and cycle.ready_check_expires_at:
            for entry in entries:
                entry.ready = False
            self._reset_cycle(cycle)
            self.db.commit()

    @staticmethod
    def _reset_cycle(cycle: QueueCycle) -> None:
        cycle.ready_check_token = None
        cycle.ready_check_expires_at = None
        cycle.announced_at = None

    def _vote_totals(self, cycle: QueueCycle) -> dict[str, int]:
        totals = dict.fromkeys(cycle.map_candidates, 0)
        votes = self.db.scalars(
            select(QueueMapVote).where(QueueMapVote.queue_cycle_id == cycle.id)
        )
        for vote in votes:
            totals[vote.map_name] = totals.get(vote.map_name, 0) + 1
        return totals

    @staticmethod
    def _primary(entry: QueueEntry) -> str:
        primary = next((pref.class_name for pref in entry.preferences if not pref.is_flex), None)
        return primary or entry.preferences[0].class_name

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _bucket_read(self, queue_bucket: str, entries: list[QueueEntry]) -> QueueBucketRead:
        players = []
        for entry in entries:
            primary = self._primary(entry)
            flex = [pref.class_name for pref in entry.preferences if pref.is_flex]
            players.append(
                QueuePlayerRead(
                    player_id=entry.player_id,
                    discord_username=entry.player.discord_username,
                    display_name=entry.player.display_name,
                    steam_name=entry.player.steam_name,
                    ready=entry.ready,
                    joined_at=entry.joined_at,
                    classes=[primary, *flex],
                    primary_class=primary,
                    flex_classes=flex,
                    pre_ready_expires_at=entry.pre_ready_expires_at,
                )
            )
        return QueueBucketRead(queue_bucket=queue_bucket, players=players, count=len(players))
