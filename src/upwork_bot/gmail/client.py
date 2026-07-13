"""Parse Vollna job-alert emails from Gmail over IMAP.

Vollna sends one email per matching job from `info@vollna.com`. The body is a
single quoted-printable `text/html` part with labelled fields. The dedup key is
the Vollna `pid` embedded in the tracking link (same invariant as the old RSS
source).
"""

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PID_RE = re.compile(r"pid=(\d+)")
_UPWORK_ID_RE = re.compile(r"~(\d{15,})")
_SUBJECT_PREFIX = "New Job:"
_RATE_LABELS = ("Hourly Rate", "Fixed Price")


@dataclass
class JobEmail:
    external_pid: str
    title: str
    description: str
    upwork_link: str
    rate: str | None = None
    pub_date: datetime | None = None


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _get_html(msg: Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return ""


def _extract_rate(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all(["strong", "b"]):
        label = tag.get_text(strip=True).rstrip(":")
        if label in _RATE_LABELS:
            sibling = tag.next_sibling
            if isinstance(sibling, str) and sibling.strip():
                return f"{label}: {sibling.strip()}"
    return None


def _extract_description(soup: BeautifulSoup) -> str:
    candidates = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if "Client rank:" in text or "AI Qualification:" in text:
            continue
        if any(text.startswith(label) for label in _RATE_LABELS):
            continue
        candidates.append(text)
    # The job overview is by far the longest paragraph; title/footer are short.
    return max(candidates, key=len) if candidates else ""


def _extract_pub_date(soup: BeautifulSoup) -> datetime | None:
    for tag in soup.find_all(["strong", "b"]):
        if tag.get_text(strip=True).rstrip(":") == "Published":
            sibling = tag.next_sibling
            if isinstance(sibling, str) and sibling.strip():
                try:
                    return datetime.strptime(sibling.strip(), "%b %d, %Y %H:%M")
                except ValueError:
                    return None
    return None


def parse_job_email(raw: bytes) -> JobEmail:
    """Parse raw RFC822 bytes of a Vollna job email into a JobEmail.

    Raises ValueError if the dedup pid or the Upwork link cannot be extracted.
    """
    return _parse_message(email.message_from_bytes(raw))


def _parse_message(msg: Message) -> JobEmail:
    html = _get_html(msg)

    pid_match = _PID_RE.search(html)
    if not pid_match:
        raise ValueError("no pid in email")
    upwork_match = _UPWORK_ID_RE.search(html)
    if not upwork_match:
        raise ValueError("no upwork job id in email")

    title = _decode_header(msg.get("Subject"))
    if title.startswith(_SUBJECT_PREFIX):
        title = title[len(_SUBJECT_PREFIX) :].strip()

    soup = BeautifulSoup(html, "html.parser")
    return JobEmail(
        external_pid=pid_match.group(1),
        title=title,
        description=_extract_description(soup),
        upwork_link=f"https://www.upwork.com/jobs/~{upwork_match.group(1)}",
        rate=_extract_rate(soup),
        pub_date=_extract_pub_date(soup),
    )


def _message_date(msg: Message) -> datetime | None:
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
    except (TypeError, ValueError):
        return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def fetch_new_job_emails(settings, since: datetime | None = None) -> list[JobEmail]:
    """Fetch unseen Vollna job emails over IMAP, parse them, mark them seen.

    When `since` is given, only emails whose Date is at/after `since` are
    processed — this bounds the first poll after startup to jobs newer than the
    bot start moment instead of the whole unread backlog. Older emails in the
    same-day IMAP `SINCE` window are still marked seen so they aren't re-fetched.

    Blocking (imaplib); call via asyncio.to_thread from the async poller.
    """
    jobs: list[JobEmail] = []
    criteria = ["UNSEEN", "FROM", settings.vollna_sender]
    if since is not None:
        # IMAP SINCE is date-granular; the precise cutoff is applied per message.
        criteria += ["SINCE", since.strftime("%d-%b-%Y")]

    with imaplib.IMAP4_SSL(settings.gmail_imap_host) as imap:
        imap.login(settings.gmail_address, settings.gmail_app_password)
        imap.select(settings.gmail_mailbox)
        typ, data = imap.search(None, *criteria)
        if typ != "OK" or not data or not data[0]:
            return jobs

        for num in data[0].split():
            typ, msg_data = imap.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            msg_date = _message_date(msg)
            if since is not None and msg_date is not None and msg_date < since:
                imap.store(num, "+FLAGS", "\\Seen")
                continue
            try:
                jobs.append(_parse_message(msg))
            except Exception as exc:  # noqa: BLE001 — one bad email must not stop the batch
                logger.warning("Skipping unparseable Vollna email: %s", exc)
            finally:
                imap.store(num, "+FLAGS", "\\Seen")

    return jobs
