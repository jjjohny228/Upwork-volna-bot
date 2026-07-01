from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.llm.analysis_chain import JobFit, analyze_job


@pytest.mark.asyncio
async def test_analyze_job_returns_structured_fit():
    fake_fit = JobFit(
        fit_score=85, short_summary="Good Python fit", reasoning="Matches resume skills"
    )

    with patch("upwork_bot.llm.analysis_chain._get_structured_llm") as mock_get_llm:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = fake_fit
        mock_get_llm.return_value = mock_chain

        result = await analyze_job(
            resume_text="Senior Python dev, 10 years, FastAPI, Django",
            job_title="Need Python developer",
            job_description="Build a scraper",
            categories=["Python"],
        )

    assert result.fit_score == 85
    assert result.short_summary == "Good Python fit"
