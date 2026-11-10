"""Turn a GitHub snapshot and the live agents into the next actions. Pure: no I/O."""

import re
from dataclasses import dataclass, field
from typing import Literal

from crew.config import Config
from crew.graph import READY, RUNNING, ready_report, rough_order
from crew.labels import FLOW
from crew.supervisor.snapshot import Snapshot, checks_state, failed_checks, owner_activity

Kind = Literal["merge", "fix", "review", "followup", "resume", "implement", "split", "refine"]
DECISION = "crew:owner-decision"
OWNER_FACING = "crew:owner-facing"
DESIGN = "crew:design"
SLUG_MAX = 40
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Kinds whose agent holds the unit's issue as running work.
WORKING_KINDS = frozenset({"implement", "resume", "fix"})


@dataclass(frozen=True)
class Action:
    """One agent to start."""

    kind: Kind
    number: int  # the issue, or the PR for review, merge and fix
    issue: int | None  # the unit's issue when number is a PR
    role: str  # crew agent role
    model: str | None  # None: the agent definition's model
    prompt: str
    branch: str | None  # worktree branch; None: run in the main checkout
    detach: bool = False  # review worktrees are detached


@dataclass(frozen=True)
class Housekeeping:
    """A label change (and comment) the supervisor makes itself."""

    number: int
    state: str  # for set_state
    comment: str | None


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    housekeeping: list[Housekeeping] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)  # why more doesn't start
    idle: bool = False  # nothing to do now or later without the owner


@dataclass(frozen=True)
class Live:
    """What the planner needs about a live agent."""

    kind: Kind
    number: int
    issue: int | None


def slug(title: str) -> str:
    """Lowercase, runs of non-alphanumerics as ``-``, at most 40 characters, cut at a ``-``."""
    text = _NON_ALNUM.sub("-", title.lower()).strip("-")
    if len(text) <= SLUG_MAX:
        return text
    head = text[: SLUG_MAX + 1]
    cut = head.rsplit("-", 1)[0] if "-" in head else head
    return cut[:SLUG_MAX].strip("-")


def unit_branch(number: int, title: str) -> str:
    """The unit's branch: ``unit/<n>-<slug>``."""
    return f"unit/{number}-{slug(title)}"


def _names(item: dict) -> set[str]:
    return {label["name"] for label in item.get("labels") or []}


def _flow(names: set[str]) -> str | None:
    return next((name for name in FLOW if name in names), None)


def _worker(*label_sets: set[str]) -> str:
    """The role that builds a unit: the designer for design work, else the implementer."""
    return "designer" if any(DESIGN in labels for labels in label_sets) else "implementer"


