from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from upwork_bot.config import get_settings

PROPOSAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are helping a freelancer write an Upwork proposal. Use their resume, "
            "similar past portfolio projects, and past proposal examples as style/content "
            "reference. Write a concise, specific, non-generic proposal in the freelancer's "
            "voice. Do not use placeholder brackets.",
        ),
        (
            "human",
            "RESUME:\n{resume}\n\n"
            "JOB TITLE: {title}\n"
            "JOB DESCRIPTION:\n{description}\n\n"
            "RELEVANT PORTFOLIO PROJECTS:\n{portfolio}\n\n"
            "PAST PROPOSAL EXAMPLES (style reference):\n{examples}\n\n"
            "{revision_context}",
        ),
    ]
)


@lru_cache
def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key, temperature=0.7)


def _build_revision_context(previous_version: str | None, feedback: str | None) -> str:
    if not previous_version:
        return ""
    return (
        f"PREVIOUS DRAFT:\n{previous_version}\n\n"
        f"USER FEEDBACK ON PREVIOUS DRAFT:\n{feedback}\n\n"
        "Revise the draft to address this feedback."
    )


async def generate_proposal(
    resume_text: str,
    job_title: str,
    job_description: str,
    portfolio_snippets: list[str],
    example_snippets: list[str],
    previous_version: str | None = None,
    feedback: str | None = None,
) -> str:
    llm = _get_llm()
    messages = PROPOSAL_PROMPT.format_messages(
        resume=resume_text,
        title=job_title,
        description=job_description,
        portfolio="\n---\n".join(portfolio_snippets) or "(none)",
        examples="\n---\n".join(example_snippets) or "(none)",
        revision_context=_build_revision_context(previous_version, feedback),
    )
    response = await llm.ainvoke(messages)
    return response.content
