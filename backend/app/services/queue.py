from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import NamedTuple
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.constants import (
    ELO_ROLE_RATINGS,
    PUG_MAP_POOL,
    QUEUE_CLASS_LIMITS,
    QUEUE_CLASS_ORDER,
    MatchStatus,
    QueueBucket,
)
from app.models.entities import Match, MatchSlot, Player, QueueCycle, QueueEntry, QueueMapVote, QueuePreference
from app.schemas.queue import QueueBucketRead, QueuePlayerRead, QueueStateResponse


class QueueAssignment(NamedTuple):
    player_id: int
    assigned_class: str


class QueueService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings

    def seed_elo_from_roles(self, player: Player) -> None:
        if player.elo_rating is not None:
            return
        candidates = [
            (rating, role_id)
            for role_id, rating in ELO_ROLE_RATINGS.items()
            if role_id in player.guild_role_ids
        ]
        if candidates:
            rating, role_id = max(candidates)
            player.elo_rating = rating
            player.elo_seed_source = "discord_role"
            player.elo_source_role_id = role_id
            player.elo_seeded_at = datetime.now(timezone.utc)
            self.db.commit()

    def blocked_classes(self, player: Player) -> list[str]:
        restrictions = self.settings.class_restrictions if self.settings else {}
        return sorted({
            class_name
            for role_id in player.guild_role_ids
            for class_name in restrictions.get(str(role_id), [])
        })

    def ensure_forming_match(self, creator_id: int | None = None) -> Match:
        match = self.db.scalar(
            select(Match)
            .where(Match.status.in_([MatchStatus.FORMING.value, MatchStatus.READY_CHECK.value]))
            .order_by(desc(Match.created_at))
        )
        if match:
            if not match.map_candidates:
                match.map_candidates = random.sample(list(PUG_MAP_POOL), 3)
                self.db.commit()
            self._ensure_cycle(match)
            return match
        match = Match(
            status=MatchStatus.FORMING.value,
            created_by_player_id=creator_id,
            map_candidates=random.sample(list(PUG_MAP_POOL), 3),
        )
        self.db.add(match)
        self.db.flush()
        self._ensure_cycle(match)
        self.db.commit()
        return match

    def upsert_primary(
        self, player: Player, primary_class: str, flex_classes: list[str] | None = None
    ) -> QueueEntry:
        if not player.steam_connected:
            raise ValueError("A Steam connection is required before joining the queue.")
        self.seed_elo_from_roles(player)
        if player.elo_rating is None:
            raise ValueError("A runner must approve your skill tier before you can queue.")
        flex_classes = [item for item in dict.fromkeys(flex_classes or []) if item != primary_class]
        selected = [primary_class, *flex_classes]
        restricted = set(self.blocked_classes(player)).intersection(selected)
        if restricted:
            raise ValueError(f"Your Discord roles restrict: {', '.join(sorted(restricted))}.")
        if any(item not in QUEUE_CLASS_ORDER for item in selected):
            raise ValueError("Invalid class selection.")

        match = self.ensure_forming_match(player.id)
        entry = self.db.scalar(
            select(QueueEntry)
            .where(QueueEntry.player_id == player.id, QueueEntry.match_id == match.id)
            .options(joinedload(QueueEntry.preferences))
        )
        if not entry:
            entry = QueueEntry(
                player_id=player.id,
                match_id=match.id,
                queue_bucket=QueueBucket.ACTIVE.value,
                ready=False,
            )
            self.db.add(entry)
        entry.preferences.clear()
        entry.preferences.extend([
            QueuePreference(class_name=primary_class, is_flex=False),
            *[QueuePreference(class_name=item, is_flex=True) for item in flex_classes],
        ])
        entry.ready = False
        if match.status == MatchStatus.READY_CHECK.value:
            cycle = self._ensure_cycle(match)
            self._reset_cycle(cycle)
            match.status = MatchStatus.FORMING.value
            for queued in self.get_entries(match.id):
                queued.ready = False
        self.db.commit()
        self._reconcile_ready_check(match)
        return entry

    def join_queue(
        self,
        player: Player,
        primary_class: str | list[str],
        flex_classes: list[str] | str | None = None,
        queue_bucket: str = "active",
    ) -> QueueEntry:
        _ = queue_bucket
        if isinstance(primary_class, list):
            values = primary_class
            primary_class = values[0] if values else ""
            flex_classes = values[1:]
        return self.upsert_primary(
            player, primary_class, flex_classes if isinstance(flex_classes, list) else []
        )

    def update_flex(self, player: Player, flex_classes: list[str]) -> None:
        match = self.ensure_forming_match()
        entry = self._entry(player.id, match.id)
        if not entry:
            raise ValueError("Select a primary class before setting flex classes.")
        self.upsert_primary(player, self._primary(entry), flex_classes)

    def leave_queue(self, player: Player, queue_bucket: str = "active") -> None:
        _ = queue_bucket
        self.remove_player(player.id)

    def remove_player(self, player_id: int) -> None:
        match = self.ensure_forming_match()
        entry = self._entry(player_id, match.id)
        if entry:
            self.db.delete(entry)
            if match.status == MatchStatus.READY_CHECK.value:
                cycle = self._ensure_cycle(match)
                self._reset_cycle(cycle)
                match.status = MatchStatus.FORMING.value
                for queued in self.get_entries(match.id):
                    queued.ready = False
            self.db.commit()
            self._reconcile_ready_check(match)

    def set_pre_ready(self, player: Player) -> None:
        match = self.ensure_forming_match()
        entry = self._entry(player.id, match.id)
        if not entry:
            raise ValueError("Player is not queued.")
        entry.pre_ready_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)
        cycle = self._ensure_cycle(match)
        if player.id in (cycle.selected_player_ids or []):
            entry.ready = True
        self.db.commit()
        self._lock_if_all_ready(match)

    def set_ready(self, player: Player, ready: bool) -> None:
        match = self.ensure_forming_match()
        cycle = self._ensure_cycle(match)
        entry = self._entry(player.id, match.id)
        if not entry or player.id not in (cycle.selected_player_ids or []):
            raise ValueError("You are not selected for the active ready check.")
        if not cycle.ready_check_expires_at or self._aware(cycle.ready_check_expires_at) <= datetime.now(timezone.utc):
            raise ValueError("There is no active ready check.")
        entry.ready = ready
        self.db.commit()
        self._lock_if_all_ready(match)

    def vote_map(self, player: Player, map_name: str) -> None:
        match = self.ensure_forming_match()
        if not self._entry(player.id, match.id):
            raise ValueError("Only queued players can vote.")
        if map_name not in match.map_candidates:
            raise ValueError("That map is not a current candidate.")
        cycle = self._ensure_cycle(match)
        vote = self.db.scalar(
            select(QueueMapVote).where(
                QueueMapVote.queue_cycle_id == cycle.id, QueueMapVote.player_id == player.id
            )
        )
        if vote:
            vote.map_name = map_name
            vote.match_id = match.id
        else:
            self.db.add(QueueMapVote(
                queue_cycle_id=cycle.id, match_id=match.id, player_id=player.id, map_name=map_name
            ))
        self.db.commit()

    def process_ready_check(self) -> list[int]:
        match = self.ensure_forming_match()
        cycle = self._ensure_cycle(match)
        now = datetime.now(timezone.utc)
        if not cycle.ready_check_expires_at or self._aware(cycle.ready_check_expires_at) > now:
            return []
        selected = set(cycle.selected_player_ids or [])
        entries = self.get_entries(match.id)
        removed = [entry.player_id for entry in entries if entry.player_id in selected and not entry.ready]
        for entry in entries:
            if entry.player_id in removed:
                self.db.delete(entry)
            else:
                entry.ready = False
        self._reset_cycle(cycle)
        match.status = MatchStatus.FORMING.value
        self.db.commit()
        self._reconcile_ready_check(match)
        return removed

    def build_queue_state(self, player: Player | None = None) -> QueueStateResponse:
        match = self.ensure_forming_match(player.id if player else None)
        self._reconcile_ready_check(match)
        if match.status == MatchStatus.READY.value:
            match = self.ensure_forming_match(player.id if player else None)
        entries = self.get_entries(match.id)
        cycle = self._ensure_cycle(match)
        bucket = self._bucket_read(entries)
        active = match.status == MatchStatus.READY_CHECK.value
        return QueueStateResponse(
            match_id=match.id,
            queue=bucket,
            active=bucket,
            matchable=self.find_matchable_assignment(entries) is not None,
            needed_by_class=self.needed_by_class(entries),
            phase=match.status,
            ready_check_id=cycle.ready_check_token if active else None,
            ready_check_expires_at=cycle.ready_check_expires_at if active else None,
            map_candidates=match.map_candidates,
            map_votes=self._vote_totals(match.id),
            blocked_classes=self.blocked_classes(player) if player else [],
        )

    def get_entries(self, match_id: int | str) -> list[QueueEntry]:
        if isinstance(match_id, str):
            match_id = self.ensure_forming_match().id
        return list(self.db.execute(
            select(QueueEntry)
            .where(QueueEntry.match_id == match_id)
            .options(joinedload(QueueEntry.player), joinedload(QueueEntry.preferences))
            .order_by(QueueEntry.joined_at.asc())
        ).unique().scalars())

    def needed_by_class(self, entries: list[QueueEntry]) -> dict[str, int]:
        counts = Counter(self._primary(entry) for entry in entries)
        return {name: max(QUEUE_CLASS_LIMITS[name] - counts[name], 0) for name in QUEUE_CLASS_ORDER}

    def find_matchable_assignment(self, entries: list[QueueEntry]) -> list[QueueAssignment] | None:
        if len(entries) < 12:
            return None
        for candidates in combinations(entries, 12):
            needed = dict(QUEUE_CLASS_LIMITS)
            chosen: list[QueueAssignment] = []

            def backtrack(index: int) -> bool:
                if index == len(candidates):
                    return all(value == 0 for value in needed.values())
                entry = candidates[index]
                options = [self._primary(entry), *[
                    pref.class_name for pref in entry.preferences if pref.is_flex
                ]]
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

    def _reconcile_ready_check(self, match: Match) -> None:
        entries = self.get_entries(match.id)
        assignment = self.find_matchable_assignment(entries)
        cycle = self._ensure_cycle(match)
        if assignment and not cycle.ready_check_expires_at:
            now = datetime.now(timezone.utc)
            cycle.ready_check_token = str(uuid4())
            cycle.ready_check_expires_at = now + timedelta(seconds=45)
            cycle.selected_player_ids = [item.player_id for item in assignment]
            cycle.announced_at = None
            match.status = MatchStatus.READY_CHECK.value
            for entry in entries:
                entry.ready = bool(
                    entry.player_id in cycle.selected_player_ids
                    and entry.pre_ready_expires_at
                    and self._aware(entry.pre_ready_expires_at) > now
                )
            self.db.commit()
            self._lock_if_all_ready(match)
        elif not assignment and cycle.ready_check_expires_at:
            self._reset_cycle(cycle)
            match.status = MatchStatus.FORMING.value
            for entry in entries:
                entry.ready = False
            self.db.commit()

    def _lock_if_all_ready(self, match: Match) -> None:
        cycle = self._ensure_cycle(match)
        selected = set(cycle.selected_player_ids or [])
        if not selected:
            return
        entries = self.get_entries(match.id)
        selected_entries = [entry for entry in entries if entry.player_id in selected]
        if len(selected_entries) != 12 or any(not entry.ready for entry in selected_entries):
            return
        assignments = self.find_matchable_assignment(selected_entries)
        if not assignments:
            return
        teams = self._balanced_teams(assignments, selected_entries)
        for order, assignment in enumerate(assignments):
            player = next(entry.player for entry in selected_entries if entry.player_id == assignment.player_id)
            self.db.add(MatchSlot(
                match_id=match.id,
                player_id=assignment.player_id,
                team=teams[assignment.player_id],
                assigned_class=assignment.assigned_class,
                slot_order=order,
                elo_at_lock=player.elo_rating or 0,
            ))
        match.map_name = self._winning_map(match)
        match.status = MatchStatus.READY.value
        match.teams_locked_at = datetime.now(timezone.utc)
        match.ready_check_expires_at = None
        match.discord_setup = self._free_discord_setup()
        for entry in selected_entries:
            self.db.delete(entry)
        new_match = Match(status=MatchStatus.FORMING.value, map_candidates=random.sample(list(PUG_MAP_POOL), 3))
        self.db.add(new_match)
        self.db.flush()
        for entry in entries:
            if entry.player_id not in selected:
                entry.match_id = new_match.id
                entry.ready = False
        self.db.execute(delete(QueueMapVote).where(QueueMapVote.queue_cycle_id == cycle.id))
        self._reset_cycle(cycle)
        cycle.match_id = new_match.id
        self.db.commit()

    def allocate_waiting_setups(self) -> None:
        occupied = set(self.db.scalars(
            select(Match.discord_setup).where(
                Match.discord_setup.is_not(None),
                Match.status.in_([MatchStatus.READY.value, MatchStatus.LIVE.value, MatchStatus.AWAITING_LOG.value]),
            )
        ))
        for match in self.db.scalars(
            select(Match).where(Match.status == MatchStatus.READY.value, Match.discord_setup.is_(None))
            .order_by(Match.created_at)
        ):
            free = next((value for value in (1, 2) if value not in occupied), None)
            if not free:
                break
            match.discord_setup = free
            occupied.add(free)
        self.db.commit()

    def _balanced_teams(
        self, assignments: list[QueueAssignment], entries: list[QueueEntry]
    ) -> dict[int, str]:
        ratings = {entry.player_id: entry.player.elo_rating or 0 for entry in entries}
        by_class: dict[str, list[int]] = {name: [] for name in QUEUE_CLASS_ORDER}
        for assignment in assignments:
            by_class[assignment.assigned_class].append(assignment.player_id)
        choices = [
            list(combinations(sorted(by_class[name]), QUEUE_CLASS_LIMITS[name] // 2))
            for name in QUEUE_CLASS_ORDER
        ]
        best: tuple[float, tuple[int, ...]] | None = None
        for scout in choices[0]:
            for soldier in choices[1]:
                for demo in choices[2]:
                    for medic in choices[3]:
                        red = tuple(sorted((*scout, *soldier, *demo, *medic)))
                        blue = tuple(sorted(set(ratings) - set(red)))
                        difference = abs(
                            sum(ratings[value] for value in red) / 6
                            - sum(ratings[value] for value in blue) / 6
                        )
                        candidate = (difference, red)
                        if best is None or candidate < best:
                            best = candidate
        red_ids = set(best[1] if best else ())
        return {player_id: ("RED" if player_id in red_ids else "BLU") for player_id in ratings}

    def _free_discord_setup(self) -> int | None:
        occupied = set(self.db.scalars(select(Match.discord_setup).where(
            Match.discord_setup.is_not(None),
            Match.status.in_([MatchStatus.READY.value, MatchStatus.LIVE.value, MatchStatus.AWAITING_LOG.value]),
        )))
        return next((value for value in (1, 2) if value not in occupied), None)

    def _ensure_cycle(self, match: Match) -> QueueCycle:
        cycle = self.db.scalar(select(QueueCycle).where(QueueCycle.queue_bucket == "active"))
        if not cycle:
            cycle = QueueCycle(queue_bucket="active", match_id=match.id, selected_player_ids=[])
            self.db.add(cycle)
            self.db.flush()
        elif cycle.match_id != match.id and match.status in {
            MatchStatus.FORMING.value, MatchStatus.READY_CHECK.value
        }:
            cycle.match_id = match.id
        return cycle

    def _entry(self, player_id: int, match_id: int) -> QueueEntry | None:
        return self.db.scalar(
            select(QueueEntry)
            .where(QueueEntry.player_id == player_id, QueueEntry.match_id == match_id)
            .options(joinedload(QueueEntry.preferences))
        )

    def _vote_totals(self, match_id: int) -> dict[str, int]:
        match = self.db.get(Match, match_id)
        totals = dict.fromkeys(match.map_candidates if match else [], 0)
        for vote in self.db.scalars(select(QueueMapVote).where(QueueMapVote.match_id == match_id)):
            totals[vote.map_name] = totals.get(vote.map_name, 0) + 1
        return totals

    def _winning_map(self, match: Match) -> str:
        totals = self._vote_totals(match.id)
        return max(match.map_candidates, key=lambda item: totals.get(item, 0))

    @staticmethod
    def _reset_cycle(cycle: QueueCycle) -> None:
        cycle.ready_check_token = None
        cycle.ready_check_expires_at = None
        cycle.announced_at = None
        cycle.selected_player_ids = []

    @staticmethod
    def _primary(entry: QueueEntry) -> str:
        return next((pref.class_name for pref in entry.preferences if not pref.is_flex), entry.preferences[0].class_name)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _bucket_read(self, entries: list[QueueEntry]) -> QueueBucketRead:
        players = []
        for entry in entries:
            primary = self._primary(entry)
            flex = [pref.class_name for pref in entry.preferences if pref.is_flex]
            players.append(QueuePlayerRead(
                player_id=entry.player_id,
                discord_username=entry.player.discord_username,
                display_name=entry.player.display_name,
                steam_name=entry.player.steam_name,
                elo_rating=entry.player.elo_rating,
                ready=entry.ready,
                joined_at=entry.joined_at,
                primary_class=primary,
                flex_classes=flex,
                classes=[primary, *flex],
                pre_ready_expires_at=entry.pre_ready_expires_at,
            ))
        return QueueBucketRead(players=players, count=len(players))
