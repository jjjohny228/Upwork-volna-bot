"""Generate a personalized job-qualification system prompt for a user.

Takes the user's resume + portfolio projects and writes a qualification prompt in
the same shape as the built-in QUALIFIER_SYSTEM_PROMPT (used as a structural
example), tailored to that freelancer's stack, niche, and positioning. The output
becomes the user's `analysis_prompt`, consumed by `qualify_job`.
"""

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from upwork_bot.config import get_settings
from upwork_bot.llm.analysis_chain import QUALIFIER_SYSTEM_PROMPT

_META_SYSTEM_PROMPT = """\
You are a prompt engineer. Write a job-qualification SYSTEM PROMPT that an LLM will use to
decide whether an Upwork job posting fits a specific freelancer (qualify vs disqualify).

You are given:
1. A REFERENCE EXAMPLE — a well-structured qualification prompt written for a
different freelancer. Mirror its structure, tone, strictness, and sections (an
"ABOUT ME" block, explicit QUALIFY-when rules, and DISQUALIFY red flags), and keep
the same instruction that the LLM must return the qualified flag, a one-sentence
short_summary, and a reason.
2. The TARGET freelancer's RESUME and PORTFOLIO PROJECTS.

Rewrite the reference so it fits the TARGET freelancer: replace the niche, delivery
stack, positioning, and skill-fit rules with theirs, derived strictly from their
resume and portfolio. Keep the general anti-scam / templated-junk red flags. Do not
invent skills the resume/portfolio do not support.

Output ONLY the finished system prompt text — no preamble, no explanation, no code fences."""


@lru_cache
def _get_llm():
    settings = get_settings()
    return ChatOpenAI(model="gpt-5.4-mini", api_key=settings.openai_api_key, temperature=0.3)


async def generate_analysis_prompt(resume_text: str, portfolio_snippets: list[str]) -> str:
    portfolio = "\n---\n".join(portfolio_snippets) or "(none)"
    human = (
        f"REFERENCE EXAMPLE (structure to mirror):\n{QUALIFIER_SYSTEM_PROMPT}\n\n"
        f"===\n\n"
        f"TARGET FREELANCER RESUME:\n{resume_text}\n\n"
        f"TARGET FREELANCER PORTFOLIO PROJECTS:\n{portfolio}"
    )
    messages = [SystemMessage(content=_META_SYSTEM_PROMPT), HumanMessage(content=human)]
    response = await _get_llm().ainvoke(messages)
    return response.content.strip()
