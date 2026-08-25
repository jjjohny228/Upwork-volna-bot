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

    with patch("upwork_bot.llm.analysis_chain._get_analysis_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = fake
        mock_get_llm.return_value = mock_llm

        result = await qualify_job(
            job_title="Need a RAG assistant",
            job_description="Build a LangChain RAG over our docs with pgvector.",
        )

    assert result.qualified is True
    assert result.short_summary == "Django + OpenAI RAG backend"
    # qualifier gets a system + human message; the human carries title + description.
    messages = mock_llm.ainvoke.call_args.args[0]
    assert len(messages) == 2
    human = messages[1].content
    assert "Need a RAG assistant" in human
    assert "LangChain RAG" in human


@pytest.mark.asyncio
async def test_qualify_job_uses_custom_prompt_and_falls_back():
    from upwork_bot.llm.analysis_chain import QUALIFIER_SYSTEM_PROMPT

    fake = JobQualification(qualified=False, short_summary="s", reason="r")

    with patch("upwork_bot.llm.analysis_chain._get_analysis_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = fake
        mock_get_llm.return_value = mock_llm

        await qualify_job("t", "d", analysis_prompt="MY CUSTOM {rules} PROMPT")
        custom_system = mock_llm.ainvoke.call_args.args[0][0].content
        assert custom_system == "MY CUSTOM {rules} PROMPT"

        await qualify_job("t", "d")
        default_system = mock_llm.ainvoke.call_args.args[0][0].content
        assert default_system == QUALIFIER_SYSTEM_PROMPT
