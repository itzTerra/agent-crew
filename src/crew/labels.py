"""The crew label set. Every label starts with ``crew:``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crew.config import Config
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
# What an owner ask asks: ``crew:owner-<ask>``. ``crew:owner-facing`` is a kind, not an ask.
OWNER_PREFIX = "crew:owner-"
OWNER_ASKS = ("accept", "decision", "stuck", "proposal")
# The asks that stack on a flow label rather than being one.
STACKED_ASKS = ("decision", "proposal")
# The flow labels under which the agents hold an item.
AGENT_HELD = ("crew:in-progress", "crew:in-review", "crew:changes-requested")
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


def logins_of(item: dict) -> set[str]:
    """The assignee logins on an issue or PR as gh or the REST API returns it."""
    return {person["login"] for person in item.get("assignees") or []}


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


@dataclass(frozen=True)
class Logins:
    """The two GitHub logins crew assigns: the owner's and the agents'."""

    owner: str
    agent: str

    @classmethod
    def of(cls, config: Config) -> Logins:
        return cls(config.owner_login, config.agent_login)


def wanted_assignees(labels: set[str], logins: Logins, closed: bool = False) -> set[str] | None:
    """The managed logins an item with ``labels`` should be assigned to.

    None for an item with no crew label at all (crew leaves its assignees alone); nobody
    once it is closed or merged; the owner while any owner ask is on it; the agents while
    they hold it; nobody otherwise.
    """
    if not any(name.startswith("crew:") for name in labels):
        return None
    if closed:
        return set()
    if any(f"{OWNER_PREFIX}{ask}" in labels for ask in OWNER_ASKS):
        return {logins.owner}
    if any(name in labels for name in AGENT_HELD):
        return {logins.agent}
    return set()


def assignee_change(
    labels: set[str], assignees: set[str], logins: Logins, closed: bool = False
) -> tuple[list[str], list[str]]:
    """The (add, remove) that bring an item's managed assignees in line with its labels.

    Only the two managed logins are ever added or removed; anyone else assigned stays.
    Logins compare case-insensitively, as on GitHub: an add uses the config's spelling, a
    remove the spelling GitHub returned.
    """
    wanted = wanted_assignees(labels, logins, closed)
    if wanted is None:
        return [], []
    present = {login.casefold() for login in assignees}
    managed = {logins.owner.casefold(), logins.agent.casefold()}
    keep = {login.casefold() for login in wanted}
    add = sorted(login for login in wanted if login.casefold() not in present)
    remove = sorted(login for login in assignees if login.casefold() in managed - keep)
    return add, remove


def sync_assignees(
    github: GitHub,
    number: int,
    labels: set[str],
    assignees: set[str],
    logins: Logins,
    closed: bool = False,
) -> str | None:
    """Set an item's managed assignees from its labels; a warning if GitHub dropped one."""
    add, remove = assignee_change(labels, assignees, logins, closed)
    if not (add or remove):
        return None
    dropped = github.set_assignees(number, add, remove)
    return refused_warning(number, dropped)


def refused_warning(number: int, dropped: set[str]) -> str | None:
    """The warning for logins GitHub would not assign on ``number``, or None."""
    if not dropped:
        return None
    return f"#{number}: GitHub did not assign {', '.join(sorted(dropped))}; is it a collaborator?"


@dataclass
class StateResult:
    """What ``set_state`` moved, and the assignments GitHub refused along the way."""

    numbers: list[int]
    warnings: list[str]


def set_state(github: GitHub, number: int, state: str, logins: Logins) -> StateResult:
    """Move an issue and its open PRs (or a PR and its issues) to one flow state together.

    Every issue an affected open PR closes moves too, so a PR that closes several issues
    keeps them all in its state whichever of them ``number`` names.

    Each item loses the flow labels it carries and gains ``crew:<state>``; other labels stay.
    ``done`` removes every flow label, from the issue's merged PRs too. Each item's managed
    assignees then follow its new labels (see ``wanted_assignees``); ``done`` unassigns both.

    Args:
        github: the repo's client.
        number: an issue or a PR. A number found among the open PRs (or, for ``done``,
            the merged ones) is a PR; any other number is an issue.
        state: one of ``STATES``.
        logins: the owner's and the agents' logins, to assign.

    Returns:
        The numbers the state was applied to, ascending, and a warning per item where
        GitHub refused an assignment (the label change still landed).

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
    warnings = []
    for target in sorted(targets):
        current, assignees = github.item_state(target)
        remove = [name for name in _flow_of(current) if name != wanted]
        add = [wanted] if wanted and wanted not in current else []
        if add or remove:
            github.set_labels(target, add, remove)
        final = (current - set(remove)) | set(add)
        if state == DONE:
            # Finished work waits on nobody. The labels it had decide whether crew manages
            # it, since done may have taken its only crew label.
            warning = sync_assignees(github, target, current, assignees, logins, closed=True)
        else:
            warning = sync_assignees(github, target, final, assignees, logins)
        if warning:
            warnings.append(warning)
    return StateResult(sorted(targets), warnings)


def set_ask(github: GitHub, number: int, ask: str, on: bool, logins: Logins) -> str | None:
    """Raise (``on``) or clear ``crew:owner-<ask>`` on one item, then sync its assignees.

    Only the asks that stack on a flow label go through here; ``accept`` and ``stuck`` are
    states (see ``set_state``).

    Returns:
        A warning if GitHub refused an assignment (the label change still landed), else None.

    Raises:
        ValueError: ``ask`` is not one of ``STACKED_ASKS`` (nothing is changed).
    """
    if ask not in STACKED_ASKS:
        raise ValueError(f"unknown ask {ask!r}; choose one of {', '.join(STACKED_ASKS)}")
    label = f"{OWNER_PREFIX}{ask}"
    current, assignees = github.item_state(number)
    if on and label not in current:
        github.set_labels(number, [label], [])
    elif not on and label in current:
        github.set_labels(number, [], [label])
    final = current | {label} if on else current - {label}
    return sync_assignees(github, number, final, assignees, logins)


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


@dataclass(frozen=True)
class AssigneeDrift:
    """Managed assignees on one issue or PR that disagree with its labels.

    Never a ``LabelProblem``: the planner holds back units with label problems, and a
    refused assignment must not stall a run.
    """

    number: int
    add: tuple[str, ...]
    remove: tuple[str, ...]

    @property
    def message(self) -> str:
        """``assign <logins>, unassign <logins>``, leaving out an empty half."""
        parts = [f"assign {', '.join(self.add)}"] if self.add else []
        parts += [f"unassign {', '.join(self.remove)}"] if self.remove else []
        return ", ".join(parts)


def assignee_drift(
    open_issues: list[dict],
    closed_issues: list[dict],
    open_prs: list[dict],
    merged_prs: list[dict],
    logins: Logins,
) -> list[AssigneeDrift]:
    """Every item whose managed assignees differ from ``wanted_assignees``, by number.

    Closed issues and merged PRs count as closed. Items with no crew label are left out.
    """
    items = [(item, False) for item in [*open_issues, *open_prs]]
    items += [(item, True) for item in [*closed_issues, *merged_prs]]
    drift = []
    for item, closed in items:
        add, remove = assignee_change(_names(item), logins_of(item), logins, closed)
        if add or remove:
            drift.append(AssigneeDrift(item["number"], tuple(add), tuple(remove)))
    return sorted(drift, key=lambda d: d.number)
