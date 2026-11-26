"""pg_dump / pg_restore wrappers shared by the Settings buttons and the daily job."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from upwork_bot.config import get_settings


class BackupError(RuntimeError):
    """pg_dump/pg_restore missing or exited non-zero; message is user-facing."""


def _pg_conn_args(parsed: ParseResult) -> list[str]:
    return [
        f"--host={parsed.hostname}",
        f"--port={parsed.port or 5432}",
        f"--username={parsed.username}",
        f"--dbname={(parsed.path or '').lstrip('/')}",
    ]


def _pg_env(parsed: ParseResult) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": parsed.password or ""}


def backup_filename(now: datetime | None = None) -> str:
    return f"upwork_backup_{(now or datetime.now(UTC)):%Y%m%d_%H%M%S}.dump"


async def _run(tool: str, *args: str) -> None:
    parsed = urlparse(get_settings().database_url)
    try:
        proc = await asyncio.create_subprocess_exec(
            tool,
            *_pg_conn_args(parsed),
            *args,
            env=_pg_env(parsed),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise BackupError(f"{tool} is not installed in this container.") from exc

    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise BackupError(stderr.decode(errors="replace")[:3500])


async def dump_database(dest: Path) -> None:
    """Write a custom-format pg_dump of the whole DB to ``dest``."""
    await _run("pg_dump", "--format=custom", f"--file={dest}")


async def restore_database(src: Path) -> None:
    """Replace the whole DB with the dump at ``src`` (atomic: rolls back on error)."""
    await _run(
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--single-transaction",
        str(src),
    )
