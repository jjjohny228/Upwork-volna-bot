from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from upwork_bot.config import get_settings

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an assistant helping a freelancer triage Upwork job postings. "
            "Given the freelancer's resume and a job posting, score how well the job "
            "fits their skills (0-100), write a one-sentence summary, and explain your "
            "reasoning in 1-3 sentences.",
        ),
        (
            "human",
            "RESUME:\n{resume}\n\n"
            "JOB TITLE: {title}\n"
            "JOB CATEGORIES: {categories}\n"
            "JOB DESCRIPTION:\n{description}",
        ),
    ]
)


class JobFit(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    short_summary: str
    reasoning: str


@lru_cache
def _get_structured_llm():
    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    return ANALYSIS_PROMPT | llm.with_structured_output(JobFit)


async def analyze_job(
    resume_text: str, job_title: str, job_description: str, categories: list[str]
) -> JobFit:
    chain = _get_structured_llm()
    return await chain.ainvoke(
        {
            "resume": resume_text,
            "title": job_title,
            "categories": ", ".join(categories),
            "description": job_description,
        }
    )
