"""Daily pg_dump sent to the configured admin chats."""

import asyncio
import html
import logging
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from upwork_bot.config import get_settings
from upwork_bot.db.backup import BackupError, backup_filename, dump_database

logger = logging.getLogger(__name__)


def seconds_until_next_run(now: datetime, hour_utc: int) -> float:
    """Seconds from ``now`` (tz-aware) until the next ``hour_utc``:00 UTC."""
    now = now.astimezone(UTC)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def send_backup_to_admins(bot: Bot, chat_ids: list[int]) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / backup_filename()
        try:
            await dump_database(dump_path)
        except BackupError as exc:
            logger.exception("Daily backup failed")
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id, f"❌ Daily backup failed:\n<pre>{html.escape(str(exc))}</pre>"
                    )
                except Exception:
                    logger.exception("Could not notify %s about failed backup", chat_id)
            return

        caption = f"📦 Daily Postgres backup ({datetime.now(UTC):%Y-%m-%d})"
        for chat_id in chat_ids:
            try:
                await bot.send_document(chat_id, FSInputFile(dump_path), caption=caption)
            except Exception:
                logger.exception("Could not send daily backup to %s", chat_id)


async def run_daily_backup(bot: Bot) -> None:
    settings = get_settings()
    if not settings.daily_backup_enabled:
        logger.info("Daily backup disabled")
        return
    while True:
        delay = seconds_until_next_run(datetime.now(UTC), settings.backup_hour_utc)
        logger.info("Next daily backup in %.0f s", delay)
        await asyncio.sleep(delay)
        try:
            await send_backup_to_admins(bot, settings.backup_recipients)
        except Exception:
            logger.exception("Daily backup crashed")