def plan(
    snapshot: Snapshot,
    live: list[Live],
    paused: list[dict],
    config: Config,
    free_slots: int,
    minutes_left: float,
) -> Plan:
    """The actions to start now, finishing work before starting new work.

    Order: housekeeping (owner feedback, red CI), then merge, fix, review, followup, resume,
    implement, split and refine actions, cut at ``free_slots``. A split turns one merged pitch
    PR that no unit links yet into units, one bet at a time. Each target gets at most one action;
    targets with a live agent or a label problem are skipped. An action whose estimate exceeds
    ``minutes_left`` is dropped. Units or PRs labeled ``crew:design`` are built (implement,
    resume, fix) and followed up by the designer instead of the implementer and architect.
    """
    result = Plan()
    occupied = {n for agent in live for n in (agent.number, agent.issue) if n is not None}
    problems = {p.number: p.message for p in snapshot.problems}
    handled: set[int] = set()
    candidates: list[Action] = []
    pending_checks = False

    def blocked(number: int, issue: int | None) -> bool:
        for n in (number, issue):
            if n is not None and n in occupied:
                result.waiting.append(f"#{number}: an agent is working on it")
                return True
            if n is not None and n in problems:
                result.waiting.append(f"#{number}: label problem: {problems[n]}")
                return True
        return False

    prs = [snapshot.prs[n] for n in sorted(snapshot.prs)]
    for pr in prs:
        number, names = pr["number"], _names(pr)
        linked = [ref["number"] for ref in pr.get("closingIssuesReferences") or []]
        issue = linked[0] if linked else None
        unit = snapshot.units.get(issue) if issue is not None else None
        flow = _flow(names)
        activity = owner_activity(
            pr.get("comments") or [],
            pr.get("reviews") or [],
            pr.get("commits") or [],
            config.owner_login,
            config.agent_login,
        )
        checks = checks_state(pr, config.ci_checks)
        url = pr.get("url", "")
        worker = _worker(names, unit.labels if unit else set())
        if DECISION in names:
            if activity.kind != "none" and not blocked(number, issue):
                candidates.append(_followup(number, url, worker == "designer"))
                handled.add(number)
            continue
        if activity.kind == "approved" and flow == "crew:changes-requested":
            # The owner approved after the feedback that set changes-requested: back to them.
            if not blocked(number, issue):
                result.housekeeping.append(Housekeeping(number, "owner-accept", None))
            continue
        if activity.kind == "feedback" and flow != "crew:changes-requested":
            if not blocked(number, issue):
                result.housekeeping.append(Housekeeping(number, "changes-requested", None))
            continue
        if flow == "crew:in-review" and checks == "fail":
            if not blocked(number, issue):
                names_failed = ", ".join(failed_checks(pr, config.ci_checks))
                comment = f"CI failed: {names_failed}. (crew run)"
                result.housekeeping.append(Housekeeping(number, "changes-requested", comment))
            continue
        branch = pr.get("headRefName")
        if flow == "crew:owner-accept" and activity.kind == "approved":
            if not blocked(number, issue):
                prompt = (
                    f"Use crew:merge on PR #{number} ({url}). The owner approved it; read their "
                    "comments first, and if any asks for a change, set changes-requested "
                    "instead of merging."
                )
                candidates.append(
                    Action("merge", number, issue, "implementer", None, prompt, branch)
                )
        elif flow == "crew:changes-requested":
            if not blocked(number, issue):
                prompt = (
                    f"Use crew:implement on issue #{issue if issue is not None else number}: "
                    f"changes are requested on PR #{number} ({url})."
                )
                candidates.append(Action("fix", number, issue, worker, None, prompt, branch))
        elif flow == "crew:in-review":
            if checks == "pending":
                pending_checks = True
                result.waiting.append(f"#{number}: waiting for its checks")
            elif not blocked(number, issue):
                facing = OWNER_FACING in names or bool(unit and OWNER_FACING in unit.labels)
                prompt = f"Use crew:review on PR #{number} ({url})."
                model = None if facing else "sonnet"
                candidates.append(
                    Action("review", number, issue, "reviewer", model, prompt, branch, True)
                )

    for number, activity in sorted(snapshot.decisions.items()):
        if activity.kind != "none" and number not in handled and not blocked(number, None):
            candidates.append(_followup(number, snapshot.units[number].url))

    paused_numbers = set()
    for entry in paused:
        number, branch = entry.get("number"), entry.get("branch")
        unit = snapshot.units.get(number)
        if unit is None or RUNNING not in unit.labels:
            continue
        paused_numbers.add(number)
        if not blocked(number, None):
            prompt = (
                f"Use crew:implement on issue #{number}: resume the work pushed on branch "
                f"{branch} in an earlier run."
            )
            role = _worker(unit.labels)
            candidates.append(Action("resume", number, None, role, None, prompt, branch))

    running = sorted({agent.issue or agent.number for agent in live if agent.kind in WORKING_KINDS})
    with_pr = {ref["number"] for pr in prs for ref in pr.get("closingIssuesReferences") or []}
    busy = sorted(
        number
        for number, unit in snapshot.units.items()
        if number not in running and (number in with_pr or RUNNING in unit.labels)
    )
    picks, skipped = ready_report(snapshot.units, running, len(live) + free_slots, busy)
    result.waiting += [f"#{item.number}: {item.reason}" for item in skipped]
    for number in picks:
        unit = snapshot.units[number]
        if blocked(number, None):
            continue
        role = _worker(unit.labels)
        prompt = f"Use crew:implement on issue #{number} ({unit.url})."
        if role == "designer":
            prompt += " It is design work: deliver the alternatives as mockups per your brief."
        branch = unit_branch(number, unit.title)
        candidates.append(Action("implement", number, None, role, None, prompt, branch))

    if not any(agent.kind == "split" for agent in live):
        for number, bet in sorted(snapshot.unsplit.items()):
            if number in occupied:
                continue
            prompt = (
                f"The owner bet on pitch {bet.pitch} by merging PR #{number} ({bet.url}). Split "
                "it into units per your brief; each unit's Bet links the pitch file."
            )
            candidates.append(Action("split", number, None, "architect", None, prompt, None))
            break

    ready_left = sum(1 for u in snapshot.units.values() if READY in u.labels) - len(picks)
    refining = any(agent.kind == "refine" for agent in live)
    if ready_left < config.refine_ahead and not refining:
        for number in rough_order(snapshot.units):
            if number in occupied or number in problems:
                continue
            prompt = f"Use crew:refine on issue #{number} only ({snapshot.units[number].url})."
            candidates.append(Action("refine", number, None, "architect", None, prompt, None))
            break

    waiting_on_capacity = False
    for action in candidates:
        minutes = config.estimates[action.kind]
        if minutes > minutes_left:
            result.waiting.append(
                f"not enough time for {action.kind} #{action.number} ({minutes} min)"
            )
            waiting_on_capacity = True
        elif len(result.actions) >= free_slots:
            result.waiting.append(f"no free agent slot for {action.kind} #{action.number}")
            waiting_on_capacity = True
        else:
            result.actions.append(action)

    result.idle = not (
        result.actions or result.housekeeping or pending_checks or waiting_on_capacity
    )
    return result


def _followup(number: int, url: str, design: bool = False) -> Action:
    if design:
        prompt = (
            f"The owner answered on #{number} ({url}). Continue from their answer: if they chose "
            "an alternative, record the chosen design per your brief; otherwise revise the "
            "alternatives."
        )
        return Action("followup", number, None, "designer", None, prompt, None)
    prompt = (
        f"The owner answered on #{number} ({url}). Continue from their answer: for a unit, use "
        f"crew:refine on issue #{number} only; for a decision document, write the ADR per your "
        "brief."
    )
    return Action("followup", number, None, "architect", None, prompt, None)
