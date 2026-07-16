from __future__ import annotations

import asyncio
from typing import cast

import discord
from discord import app_commands
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Match, Player
from app.services.match import MatchService
from app.services.queue import QueueService
from app.services.stats import StatsService

settings = get_settings()


class HostedPugsBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        guild = discord.Object(id=int(settings.discord_guild_id))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user}")

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
@app_commands.describe(classes="Comma-separated classes, for example scout,soldier")
async def queue_command(interaction: discord.Interaction, classes: str) -> None:
    await interaction.response.defer(ephemeral=True)
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.followup.send("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db).join_queue(
                player,
                [value.strip().lower() for value in classes.split(",") if value.strip()],
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
@app_commands.describe(classes="Comma-separated classes, for example scout,soldier")
async def next_command(interaction: discord.Interaction, classes: str) -> None:
    with SessionLocal() as db:
        player = ensure_player(db, cast(discord.User, interaction.user))
        if not player:
            await interaction.response.send_message("Please log into the site first.", ephemeral=True)
            return
        try:
            QueueService(db).join_queue(
                player,
                [value.strip().lower() for value in classes.split(",") if value.strip()],
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
