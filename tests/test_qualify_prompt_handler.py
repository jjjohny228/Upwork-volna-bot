from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.qualify_prompt import generate_prompt
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import PortfolioProject
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id, upsert_resume


def _make_message() -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text="✨ Generate prompt",
    )


@pytest.mark.asyncio
async def test_generate_prompt_refuses_without_resume_and_portfolio():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=557001, display_name="empty")

    try:
        with (
            patch.object(Message, "answer", new_callable=AsyncMock),
            patch(
                "upwork_bot.bot.handlers.qualify_prompt.generate_analysis_prompt",
                new=AsyncMock(),
            ) as gen,
        ):
            await generate_prompt(_make_message(), user)
            # Gate blocks generation until resume + a portfolio project exist.
            gen.assert_not_awaited()
        assert user.analysis_prompt is None
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=557001)


@pytest.mark.asyncio
async def test_generate_prompt_saves_when_resume_and_portfolio_present():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=557002, display_name="ready")
        await upsert_resume(session, user.id, content="Python/Django engineer")
        session.add(
            PortfolioProject(
                user_id=user.id,
                title="RAG bot",
                description="pgvector RAG",
                link=None,
                embedding=[0.0] * 1536,
            )
        )
        await session.commit()

    try:
        with (
            patch.object(Message, "answer", new_callable=AsyncMock),
            patch(
                "upwork_bot.bot.handlers.qualify_prompt.generate_analysis_prompt",
                new=AsyncMock(return_value="GENERATED PROMPT"),
            ) as gen,
        ):
            await generate_prompt(_make_message(), user)
            gen.assert_awaited_once()

        assert user.analysis_prompt == "GENERATED PROMPT"
        async with AsyncSessionLocal() as session:
            saved = await get_user_by_telegram_id(session, 557002)
            assert saved.analysis_prompt == "GENERATED PROMPT"
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=557002)
