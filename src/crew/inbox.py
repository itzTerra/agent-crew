"""The owner's inbox: only the items waiting on the owner, most blocking first."""

from dataclasses import dataclass
from typing import Literal

from crew.graph import (
    OWNER_ASKS,
    OWNER_PREFIX,
    Unit,
    dependents_count,
    effective_ranks,
    label_names,
    own_rank,
    priority_key,
    rank_name,
)
from crew.labels import IDEA, PRIORITY_LABELS

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
    priority: str  # must, should or later: the effective priority


def _ask(labels: set[str]) -> str | None:
    for ask in ASKS:
        if f"{OWNER_PREFIX}{ask}" in labels:
            return ask
    return None


def owner_inbox(units: dict[int, Unit], open_prs: list[dict]) -> list[InboxItem]:
    """Items waiting on the owner, from issues' and PRs' ``crew:owner-*`` labels.

    A PR is listed under the issue it closes, or under its own number when it closes none.
    Order: effective priority (see ``effective_ranks``; a PR counts at least as high as its
    issue), then the number of units each blocks, then the oldest first.
    """
    counts = dependents_count(units)
    ranks = effective_ranks(units)
    # Keyed by (number, ask): an issue and its PR may ask different things.
    items: dict[tuple[int, str], tuple[InboxItem, str, int]] = {}

    for unit in units.values():
        ask = _ask(unit.labels)
        if ask:
            item = InboxItem(
                unit.number,
                unit.title,
                unit.url,
                ask,  # type: ignore[arg-type]
                counts.get(unit.number, 0),
                rank_name(ranks[unit.number]),
            )
            items[(unit.number, ask)] = (item, unit.created_at, ranks[unit.number])

    for pr in open_prs:
        labels = label_names(pr)
        ask = _ask(labels)
        if not ask:
            continue
        linked = [ref["number"] for ref in pr.get("closingIssuesReferences") or []]
        number = linked[0] if linked else pr["number"]
        unit = units.get(number)
        if unit is None:
            rank = own_rank(labels)
        elif labels & set(PRIORITY_LABELS):
            rank = min(own_rank(labels), ranks[number])
        else:
            rank = ranks[number]  # an unlabeled PR takes its issue's priority
        item = InboxItem(
            number,
            pr.get("title", ""),
            pr.get("url", ""),
            ask,  # type: ignore[arg-type]
            counts.get(number, 0),
            rank_name(rank),
        )
        items[(number, ask)] = (item, unit.created_at if unit else "", rank)

    ordered = sorted(
        items.values(),
        key=lambda entry: priority_key(entry[2], entry[0].blocks, entry[1], entry[0].number),
    )
    return [item for item, _, _ in ordered]


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
