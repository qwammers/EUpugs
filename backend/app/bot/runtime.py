from __future__ import annotations

import asyncio
import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import tasks
from sqlalchemy import select

from app.core.config import get_settings
from app.core.constants import ELO_ROLE_RATINGS
from app.db.session import SessionLocal
from app.models.entities import Player
from app.services.match import MatchService
from app.services.queue import QueueService
from app.services.stats import StatsService

settings = get_settings()


class HostedPugsBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        guild = discord.Object(id=int(settings.discord_guild_id))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.lifecycle_loop.start()

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user}")

    async def close(self) -> None:
        self.lifecycle_loop.cancel()
        await super().close()

    @tasks.loop(seconds=10)
    async def lifecycle_loop(self) -> None:
        await asyncio.to_thread(self._process_queue)
        await self._reconcile_roles()

    @lifecycle_loop.before_loop
    async def before_lifecycle_loop(self) -> None:
        await self.wait_until_ready()

    def _process_queue(self) -> None:
        with SessionLocal() as db:
            service = QueueService(db, settings)
            state = service.build_queue_state()
            if state.phase == "ready_check":
                from app.models.entities import QueueCycle

                cycle = db.scalar(select(QueueCycle).where(QueueCycle.queue_bucket == "active"))
                if cycle and not cycle.announced_at:
                    cycle.announced_at = cycle.ready_check_expires_at
                    db.commit()
                    channel = self.get_channel(int(settings.discord_log_channel_id))
                    if channel:
                        asyncio.run_coroutine_threadsafe(
                            channel.send("Queue is full. Ready up within 45 seconds!"),
                            self.loop,
                        )
            service.process_ready_check()

    async def _reconcile_roles(self) -> None:
        guild = self.get_guild(int(settings.discord_guild_id))
        if not guild:
            return
        desired_by_role: dict[str, set[int]] = {}
        with SessionLocal() as db:
            QueueService(db, settings).allocate_waiting_setups()
            matches = MatchService(db, settings).get_active_matches()
            for match in matches:
                if not match.discord_setup:
                    continue
                for slot in match.slots:
                    role_id = settings.match_role_id(match.discord_setup, slot.team)
                    if role_id:
                        desired_by_role.setdefault(role_id, set()).add(
                            int(slot.player.discord_user_id)
                        )
            approved = [
                int(value)
                for value in db.scalars(
                    select(Player.discord_user_id).where(Player.etf2l_decision == "accepted")
                )
            ]
            skill_roles = {
                int(player.discord_user_id): player.elo_source_role_id
                for player in db.scalars(
                    select(Player).where(
                        Player.etf2l_decision == "accepted",
                        Player.elo_source_role_id.is_not(None),
                    )
                )
            }
        for role_id in {
            settings.match_role_id(setup, team)
            for setup in (1, 2)
            for team in ("RED", "BLU")
        } - {""}:
            role = guild.get_role(int(role_id))
            if role:
                current_role_members = {member.id for member in role.members}
                desired = desired_by_role.get(role_id, set())
                for user_id in desired | current_role_members:
                    member = guild.get_member(user_id)
                    if not member:
                        continue
                    if user_id in desired and role not in member.roles:
                        await member.add_roles(role, reason="PUG match access")
                    elif user_id not in desired and role in member.roles:
                        await member.remove_roles(role, reason="PUG match ended")
        if settings.discord_approved_role_id:
            role = guild.get_role(int(settings.discord_approved_role_id))
            if role:
                approved_ids = set(approved)
                for user_id in approved_ids | {member.id for member in role.members}:
                    member = guild.get_member(user_id)
                    if member and user_id in approved_ids and role not in member.roles:
                        await member.add_roles(role, reason="ETF2L screening accepted")
                    elif member and user_id not in approved_ids and role in member.roles:
                        await member.remove_roles(role, reason="ETF2L screening changed")
        for user_id, role_id in skill_roles.items():
            if not role_id:
                continue
            member = guild.get_member(user_id)
            role = guild.get_role(int(role_id))
            if member and role:
                old_roles = [
                    existing
                    for existing in member.roles
                    if str(existing.id) in ELO_ROLE_RATINGS and existing.id != role.id
                ]
                if old_roles:
                    await member.remove_roles(*old_roles, reason="Skill tier updated")
                if role not in member.roles:
                    await member.add_roles(role, reason="Runner-approved skill tier")

    async def on_message(self, message: discord.Message) -> None:
        if self.user and message.author.id == self.user.id:
            return
        if str(message.channel.id) != settings.discord_log_channel_id:
            return

        from app.clients.logstf_client import LogsTfClient

        client = LogsTfClient()
        parts = [message.content]
        for embed in message.embeds:
            parts.extend([embed.url or "", embed.title or "", embed.description or ""])
            for field in embed.fields:
                parts.extend([field.name, field.value])
        log_ids = client.parse_log_ids("\n".join(parts))
        if not log_ids:
            return

        for log_id in sorted(log_ids):
            try:
                await self._ingest_channel_log(log_id)
            except Exception:
                logging.exception("Failed to ingest logs.tf log %s from Discord", log_id)

    async def _ingest_channel_log(self, log_id: int) -> None:
        with SessionLocal() as db:
            matches = MatchService(db).get_active_matches()
            match = next((item for item in reversed(matches) if item.status == "awaiting_log"), None)
            stats = StatsService(db, settings)
            if match:
                await stats.attach_log_to_match(match, log_id)
            else:
                await stats.import_historical_log(
                    log_id,
                    source=f"discord_channel:{settings.discord_log_channel_id}",
                )


