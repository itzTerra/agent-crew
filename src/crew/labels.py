"""The crew label set. Every label starts with ``crew:``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crew.github import GitHub


@dataclass(frozen=True)
class Label:
    """One GitHub label: name, 6-digit hex color without ``#``, and a description."""

    name: str
    color: str
    description: str


LABELS: list[Label] = [
    # Work state.
    Label("crew:rough", "d4c5f9", "Not yet refined to the definition of ready."),
    Label("crew:ready", "0e8a16", "Meets the definition of ready; a worker may take it."),
    Label("crew:in-progress", "fbca04", "A worker is implementing it."),
    Label("crew:in-review", "1d76db", "Waiting for the agent review gate."),
    Label("crew:changes-requested", "e99695", "Review or owner feedback must be addressed."),
    # Waiting on the owner.
    Label("crew:owner-accept", "b60205", "Waiting for the owner to accept the work."),
    Label("crew:owner-decision", "b60205", "Waiting for the owner to decide a question."),
    Label("crew:owner-stuck", "b60205", "Failed review three times and needs the owner."),
    Label("crew:owner-proposal", "b60205", "A proposal waiting for the owner's pitch challenge."),
    # Priority and kind.
    Label("crew:do-first", "5319e7", "The owner wants this before anything else."),
    Label("crew:owner-facing", "c5def5", "Needs the owner's acceptance before merging."),
    Label("crew:internal", "bfdadc", "Merges after review and CI without the owner."),
]

# Flow labels: at most one on an issue or PR at a time. The owner asks
# crew:owner-decision and crew:owner-proposal may stack on top of a flow label.
FLOW = (
    "crew:rough",
    "crew:ready",
    "crew:in-progress",
    "crew:in-review",
    "crew:changes-requested",
    "crew:owner-accept",
    "crew:owner-stuck",
)
# "done" removes every flow label.
STATES = (
    "rough",
    "ready",
    "in-progress",
    "in-review",
    "changes-requested",
    "owner-accept",
    "owner-stuck",
    "done",
)
DONE = "done"


def _names(item: dict) -> set[str]:
    return {label["name"] for label in item.get("labels") or []}


def _flow_of(names: set[str]) -> list[str]:
    return [name for name in FLOW if name in names]


def _linked(pr: dict) -> list[int]:
    return [ref["number"] for ref in pr.get("closingIssuesReferences") or []]


def set_state(github: GitHub, number: int, state: str) -> list[int]:
    """Move an issue and its open PRs (or a PR and its issues) to one flow state together.

    Each item loses the flow labels it carries and gains ``crew:<state>``; other labels stay.
    ``done`` removes every flow label, from the issue's merged PRs too.

    Args:
        github: the repo's client.
        number: an issue or a PR. A number found among the open PRs (or, for ``done``,
            the merged ones) is a PR; any other number is an issue.
        state: one of ``STATES``.

    Returns:
        The numbers the state was applied to, ascending.

    Raises:
        ValueError: ``state`` is not one of ``STATES``.
    """
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}; choose one of {', '.join(STATES)}")
    prs = list(github.list_prs("open"))
    if state == DONE:
        prs += github.list_prs("merged")
    by_number = {pr["number"]: pr for pr in prs}
    issues = _linked(by_number[number]) if number in by_number else [number]
    targets = {number, *issues}
    targets |= {pr["number"] for pr in prs if set(_linked(pr)) & set(issues)}

    wanted = None if state == DONE else f"crew:{state}"
    for target in sorted(targets):
        current = github.labels_of(target)
        remove = [name for name in _flow_of(current) if name != wanted]
        add = [wanted] if wanted and wanted not in current else []
        if add or remove:
            github.set_labels(target, add, remove)
    return sorted(targets)


@dataclass(frozen=True)
class LabelProblem:
    """A label inconsistency on one issue or PR."""

    number: int
    message: str
    fix_remove: tuple[str, ...]  # empty: not safe to fix automatically


def label_problems(
    open_issues: list[dict],
    closed_issues: list[dict],
    open_prs: list[dict],
    merged_prs: list[dict],
) -> list[LabelProblem]:
    """Flow labels that disagree with an item's state or with each other.

    In this order, each by number: closed issues and merged PRs still carrying flow labels
    (fixable by removing them); open items with more than one flow label; open PRs whose
    flow label differs from their linked open issue's.
    """
    problems: list[LabelProblem] = []
    for kind, items in (("closed issue", closed_issues), ("merged PR", merged_prs)):
        for item in sorted(items, key=lambda i: i["number"]):
            if flow := _flow_of(_names(item)):
                problems.append(
                    LabelProblem(item["number"], f"{kind} still has {', '.join(flow)}", tuple(flow))
                )
    for item in sorted([*open_issues, *open_prs], key=lambda i: i["number"]):
        flow = _flow_of(_names(item))
        if len(flow) > 1:
            message = f"has more than one state label: {', '.join(flow)}"
            problems.append(LabelProblem(item["number"], message, ()))
    issue_flow = {item["number"]: _flow_of(_names(item)) for item in open_issues}
    for pr in sorted(open_prs, key=lambda i: i["number"]):
        pr_flow = _flow_of(_names(pr))
        for linked in _linked(pr):
            theirs = issue_flow.get(linked)
            if len(pr_flow) == 1 and theirs and len(theirs) == 1 and theirs != pr_flow:
                message = (
                    f"PR #{pr['number']} has {pr_flow[0]}, its issue #{linked} has {theirs[0]}"
                )
                problems.append(LabelProblem(pr["number"], message, ()))
    return problems
