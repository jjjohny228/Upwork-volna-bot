"""Per-user parsing-schedule gate.

Pure decision function: given a user's manual pause switch and optional quiet-hours
window (a daily local-time range in the user's IANA timezone), decide whether the
poller may parse that user's mailboxes right now.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from upwork_bot.db.models import User


def is_parsing_allowed(user: User, now_utc: datetime) -> bool:
    """Return whether the poller may parse this user's mailboxes right now.

    `now_utc` must be a timezone-aware UTC datetime — a naive value would make
    `.astimezone` assume system-local time and corrupt the window check.
    """
    if not user.parsing_active:
        return False
    if not (user.quiet_hours_enabled and user.timezone and user.quiet_start and user.quiet_end):
        return True

    local = now_utc.astimezone(ZoneInfo(user.timezone)).time()
    start, end = user.quiet_start, user.quiet_end
    # Same-day window: start <= local < end. Window wraps past midnight otherwise.
    in_quiet = start <= local < end if start <= end else local >= start or local < end
    return not in_quiet
