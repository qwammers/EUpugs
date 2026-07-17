from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import discord

from app.clients.logstf_client import LogsTfClient
from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.services.stats import StatsService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import historical logs.tf stats.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Text file containing log IDs or logs.tf URLs.")
    source.add_argument("--channel-id", type=int, help="Discord channel whose full history is scanned.")
    parser.add_argument("--limit", type=int, default=None, help="Optional newest-message limit.")
    return parser.parse_args()


def ids_from_file(path: Path) -> set[int]:
    return LogsTfClient().parse_log_ids(path.read_text(encoding="utf-8"))


async def ids_from_discord(channel_id: int, limit: int | None) -> set[int]:
    settings = get_settings()
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    found: set[int] = set()

    @client.event
    async def on_ready() -> None:
        try:
            channel = await client.fetch_channel(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                raise RuntimeError("The configured channel does not contain messages.")
            parser = LogsTfClient()
            async for message in channel.history(limit=limit, oldest_first=True):
                parts = [message.content]
                for embed in message.embeds:
                    parts.extend([embed.url or "", embed.title or "", embed.description or ""])
                    for field in embed.fields:
                        parts.extend([field.name, field.value])
                found.update(parser.parse_log_ids("\n".join(parts)))
        finally:
            await client.close()

    await client.start(settings.discord_bot_token)
    return found


async def import_logs(log_ids: set[int], source: str) -> None:
    imported = skipped = failed = 0
    for index, log_id in enumerate(sorted(log_ids), start=1):
        try:
            with SessionLocal() as db:
                created = await StatsService(db, get_settings()).import_historical_log(log_id, source)
            imported += int(created)
            skipped += int(not created)
            print(f"[{index}/{len(log_ids)}] {'imported' if created else 'skipped'} {log_id}")
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(log_ids)}] failed {log_id}: {exc}")
    print(f"Finished: imported={imported} skipped={skipped} failed={failed}")


async def main() -> None:
    args = parse_args()
    init_db()
    if args.file:
        log_ids = ids_from_file(args.file)
        source = f"file:{args.file.name}"
    else:
        log_ids = await ids_from_discord(args.channel_id, args.limit)
        source = f"discord_channel:{args.channel_id}"
    print(f"Found {len(log_ids)} unique logs.tf logs")
    await import_logs(log_ids, source)


if __name__ == "__main__":
    asyncio.run(main())
