import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RssJob:
    external_pid: str
    title: str
    description: str
    upwork_link: str
    categories: list[str] = field(default_factory=list)
    pub_date: datetime | None = None


def parse_vollna_link(link: str) -> tuple[str, str]:
    query = parse_qs(urlparse(link).query)
    pid = query["pid"][0]
    encoded_url = query["url"][0]
    # Vollna double-URL-encodes the target Upwork link.
    real_url = unquote(unquote(encoded_url))
    return pid, real_url


def _parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def _parse_item(item: ET.Element) -> RssJob:
    title = (item.findtext("title") or "").strip()
    description = (item.findtext("description") or "").strip()
    link = (item.findtext("link") or "").strip()
    pub_date = _parse_pub_date(item.findtext("pubDate"))
    categories = [c.text.strip() for c in item.findall("category") if c.text]

    pid, real_url = parse_vollna_link(link)

    return RssJob(
        external_pid=pid,
        title=title,
        description=description,
        upwork_link=real_url,
        categories=categories,
        pub_date=pub_date,
    )


async def fetch_feed(url: str) -> list[RssJob]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    items = root.findall(".//item")

    jobs = []
    for item in items:
        try:
            job = _parse_item(item)
            jobs.append(job)
        except (KeyError, ValueError, TypeError) as e:
            link = item.findtext("link") or "(no link)"
            logger.warning(f"Skipping malformed feed item: {e}. Link: {link}")
            continue

    return jobs