bot = HostedPugsBot()


def ensure_player(db, user: discord.User | discord.Member) -> Player | None:
    return db.scalar(select(Player).where(Player.discord_user_id == str(user.id)))


@bot.tree.command(name="queue", description="Join the active pug queue.")
@app_commands.describe(primary_class="Primary class", flex_classes="Optional comma-separated flex classes")
async def queue_command(
    interaction: discord.Interaction, primary_class: str, flex_classes: str = ""
) -> None:
    await interaction.response.defer(ephemeral=True)
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.followup.send("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db, settings).upsert_primary(
                player,
                primary_class.strip().lower(),
                [value.strip().lower() for value in flex_classes.split(",") if value.strip()],
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send("Joined the active queue.", ephemeral=True)


@bot.tree.command(name="leave", description="Leave the active pug queue.")
async def leave_command(interaction: discord.Interaction) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if player:
            QueueService(db, settings).leave_queue(player)
    await interaction.response.send_message("Left the active queue.", ephemeral=True)


@bot.tree.command(name="ready", description="Toggle your ready state in the active queue.")
@app_commands.describe(is_ready="Set true to ready up, false to undo")
async def ready_command(interaction: discord.Interaction, is_ready: bool) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.response.send_message("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db, settings).set_ready(player, is_ready)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
    await interaction.response.send_message(f"Ready set to {is_ready}.", ephemeral=True)


@bot.tree.command(name="pre-ready", description="Auto-ready for checks starting in the next 3 minutes.")
async def pre_ready_command(interaction: discord.Interaction) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.response.send_message("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db, settings).set_pre_ready(player)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
    await interaction.response.send_message("Pre-ready enabled for 3 minutes.", ephemeral=True)


@bot.tree.command(name="status", description="Show current queue and match status.")
async def status_command(interaction: discord.Interaction) -> None:
    with SessionLocal() as db:
        queue_state = QueueService(db, settings).build_queue_state()
        match = MatchService(db).get_current_match()
    summary = (
        f"Active queue: {queue_state.active.count}/12\n"
        f"Matchable: {'yes' if queue_state.matchable else 'no'}\n"
        f"Current match: {match.status if match else 'none'}"
    )
    await interaction.response.send_message(summary, ephemeral=True)


@bot.tree.command(name="profile", description="Show your tracked identity and aggregate stats.")
async def profile_command(interaction: discord.Interaction) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.response.send_message("Please log into the site first.", ephemeral=True)
            return
        aggregate = player.aggregate
        message = (
            f"Discord: {player.display_name or player.discord_username}\n"
            f"Steam: {player.steam_name or 'not linked'}\n"
            f"Matches: {aggregate.matches_played if aggregate else 0}\n"
            f"Wins: {aggregate.wins if aggregate else 0}"
            f"\nElo: {player.elo_rating if player.elo_rating is not None else 'unseeded'}"
        )
    await interaction.response.send_message(message, ephemeral=True)


admin_group = app_commands.Group(name="admin", description="Admin controls")


@admin_group.command(name="match", description="Start or update a match.")
@app_commands.describe(action="live, awaiting_log, complete, cancel", match_id="Existing match id")
async def admin_match_command(
    interaction: discord.Interaction,
    action: str,
    match_id: int | None = None,
) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player or not set(player.guild_role_ids).intersection(settings.admin_role_ids):
            await interaction.response.send_message("Admin role required.", ephemeral=True)
            return

        service = MatchService(db)
        if not match_id:
            await interaction.response.send_message("match_id is required.", ephemeral=True)
            return

        status_map = {
            "live": "live",
            "awaiting_log": "awaiting_log",
            "complete": "completed",
            "cancel": "cancelled",
        }
        if action not in status_map:
            await interaction.response.send_message("Unknown action.", ephemeral=True)
            return
        match = service.update_match_state(match_id, status_map[action])
    await interaction.response.send_message(f"Updated match #{match.id} to {match.status}.", ephemeral=True)


@admin_group.command(name="remove", description="Remove a player from the current queue.")
async def admin_remove_command(interaction: discord.Interaction, player_id: int) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player or not set(player.guild_role_ids).intersection(settings.admin_role_ids):
            await interaction.response.send_message("Admin role required.", ephemeral=True)
            return
        QueueService(db, settings).remove_player(player_id)
    await interaction.response.send_message(f"Removed player #{player_id}.", ephemeral=True)


@admin_group.command(name="sync-log", description="Attach a logs.tf log to the current pending match.")
async def admin_sync_log_command(interaction: discord.Interaction, log: str) -> None:
    await interaction.response.defer(ephemeral=True)
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player or not set(player.guild_role_ids).intersection(settings.admin_role_ids):
            await interaction.followup.send("Admin role required.", ephemeral=True)
            return
        match = MatchService(db).get_current_match()
        if not match:
            await interaction.followup.send("No current match.", ephemeral=True)
            return
        await StatsService(db, settings).attach_log_to_match(match, log)
    await interaction.followup.send("Attached log and ingested stats.", ephemeral=True)


bot.tree.add_command(admin_group, guild=discord.Object(id=int(settings.discord_guild_id)))


def run() -> None:
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    run()
