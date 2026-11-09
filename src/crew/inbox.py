"""The owner's inbox: only the items waiting on the owner, most blocking first."""

from dataclasses import dataclass
from typing import Literal

from crew.graph import (
    DO_FIRST,
    OWNER_ASKS,
    OWNER_PREFIX,
    Unit,
    dependents_count,
    label_names,
    priority_key,
)
from crew.labels import IDEA

ASKS = OWNER_ASKS
INTERNAL = "crew:internal"


@dataclass
class InboxItem:
    """One thing the owner is asked to do."""

    number: int
    title: str
    url: str
    ask: Literal["accept", "decision", "stuck", "proposal"]
    blocks: int
    do_first: bool


def _ask(labels: set[str]) -> str | None:
    for ask in ASKS:
        if f"{OWNER_PREFIX}{ask}" in labels:
            return ask
    return None


def owner_inbox(units: dict[int, Unit], open_prs: list[dict]) -> list[InboxItem]:
    """Items waiting on the owner, from issues' and PRs' ``crew:owner-*`` labels.

    A PR is listed under the issue it closes, or under its own number when it closes none.
    Order: do-first items, then the number of units each blocks, then the oldest first.
    """
    counts = dependents_count(units)
    # Keyed by (number, ask): an issue and its PR may ask different things.
    items: dict[tuple[int, str], tuple[InboxItem, str]] = {}

    for unit in units.values():
        ask = _ask(unit.labels)
        if ask:
            item = InboxItem(
                unit.number,
                unit.title,
                unit.url,
                ask,  # type: ignore[arg-type]
                counts.get(unit.number, 0),
                DO_FIRST in unit.labels,
            )
            items[(unit.number, ask)] = (item, unit.created_at)

    for pr in open_prs:
        labels = label_names(pr)
        ask = _ask(labels)
        if not ask:
            continue
        linked = [ref["number"] for ref in pr.get("closingIssuesReferences") or []]
        number = linked[0] if linked else pr["number"]
        unit = units.get(number)
        do_first = DO_FIRST in labels or bool(unit and DO_FIRST in unit.labels)
        item = InboxItem(
            number,
            pr.get("title", ""),
            pr.get("url", ""),
            ask,  # type: ignore[arg-type]
            counts.get(number, 0),
            do_first,
        )
        items[(number, ask)] = (item, unit.created_at if unit else "")

    ordered = sorted(
        items.values(),
        key=lambda pair: priority_key(pair[0].do_first, pair[0].blocks, pair[1], pair[0].number),
    )
    return [item for item, _ in ordered]


def merged_without_owner(merged_prs: list[dict], since: str | None) -> list[dict]:
    """Merged PRs labeled internal whose merge time is after ``since`` (all when None)."""
    return [
        pr
        for pr in merged_prs
        if INTERNAL in label_names(pr)
        and pr.get("mergedAt")
        and (since is None or pr["mergedAt"] > since)
    ]


def parked_ideas(units: dict[int, Unit]) -> int:
    """The number of open issues labeled ``crew:idea``; they never wait on the owner."""
    return sum(1 for unit in units.values() if IDEA in unit.labels)
