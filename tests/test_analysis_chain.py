from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.llm.analysis_chain import JobQualification, qualify_job


@pytest.mark.asyncio
async def test_qualify_job_returns_decision():
    fake = JobQualification(
        qualified=True,
        short_summary="Django + OpenAI RAG backend",
        reason="Matches my LLM/Django niche; real client brief.",
    )

    with patch("upwork_bot.llm.analysis_chain._get_structured_llm") as mock_get_llm:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = fake
        mock_get_llm.return_value = mock_chain

        result = await qualify_job(
            job_title="Need a RAG assistant",
            job_description="Build a LangChain RAG over our docs with pgvector.",
        )

    assert result.qualified is True
    assert result.short_summary == "Django + OpenAI RAG backend"
    # qualifier prompt gets only title + description, no resume/categories
    payload = mock_chain.ainvoke.call_args.args[0]
    assert set(payload.keys()) == {"title", "description"}
