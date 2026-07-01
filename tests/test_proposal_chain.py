from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.llm.proposal_chain import generate_proposal


@pytest.mark.asyncio
async def test_generate_proposal_calls_llm_with_context():
    with patch("upwork_bot.llm.proposal_chain._get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = "Dear client, I can help..."
        mock_get_llm.return_value = mock_llm

        result = await generate_proposal(
            resume_text="Python dev",
            job_title="Need scraper",
            job_description="Build a scraper",
            portfolio_snippets=["Scraper Bot: built a resilient pipeline"],
            example_snippets=["Hi, I read your post..."],
        )

    assert result == "Dear client, I can help..."
    mock_llm.ainvoke.assert_awaited_once()
