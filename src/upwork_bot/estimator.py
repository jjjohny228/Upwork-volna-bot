"""Budget estimation from an hourly rate and a project duration.

Working-time assumptions (averages): 21 working days per month, 8 hours per day,
40 hours per week. Used to turn a duration estimate into an hourly-rate budget.
"""

from langchain_core.tools import StructuredTool

WORKING_DAYS_PER_MONTH = 21
HOURS_PER_DAY = 8
HOURS_PER_WEEK = 40


def estimate_budget(
    hourly_rate: float,
    months: float = 0.0,
    weeks: float = 0.0,
    days: float = 0.0,
    hours: float = 0.0,
) -> dict:
    """Estimate total hours and cost for a duration at a given hourly rate (USD/hour).

    Duration is the sum of the months/weeks/days/hours arguments. Averages used:
    1 month = 21 working days, 1 week = 40 hours, 1 day = 8 hours.
    """
    total_hours = (
        months * WORKING_DAYS_PER_MONTH * HOURS_PER_DAY
        + weeks * HOURS_PER_WEEK
        + days * HOURS_PER_DAY
        + hours
    )
    total_usd = round(total_hours * hourly_rate, 2)
    return {
        "hourly_rate": hourly_rate,
        "total_hours": round(total_hours, 2),
        "total_usd": total_usd,
    }


estimate_budget_tool = StructuredTool.from_function(
    func=estimate_budget,
    name="estimate_budget",
    description=(
        "Compute a project budget in USD from an hourly rate and a duration. "
        "Pass the hourly_rate (USD/hour) and the duration split across months, weeks, "
        "days, hours. Assumes 21 working days/month, 8 hours/day, 40 hours/week. "
        "Use this whenever you state a budget or cost so the number is consistent with "
        "the hourly rate."
    ),
)
