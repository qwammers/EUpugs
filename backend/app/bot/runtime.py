from __future__ import annotations

import asyncio
from typing import cast

import discord
from discord import app_commands
from discord.ext import tasks
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import MatchSlot, Player
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
        self._match_role_members: set[int] = set()

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
            service = QueueService(db)
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
        desired: set[int] = set()
        with SessionLocal() as db:
            match = MatchService(db).get_current_match()
            if match and match.status == "live":
                desired = {
                    int(value)
                    for value in db.scalars(
                        select(Player.discord_user_id)
                        .join(MatchSlot, MatchSlot.player_id == Player.id)
                        .where(MatchSlot.match_id == match.id)
                    )
                }
            approved = [
                int(value)
                for value in db.scalars(
                    select(Player.discord_user_id).where(Player.etf2l_decision == "accepted")
                )
            ]
        if settings.discord_match_role_id:
            role = guild.get_role(int(settings.discord_match_role_id))
            if role:
                current_role_members = {member.id for member in role.members}
                for user_id in desired | self._match_role_members | current_role_members:
                    member = guild.get_member(user_id)
                    if not member:
                        continue
                    if user_id in desired and role not in member.roles:
                        await member.add_roles(role, reason="PUG match access")
                    elif user_id not in desired and role in member.roles:
                        await member.remove_roles(role, reason="PUG match ended")
                self._match_role_members = desired
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

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if str(message.channel.id) != settings.discord_log_channel_id:
            return

        from app.clients.logstf_client import LogsTfClient

        client = LogsTfClient()
        log_id = client.parse_log_id(message.content)
        if not log_id:
            return

        await asyncio.to_thread(self._attach_latest_pending_log, log_id)

    def _attach_latest_pending_log(self, log_id: int) -> None:
        with SessionLocal() as db:
            match = MatchService(db).get_current_match()
            if not match or match.status != "awaiting_log":
                return
            asyncio.run(StatsService(db, settings).attach_log_to_match(match, log_id))


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
            QueueService(db).join_queue(
                player,
                primary_class.strip().lower(),
                [value.strip().lower() for value in flex_classes.split(",") if value.strip()],
                "active",
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
            QueueService(db).leave_queue(player, "active")
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
            QueueService(db).set_ready(player, is_ready)
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
            QueueService(db).set_pre_ready(player)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
    await interaction.response.send_message("Pre-ready enabled for 3 minutes.", ephemeral=True)


@bot.tree.command(name="status", description="Show current queue and match status.")
async def status_command(interaction: discord.Interaction) -> None:
    with SessionLocal() as db:
        queue_state = QueueService(db).build_queue_state()
        match = MatchService(db).get_current_match()
    summary = (
        f"Active queue: {queue_state.active.count}/12\n"
        f"Next queue: {queue_state.next.count}\n"
        f"Matchable: {'yes' if queue_state.matchable else 'no'}\n"
        f"Current match: {match.status if match else 'none'}"
    )
    await interaction.response.send_message(summary, ephemeral=True)


@bot.tree.command(name="next", description="Join the next-match opt-in queue.")
@app_commands.describe(primary_class="Primary class", flex_classes="Optional comma-separated flex classes")
async def next_command(
    interaction: discord.Interaction, primary_class: str, flex_classes: str = ""
) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.response.send_message("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db).join_queue(
                player,
                primary_class.strip().lower(),
                [value.strip().lower() for value in flex_classes.split(",") if value.strip()],
                "next",
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
    await interaction.response.send_message("Joined the next-match queue.", ephemeral=True)


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
        )
    await interaction.response.send_message(message, ephemeral=True)


admin_group = app_commands.Group(name="admin", description="Admin controls")


@admin_group.command(name="match", description="Create or update a match.")
@app_commands.describe(action="create, live, awaiting_log, complete, cancel", match_id="Existing match id")
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
        if action == "create":
            try:
                match = service.create_match_from_active_queue(player)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await interaction.response.send_message(f"Created match #{match.id}.", ephemeral=True)
            return

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
