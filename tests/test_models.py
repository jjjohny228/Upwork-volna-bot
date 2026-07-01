import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed


@pytest.mark.asyncio
async def test_insert_and_query_feed():
    async with AsyncSessionLocal() as session:
        feed = Feed(url="https://vollna.com/rss/test-unique-123", label="test")
        session.add(feed)
        await session.commit()

        result = await session.execute(select(Feed).where(Feed.url == feed.url))
        loaded = result.scalar_one()
        assert loaded.label == "test"
        assert loaded.is_active is True

        await session.delete(loaded)
        await session.commit()
