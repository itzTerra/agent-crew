"""The crew label set. Every label starts with ``crew:``."""

from __future__ import annotations

import re
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


# A parked idea: never carries a flow label and never waits on the owner.
IDEA = "crew:idea"
OWNER_PROPOSAL = "crew:owner-proposal"
# Priority, highest first; the same scale as the requirements (Must, Should, Later).
PRIORITY_LABELS = ("crew:must", "crew:should", "crew:later")
# An item with no priority label counts as this one.
DEFAULT_PRIORITY = "crew:should"

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
    # Parked.
    Label(IDEA, "ededed", "A parked idea: not a bet, not work, not waiting on the owner."),
    # Priority and kind.
    Label("crew:must", "5319e7", "Needed for the current cut (MVP or the bet it serves)."),
    Label("crew:should", "9b7fd4", "Wanted, but the cut works without it."),
    Label("crew:later", "d8cdf0", "A nice-to-have or a later idea."),
    Label("crew:owner-facing", "c5def5", "Needs the owner's acceptance before merging."),
    Label("crew:internal", "bfdadc", "Merges after review and CI without the owner."),
    Label("crew:design", "f9d0c4", "Design work: the designer builds it, not the implementer."),
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
# A unit's branch, ``unit/<n>-<slug>`` (see ``crew.supervisor.planner.unit_branch``).
_UNIT_BRANCH = re.compile(r"^unit/(\d+)-")


def _names(item: dict) -> set[str]:
    return {label["name"] for label in item.get("labels") or []}


def _flow_of(names: set[str]) -> list[str]:
    return [name for name in FLOW if name in names]


def _linked(pr: dict) -> list[int]:
    return [ref["number"] for ref in pr.get("closingIssuesReferences") or []]


def _unit_of(pr: dict) -> int | None:
    """The unit whose branch the PR is on, or None for a branch not named ``unit/<n>-…``."""
    match = _UNIT_BRANCH.match(pr.get("headRefName") or "")
    return int(match.group(1)) if match else None


def _unlinked_unit_pr(pr: dict) -> str | None:
    """Why an open PR on a unit's branch doesn't count as that unit's, or None if it does.

    Such a PR is invisible to ``set_state`` and to the inbox's grouping by issue, for example
    when its body was taken from another PR's and closes the wrong issue.
    """
    unit = _unit_of(pr)
    if unit is None or unit in _linked(pr):
        return None
    branch = pr["headRefName"]
    return (
        f"PR #{pr['number']} is on branch {branch} but doesn't close #{unit}; "
        f"put `Closes #{unit}` in its body"
    )


def set_state(github: GitHub, number: int, state: str) -> list[int]:
    """Move an issue and its open PRs (or a PR and its issues) to one flow state together.

    Every issue an affected open PR closes moves too, so a PR that closes several issues
    keeps them all in its state whichever of them ``number`` names.

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
        ValueError: ``state`` is not one of ``STATES``, or ``number`` is an open PR on a
            ``unit/<n>-…`` branch that doesn't close ``n``, or such a PR's unit (nothing is
            changed).
    """
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}; choose one of {', '.join(STATES)}")
    prs = list(github.list_prs("open"))
    for pr in prs:
        problem = _unlinked_unit_pr(pr)
        if problem and number in (pr["number"], _unit_of(pr)):
            raise ValueError(problem)
    open_prs = list(prs)
    if state == DONE:
        prs += github.list_prs("merged")
    by_number = {pr["number"]: pr for pr in prs}
    issues = set(_linked(by_number[number])) if number in by_number else {number}
    # An open PR that closes one of the issues brings every other issue it closes along.
    while more := {n for pr in open_prs if set(_linked(pr)) & issues for n in _linked(pr)} - issues:
        issues |= more
    targets = {number, *issues}
    targets |= {pr["number"] for pr in prs if set(_linked(pr)) & issues}

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
    # A state (as for ``set_state``) to move ``number`` and its issues to instead, or None.
    fix_state: str | None = None


def label_problems(
    open_issues: list[dict],
    closed_issues: list[dict],
    open_prs: list[dict],
    merged_prs: list[dict],
) -> list[LabelProblem]:
    """Flow labels that disagree with an item's state or with each other.

    In this order, each by number: closed issues and merged PRs still carrying flow labels
    (fixable by removing them); open items with more than one flow label or more than one
    priority label; open issues with
    ``crew:idea`` and a flow label or ``crew:owner-proposal``; open PRs whose
    flow label differs from their linked open issue's (fixable by moving the issue to the
    PR's state when it is the issue's only open PR); open PRs on a ``unit/<n>-…`` branch
    that don't close issue ``n``.
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
        priorities = [name for name in PRIORITY_LABELS if name in _names(item)]
        if len(priorities) > 1:
            message = f"has more than one priority label: {', '.join(priorities)}"
            problems.append(LabelProblem(item["number"], message, ()))
    for item in sorted(open_issues, key=lambda i: i["number"]):
        names = _names(item)
        if IDEA in names:
            clash = _flow_of(names) + ([OWNER_PROPOSAL] if OWNER_PROPOSAL in names else [])
            if clash:
                message = f"parked idea also has {', '.join(clash)}"
                problems.append(LabelProblem(item["number"], message, ()))
    issue_flow = {item["number"]: _flow_of(_names(item)) for item in open_issues}
    open_prs_of: dict[int, int] = {}
    for pr in open_prs:
        for linked in _linked(pr):
            open_prs_of[linked] = open_prs_of.get(linked, 0) + 1
    for pr in sorted(open_prs, key=lambda i: i["number"]):
        pr_flow = _flow_of(_names(pr))
        for linked in _linked(pr):
            theirs = issue_flow.get(linked)
            if len(pr_flow) == 1 and theirs and len(theirs) == 1 and theirs != pr_flow:
                message = (
                    f"PR #{pr['number']} has {pr_flow[0]}, its issue #{linked} has {theirs[0]}"
                )
                # The PR's label wins when it is the issue's only open PR.
                only = open_prs_of[linked] == 1
                fix = pr_flow[0].removeprefix("crew:") if only else None
                problems.append(LabelProblem(pr["number"], message, (), fix))
    for pr in sorted(open_prs, key=lambda i: i["number"]):
        if message := _unlinked_unit_pr(pr):
            problems.append(LabelProblem(pr["number"], message, ()))
    return problems
