from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed, Job
from upwork_bot.rss.poller import poll_once

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <item>
            <title>Poller Test Job 1</title>
            <description>First fake job</description>
            <link>https://www.vollna.com/go?pid=poller-test-1&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~1001</link>
        </item>
        <item>
            <title>Poller Test Job 2</title>
            <description>Second fake job</description>
            <link>https://www.vollna.com/go?pid=poller-test-2&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~1002</link>
        </item>
        <item>
            <title>Poller Test Job 3</title>
            <description>Third fake job</description>
            <link>https://www.vollna.com/go?pid=poller-test-3&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~1003</link>
        </item>
    </channel>
</rss>
"""

TEST_PIDS = ["poller-test-1", "poller-test-2", "poller-test-3"]


@pytest.mark.asyncio
async def test_poll_once_dedups_across_two_runs():
    """End-to-end poll_once verification against the live db.

    Mocks the httpx layer (same pattern as test_rss_client.py) so every feed
    fetch returns a fixed 3-item feed, then runs poll_once twice back to
    back and asserts the second pass reports 0 new jobs. Any pre-existing
    active feeds are temporarily deactivated so the mocked response isn't
    double-attributed to unrelated feeds (e.g. the real seeded "main" feed).
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Feed).where(Feed.is_active.is_(True)))
        other_feeds = list(result.scalars())
        for f in other_feeds:
            f.is_active = False

        test_feed = Feed(
            url="https://example.com/poller-test-feed.xml",
            label="poller-test",
            is_active=True,
        )
        session.add(test_feed)
        await session.commit()
        test_feed_id = test_feed.id
        other_feed_ids = [f.id for f in other_feeds]

    mock_response = AsyncMock()
    mock_response.text = FEED_XML
    mock_response.raise_for_status = lambda: None

    received: list[str] = []

    async def on_new_job(job: Job) -> None:
        received.append(job.external_pid)

    try:
        with patch("upwork_bot.rss.client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            run1_count = await poll_once(on_new_job)
            run2_count = await poll_once(on_new_job)

        assert run1_count == 3
        assert sorted(received) == TEST_PIDS
        assert run2_count == 0
    finally:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Job).where(Job.external_pid.in_(TEST_PIDS)))
            for job in result.scalars():
                await session.delete(job)

            result = await session.execute(select(Feed).where(Feed.id == test_feed_id))
            feed = result.scalar_one_or_none()
            if feed is not None:
                await session.delete(feed)

            if other_feed_ids:
                result = await session.execute(select(Feed).where(Feed.id.in_(other_feed_ids)))
                for f in result.scalars():
                    f.is_active = True

            await session.commit()
