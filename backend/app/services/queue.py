from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import QUEUE_CLASS_LIMITS, QUEUE_CLASS_ORDER, QueueBucket
from app.models.entities import Player, QueueEntry, QueuePreference
from app.schemas.queue import QueueBucketRead, QueuePlayerRead, QueueStateResponse


class QueueAssignment(NamedTuple):
    player_id: int
    assigned_class: str


class QueueService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def join_queue(self, player: Player, classes: list[str], queue_bucket: str) -> QueueEntry:
        if not player.steam_connected:
            raise ValueError("A Steam connection is required before joining the queue.")

        existing = self.db.scalar(
            select(QueueEntry)
            .where(QueueEntry.player_id == player.id, QueueEntry.queue_bucket == queue_bucket)
            .options(joinedload(QueueEntry.preferences))
        )
        if existing:
            raise ValueError(f"Player is already queued in {queue_bucket}.")

        entry = QueueEntry(player_id=player.id, queue_bucket=queue_bucket, ready=False)
        entry.preferences = [QueuePreference(class_name=value) for value in classes]
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def leave_queue(self, player: Player, queue_bucket: str) -> None:
        entry = self.db.scalar(
            select(QueueEntry).where(
                QueueEntry.player_id == player.id,
                QueueEntry.queue_bucket == queue_bucket,
            )
        )
        if entry:
            self.db.delete(entry)
            self.db.commit()

    def set_ready(self, player: Player, ready: bool, queue_bucket: str = QueueBucket.ACTIVE.value) -> None:
        entry = self.db.scalar(
            select(QueueEntry).where(
                QueueEntry.player_id == player.id, QueueEntry.queue_bucket == queue_bucket
            )
        )
        if not entry:
            raise ValueError("Player is not in the queue.")
        entry.ready = ready
        self.db.commit()

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

    def build_queue_state(self) -> QueueStateResponse:
        active_entries = self.get_entries(QueueBucket.ACTIVE.value)
        next_entries = self.get_entries(QueueBucket.NEXT.value)
        assignment = self.find_matchable_assignment(active_entries)
        needed = self.needed_by_class(active_entries)
        return QueueStateResponse(
            active=self._bucket_read(QueueBucket.ACTIVE.value, active_entries),
            next=self._bucket_read(QueueBucket.NEXT.value, next_entries),
            matchable=assignment is not None,
            needed_by_class=needed,
        )

    def needed_by_class(self, entries: list[QueueEntry]) -> dict[str, int]:
        counts = Counter()
        for entry in entries:
            for pref in entry.preferences:
                counts[pref.class_name] += 1
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

                prefs = sorted(
                    (pref.class_name for pref in candidate_entries[index].preferences),
                    key=lambda item: needed[item],
                )
                for class_name in prefs:
                    if needed[class_name] <= 0:
                        continue
                    needed[class_name] -= 1
                    chosen.append(
                        QueueAssignment(
                            player_id=candidate_entries[index].player_id,
                            assigned_class=class_name,
                        )
                    )
                    if backtrack(index + 1):
                        return True
                    chosen.pop()
                    needed[class_name] += 1
                return False

            if backtrack(0):
                return chosen
        return None

    def _bucket_read(self, queue_bucket: str, entries: list[QueueEntry]) -> QueueBucketRead:
        players = [
            QueuePlayerRead(
                player_id=entry.player_id,
                discord_username=entry.player.discord_username,
                display_name=entry.player.display_name,
                steam_name=entry.player.steam_name,
                ready=entry.ready,
                joined_at=entry.joined_at,
                classes=[pref.class_name for pref in entry.preferences],
            )
            for entry in entries
        ]
        return QueueBucketRead(queue_bucket=queue_bucket, players=players, count=len(players))
