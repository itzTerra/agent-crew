"""Bets: pitch PRs the owner merged, and which of them no unit links yet.

A bet is a merged PR from a ``pitch/NNNN`` branch. It is split once any issue, open or closed,
links it in its ``## Bet`` section: by the pitch file (``NNNN-slug.md``) or by the PR
(``#N`` or its URL). Until then the architect still has to split it into units.
"""

import re
from dataclasses import dataclass

from crew.units import parse_unit_body

_PITCH_BRANCH = re.compile(r"^pitch/(\d{4})(?:-[a-z0-9-]*)?$")


@dataclass(frozen=True)
class Bet:
    """A merged pitch PR."""

    number: int  # the pitch PR
    pitch: str  # the pitch's four-digit number
    title: str
    url: str


def _links(bet_text: str, bet: Bet) -> bool:
    patterns = (
        rf"(?<![\d]){bet.pitch}-[a-z0-9-]*\.md",
        rf"#{bet.number}(?!\d)",
        rf"/pull/{bet.number}(?!\d)",
    )
    return any(re.search(pattern, bet_text) for pattern in patterns)


def unsplit_bets(merged_prs: list[dict], issues: list[dict]) -> list[Bet]:
    """Merged pitch PRs that no issue's ``## Bet`` section links, oldest PR first."""
    bet_texts = [parse_unit_body(item.get("body") or "").bet for item in issues]
    result = []
    for pr in sorted(merged_prs, key=lambda item: item["number"]):
        match = _PITCH_BRANCH.match(pr.get("headRefName") or "")
        if not match:
            continue
        bet = Bet(pr["number"], match.group(1), pr.get("title", ""), pr.get("url", ""))
        if not any(_links(text, bet) for text in bet_texts):
            result.append(bet)
    return result
