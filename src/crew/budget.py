"""This week's budget cap: the configured default, or an override that lasts until the reset."""

from datetime import datetime

from crew.config import BUDGET_MAX, BUDGET_MIN, Config
from crew.usage import Usage

OVERRIDE_KEY = "budget_override"


def effective_cap(config: Config, state: dict, now: datetime) -> tuple[int, str]:
    """The cap in force at ``now`` and where it comes from.

    Returns:
        ``(percent, "default")``, or ``(percent, "this week until <ISO>")`` while an override
        in ``state["budget_override"]`` lasts. An expired or malformed override is ignored.
    """
    override = state.get(OVERRIDE_KEY)
    if isinstance(override, dict):
        percent, until = override.get("percent"), override.get("until")
        try:
            ends = datetime.fromisoformat(str(until))
        except ValueError:
            ends = None
        valid = isinstance(percent, int) and not isinstance(percent, bool)
        if valid and ends and ends.tzinfo and BUDGET_MIN <= percent <= BUDGET_MAX and now < ends:
            return percent, f"this week until {until}"
    return config.budget_cap_percent, "default"


def week_override(percent: int, usage: Usage) -> dict:
    """The ``state["budget_override"]`` value that holds ``percent`` until the weekly reset."""
    return {"percent": percent, "until": usage.week_resets_at.isoformat()}
