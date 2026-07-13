import re
from functools import lru_cache

from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from upwork_bot.config import get_settings
from upwork_bot.estimator import estimate_budget, estimate_budget_tool


def strip_markdown(text: str) -> str:
    """Remove Markdown emphasis the model still emits (Telegram sends plain text).

    Drops **bold**/*italic*/__underline__ markers and leading heading hashes, while
    keeping '- ' bullet lists intact.
    """
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", text)  # ATX headings
    text = text.replace("*", "")  # stray single-asterisk emphasis
    return text


def portfolio_snippet(project) -> str:
    """Format a portfolio project for the prompt, including its real URL when present."""
    if getattr(project, "link", None):
        return f"{project.title} ({project.link}): {project.description}"
    return f"{project.title}: {project.description}"


def _build_signature_context(name: str) -> str:
    if not name:
        return ""
    return f"End the proposal with a sign-off on its own line using this name: {name}\n\n"


def _build_rate_context(hourly_rate: float) -> str:
    if not hourly_rate:
        return ""
    return f"HOURLY RATE: {hourly_rate} USD/hour\n\n"


PROPOSAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are helping a freelancer write an Upwork proposal. Use their resume, "
            "similar past portfolio projects, and past proposal examples as style/content "
            "reference. Write a concise, specific, non-generic proposal in the freelancer's "
            "voice. Do not use placeholder brackets. "
            "Write the proposal in the same language as the JOB DESCRIPTION, regardless of "
            "the language of the resume or past examples. "
            "If the JOB DESCRIPTION asks the applicant to start the proposal with a specific "
            "word or phrase (e.g. a keyword to prove they read the post), begin the proposal "
            "with exactly that word or phrase. "
            "Write plain text only: no asterisks, no bold, no headings, no Markdown emphasis. "
            "When you present the proposed tech stack (and only for such short lists), write it "
            "as a simple list with each item on its own line starting with '- '. "
            "When you reference a portfolio project, insert its real URL directly as a plain "
            "clickable link (e.g. https://example.com), never a bold name or placeholder. "
            "Only mention a project link if a real URL is provided for it. "
            "The freelancer bills hourly. Only mention budget, price, cost, timeline, or "
            "duration if the JOB DESCRIPTION explicitly asks for it (e.g. it requests an "
            "estimate, budget, rate, or timeline). If the job does not ask, do not mention "
            "money, timeline, or estimates at all. When the job does ask for a budget, derive "
            "it with the estimate_budget tool from the given HOURLY RATE and your estimated "
            "duration — never invent a fixed lump sum — and present it as the hourly rate plus "
            "the estimated total. If no hourly rate is provided, give the timeline but not a "
            "total price.",
        ),
        (
            "human",
            "RESUME:\n{resume}\n\n"
            "JOB TITLE: {title}\n"
            "JOB DESCRIPTION:\n{description}\n\n"
            "RELEVANT PORTFOLIO PROJECTS:\n{portfolio}\n\n"
            "PAST PROPOSAL EXAMPLES (style reference):\n{examples}\n\n"
            "{rate_context}"
            "{signature_context}"
            "{revision_context}",
        ),
    ]
)


@lru_cache
def _get_llm():
    settings = get_settings()
    llm = ChatOpenAI(model="gpt-5.4-mini", api_key=settings.openai_api_key, temperature=0.7)
    return llm.bind_tools([estimate_budget_tool])


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
    settings = get_settings()
    llm = _get_llm()
    messages = PROPOSAL_PROMPT.format_messages(
        resume=resume_text,
        title=job_title,
        description=job_description,
        portfolio="\n---\n".join(portfolio_snippets) or "(none)",
        examples="\n---\n".join(example_snippets) or "(none)",
        rate_context=_build_rate_context(settings.hourly_rate),
        signature_context=_build_signature_context(settings.proposal_signature_name),
        revision_context=_build_revision_context(previous_version, feedback),
    )
    response = await llm.ainvoke(messages)

    # Resolve any estimate_budget tool calls, then let the model finish the draft.
    while isinstance(getattr(response, "tool_calls", None), list) and response.tool_calls:
        messages.append(response)
        for call in response.tool_calls:
            result = estimate_budget(**call["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        response = await llm.ainvoke(messages)

    return strip_markdown(response.content)
