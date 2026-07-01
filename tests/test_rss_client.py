import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.rss.client import _parse_item, fetch_feed, parse_vollna_link

SAMPLE_LINK = (
    "https://www.vollna.com/go?"
    "pid=abc123def&"
    "url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~0123456789abcdef"
)


def test_parse_vollna_link_extracts_pid_and_decoded_url():
    pid, real_url = parse_vollna_link(SAMPLE_LINK)

    assert pid == "abc123def"
    assert real_url == "https://www.upwork.com/jobs/~0123456789abcdef"


SAMPLE_ITEM_XML = """
<item>
    <title>Need a Python developer</title>
    <description><![CDATA[Looking for someone to build a scraper.]]></description>
    <pubDate>Wed, 01 Jul 2026 12:00:00 GMT</pubDate>
    <link>https://www.vollna.com/go?pid=xyz789&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~999</link>
    <category>Web, Mobile &amp; Software Dev</category>
    <category>Python</category>
</item>
"""


def test_parse_item_extracts_all_fields():
    item = ET.fromstring(SAMPLE_ITEM_XML)
    job = _parse_item(item)

    assert job.external_pid == "xyz789"
    assert job.upwork_link == "https://www.upwork.com/jobs/~999"
    assert job.title == "Need a Python developer"
    assert "scraper" in job.description
    assert job.categories == ["Web, Mobile & Software Dev", "Python"]
    assert job.pub_date is not None


@pytest.mark.asyncio
async def test_fetch_feed_skips_malformed_items():
    """Test that fetch_feed skips items with missing query params instead of crashing."""
    # Feed with one well-formed item, one malformed item (missing pid/url), and another well-formed.
    feed_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>Good Job 1</title>
                <description>First job</description>
                <link>https://www.vollna.com/go?pid=good1&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~111</link>
            </item>
            <item>
                <title>Malformed Job</title>
                <description>Missing pid/url params</description>
                <link>https://www.vollna.com/go?badparam=value</link>
            </item>
            <item>
                <title>Good Job 2</title>
                <description>Second job</description>
                <link>https://www.vollna.com/go?pid=good2&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~222</link>
            </item>
        </channel>
    </rss>
    """

    mock_response = AsyncMock()
    mock_response.text = feed_xml
    mock_response.raise_for_status = lambda: None

    with patch("upwork_bot.rss.client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        jobs = await fetch_feed("https://example.com/feed.xml")

        # Should have parsed 2 jobs (the well-formed ones), skipping the malformed one.
        assert len(jobs) == 2
        assert jobs[0].external_pid == "good1"
        assert jobs[0].title == "Good Job 1"
        assert jobs[1].external_pid == "good2"
        assert jobs[1].title == "Good Job 2"
