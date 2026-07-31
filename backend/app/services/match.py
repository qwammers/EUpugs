from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.constants import MatchStatus
from app.models.entities import Match, MatchSlot, MatchSubstitution, Player, PugRatingEvent, QueueEntry
from app.schemas.match import MatchRead, MatchSlotRead, MatchSubstitutionRead
from app.services.elo import PugRatingService
from app.services.queue import QueueService


class MatchService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def start_match(self, match_id: int) -> Match:
        match = self.get_match(match_id)
        if not match:
            raise ValueError("Match not found.")
        QueueService(self.db, self.settings).allocate_waiting_setups()
        self.db.refresh(match)
        if match.status != MatchStatus.READY.value:
            raise ValueError("Only a ready match can be started.")
        if match.discord_setup is None:
            raise ValueError("No Discord team voice setup is currently available.")
        match.status = MatchStatus.LIVE.value
        self.db.commit()
        return self.get_match(match_id)

    def substitute(
        self, match_id: int, outgoing_player_id: int, incoming_player_id: int, admin: Player
    ) -> Match:
        match = self.get_match(match_id)
        if not match or match.status != MatchStatus.LIVE.value:
            raise ValueError("Substitutions are only available for a live match.")
        slot = next((item for item in match.slots if item.player_id == outgoing_player_id), None)
        if not slot:
            raise ValueError("Outgoing player is not in this match.")
        forming = QueueService(self.db, self.settings).ensure_forming_match()
        queued = self.db.scalar(select(QueueEntry).where(
            QueueEntry.player_id == incoming_player_id, QueueEntry.match_id == forming.id
        ))
        incoming = self.db.get(Player, incoming_player_id)
        if not queued or not incoming:
            raise ValueError("Incoming player must be in the current queue.")
        self.db.add(MatchSubstitution(
            match_id=match.id,
            outgoing_player_id=outgoing_player_id,
            incoming_player_id=incoming_player_id,
            created_by_player_id=admin.id,
            team=slot.team,
            assigned_class=slot.assigned_class,
        ))
        slot.player_id = incoming_player_id
        slot.rating_at_lock = incoming.pug_rating or 0
        slot.elo_at_lock = incoming.pug_rating or 0
        self.db.delete(queued)
        self.db.commit()
        return self.get_match(match_id)

    def get_current_match(self) -> Match | None:
        return self.db.execute(
            self._query().where(
                Match.status.in_([
                    MatchStatus.READY.value,
                    MatchStatus.LIVE.value,
                    MatchStatus.AWAITING_LOG.value,
                ])
            ).order_by(desc(Match.created_at))
        ).unique().scalars().first()

    def get_active_matches(self) -> list[Match]:
        return list(self.db.execute(
            self._query().where(Match.status.in_([
                MatchStatus.READY.value,
                MatchStatus.LIVE.value,
                MatchStatus.AWAITING_LOG.value,
            ])).order_by(Match.created_at)
        ).unique().scalars())

    def get_recent_matches(self, limit: int = 100) -> list[Match]:
        return list(self.db.execute(
            self._query().where(Match.status.in_([
                MatchStatus.COMPLETED.value, MatchStatus.CANCELLED.value
            ])).order_by(desc(Match.created_at)).limit(limit)
        ).unique().scalars())

    def get_match(self, match_id: int) -> Match | None:
        return self.db.execute(
            self._query().where(Match.id == match_id)
        ).unique().scalars().first()

    def update_match_state(
        self,
        match_id: int,
        status: str,
        winner: str | None = None,
        score_red: int | None = None,
        score_blu: int | None = None,
    ) -> Match:
        if status == MatchStatus.LIVE.value:
            return self.start_match(match_id)
        match = self.get_match(match_id)
        if not match:
            raise ValueError("Match not found.")
        match.status = status
        match.winner = winner or match.winner
        match.score_red = score_red if score_red is not None else match.score_red
        match.score_blu = score_blu if score_blu is not None else match.score_blu
        if status == MatchStatus.COMPLETED.value:
            if match.winner is None and match.score_red is not None and match.score_blu is not None:
                match.winner = (
                    "RED" if match.score_red > match.score_blu
                    else "BLU" if match.score_blu > match.score_red
                    else "DRAW"
                )
            match.completed_at = datetime.now(timezone.utc)
            match.discord_setup = None
        elif status == MatchStatus.CANCELLED.value:
            match.discord_setup = None
        self.db.commit()
        PugRatingService(self.db).settle_match(match)
        QueueService(self.db, self.settings).allocate_waiting_setups()
        return self.get_match(match_id)

    def serialize(self, match: Match, viewer: Player | None = None) -> MatchRead:
        events = {
            event.player_id: event
            for event in self.db.scalars(
                select(PugRatingEvent).where(PugRatingEvent.match_id == match.id)
            )
        }
        voice_url = None
        if viewer and match.discord_setup:
            slot = next((item for item in match.slots if item.player_id == viewer.id), None)
            if slot:
                channel_id = self.settings.match_voice_channel_id(match.discord_setup, slot.team)
                if channel_id:
                    voice_url = (
                        f"https://discord.com/channels/{self.settings.discord_guild_id}/{channel_id}"
                    )
        averages = {}
        for team in ("RED", "BLU"):
            team_slots = [slot for slot in match.slots if slot.team == team]
            if team_slots:
                averages[team] = sum(
                    slot.rating_at_lock or slot.elo_at_lock for slot in team_slots
                ) / len(team_slots)
        return MatchRead(
            id=match.id,
            status=match.status,
            map_name=match.map_name,
            map_candidates=match.map_candidates,
            winner=match.winner,
            score_red=match.score_red,
            score_blu=match.score_blu,
            ready_check_expires_at=match.ready_check_expires_at,
            created_at=match.created_at,
            completed_at=match.completed_at,
            teams_locked_at=match.teams_locked_at,
            discord_setup=match.discord_setup,
            team_average_rating=averages,
            team_average_elo=averages,
            log_ids=[log.log_id for log in match.logs],
            voice_channel_url=voice_url,
            slots=[
                MatchSlotRead(
                    player_id=slot.player_id,
                    display_name=slot.player.display_name,
                    discord_username=slot.player.discord_username,
                    assigned_class=slot.assigned_class,
                    team=slot.team,
                    slot_order=slot.slot_order,
                    rating_at_lock=slot.rating_at_lock or slot.elo_at_lock,
                    rating_delta=(
                        events[slot.player_id].delta if slot.player_id in events else None
                    ),
                    rating_result_component=(
                        events[slot.player_id].result_component
                        if slot.player_id in events
                        else None
                    ),
                    rating_impact_modifier=(
                        events[slot.player_id].impact_modifier
                        if slot.player_id in events
                        else None
                    ),
                    rating_dominant_class=(
                        events[slot.player_id].dominant_class
                        if slot.player_id in events
                        else None
                    ),
                    rating_damage_per_minute=(
                        events[slot.player_id].damage_per_minute
                        if slot.player_id in events
                        else None
                    ),
                    rating_kills_per_minute=(
                        events[slot.player_id].kills_per_minute
                        if slot.player_id in events
                        else None
                    ),
                    rating_dpm_percentile=(
                        events[slot.player_id].dpm_percentile
                        if slot.player_id in events
                        else None
                    ),
                    rating_kpm_percentile=(
                        events[slot.player_id].kpm_percentile
                        if slot.player_id in events
                        else None
                    ),
                    rating_benchmark_samples=(
                        events[slot.player_id].benchmark_sample_count
                        if slot.player_id in events
                        else None
                    ),
                    rating_formula_version=(
                        events[slot.player_id].formula_version
                        if slot.player_id in events
                        else None
                    ),
                    elo_at_lock=slot.rating_at_lock or slot.elo_at_lock,
                    elo_delta=(
                        events[slot.player_id].delta if slot.player_id in events else None
                    ),
                )
                for slot in sorted(match.slots, key=lambda item: item.slot_order)
            ],
            substitutions=[
                MatchSubstitutionRead(
                    outgoing_player_id=item.outgoing_player_id,
                    outgoing_name=item.outgoing_player.display_name or item.outgoing_player.discord_username,
                    incoming_player_id=item.incoming_player_id,
                    incoming_name=item.incoming_player.display_name or item.incoming_player.discord_username,
                    assigned_class=item.assigned_class,
                    team=item.team,
                    created_at=item.created_at,
                )
                for item in sorted(match.substitutions, key=lambda value: value.created_at)
            ],
        )

    @staticmethod
    def _query():
        return select(Match).options(
            joinedload(Match.slots).joinedload(MatchSlot.player),
            joinedload(Match.logs),
            joinedload(Match.substitutions).joinedload(MatchSubstitution.outgoing_player),
            joinedload(Match.substitutions).joinedload(MatchSubstitution.incoming_player),
        )
