import xml.etree.ElementTree as ET

from upwork_bot.rss.client import _parse_item, parse_vollna_link

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
