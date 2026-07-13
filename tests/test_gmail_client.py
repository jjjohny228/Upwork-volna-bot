from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import upwork_bot.gmail.client as gmail_client
from upwork_bot.gmail.client import fetch_new_job_emails, parse_job_email

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_hourly_email():
    raw = (FIXTURES / "vollna_hourly.eml").read_bytes()
    job = parse_job_email(raw)

    assert job.external_pid == "74835640"
    assert job.upwork_link == "https://www.upwork.com/jobs/~022074164276058730392"
    assert job.title == (
        "Developer Needed to Turn an AI SaaS Concept Into an MVP "
        "(Vibe-Coded Prototype Already Exists)"
    )
    assert job.rate == "Hourly Rate: 25 - 47 USD"
    assert "My Adam Preview" in job.description
    assert job.pub_date == datetime(2026, 7, 6, 16, 12)


def _build_email(rate_label: str, rate_value: str) -> bytes:
    return (
        "From: Vollna <info@vollna.com>\n"
        "Subject: New Job: Quick fix\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        "<html><body>"
        '<p><a href="https://x/go?pid=999&url=https://www.upwork.com/jobs/~012345678901234567">'
        "Quick fix</a></p>"
        f"<p><strong>{rate_label}:</strong> {rate_value}<br>"
        "<strong>Published:</strong> Jul 6, 2026 16:12</p>"
        "<p>This is the job description body with enough text to be the longest paragraph.</p>"
        "</body></html>"
    ).encode()


def test_parse_fixed_price():
    job = parse_job_email(_build_email("Fixed Price", "50 USD"))

    assert job.external_pid == "999"
    assert job.upwork_link == "https://www.upwork.com/jobs/~012345678901234567"
    assert job.title == "Quick fix"
    assert job.rate == "Fixed Price: 50 USD"
    assert "description body" in job.description


def _raw_with_date(date_header: str, pid: int) -> bytes:
    return (
        f"From: Vollna <info@vollna.com>\nSubject: New Job: t\nDate: {date_header}\n"
        "Content-Type: text/html; charset=utf-8\n\n"
        f'<html><body><p><a href="x?pid={pid}&'
        'url=https://www.upwork.com/jobs/~012345678901234567">t</a></p>'
        "<p>long enough description paragraph for parsing</p></body></html>"
    ).encode()


def test_fetch_skips_emails_older_than_since(monkeypatch):
    imap = MagicMock()
    imap.search.return_value = ("OK", [b"1 2"])
    imap.fetch.side_effect = [
        ("OK", [(b"1", _raw_with_date("Mon, 6 Jul 2026 15:00:00 +0000", 111))]),  # old
        ("OK", [(b"2", _raw_with_date("Mon, 6 Jul 2026 17:00:00 +0000", 222))]),  # new
    ]

    class _Ctx:
        def __enter__(self):
            return imap

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gmail_client.imaplib, "IMAP4_SSL", lambda host: _Ctx())
    settings = SimpleNamespace(
        gmail_imap_host="h",
        gmail_address="a",
        gmail_app_password="p",
        gmail_mailbox="INBOX",
        vollna_sender="info@vollna.com",
    )

    since = datetime(2026, 7, 6, 16, 0, tzinfo=UTC)
    jobs = fetch_new_job_emails(settings, since)

    assert [j.external_pid for j in jobs] == ["222"]  # old one skipped
    assert "SINCE" in imap.search.call_args.args
    assert imap.store.call_count == 2  # both marked seen


def test_missing_pid_raises():
    raw = (
        b"From: Vollna <info@vollna.com>\nSubject: New Job: x\n\n"
        b"<html><body><p>no link</p></body></html>"
    )
    try:
        parse_job_email(raw)
    except ValueError:
        return
    raise AssertionError("expected ValueError for missing pid")
