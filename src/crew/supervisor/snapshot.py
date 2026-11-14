"""One look at GitHub per tick: open units, open PRs in detail, and the owner's activity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from crew.bets import Bet, unsplit_bets
from crew.config import Config
from crew.github import GitHub
from crew.graph import Unit, build_units
from crew.labels import AssigneeDrift, LabelProblem, Logins, assignee_drift, label_problems

DECISION = "crew:owner-decision"
# Hidden in every comment crew run posts. crew run uses whatever gh login it runs under,
# often the owner's, so its own comments must never read as the owner's (or an agent's) words.
MARKER = "<!-- crew run -->"
FAILED = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "ERROR", "STARTUP_FAILURE"}
)
STATUS_PENDING = frozenset({"PENDING", "EXPECTED"})


@dataclass(frozen=True)
class OwnerActivity:
    """The owner's latest unanswered action on an issue or PR."""

    kind: Literal["approved", "feedback", "none"]
    at: str  # ISO time of the owner's latest unanswered action, "" for none


@dataclass
class Snapshot:
    """What the planner sees of GitHub."""

    units: dict[int, Unit]
    prs: dict[int, dict]  # open PRs, pr_detail dicts
    decisions: dict[int, OwnerActivity]  # open issues labeled crew:owner-decision
    problems: list[LabelProblem] = field(default_factory=list)
    unsplit: dict[int, Bet] = field(default_factory=dict)  # merged pitch PRs with no units yet
    drift: list[AssigneeDrift] = field(default_factory=list)  # the planner never reads it


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _login(item: dict) -> str:
    return str((item.get("author") or {}).get("login") or "").casefold()


def owner_activity(
    comments: list[dict],
    reviews: list[dict],
    commits: list[dict],
    owner_login: str,
    agent_login: str,
) -> OwnerActivity:
    """The owner's latest action that no agent comment, review or commit has answered yet.

    The answer mark is the latest of the comments and reviews by ``agent_login`` and the
    commits; the owner's comments and non-approving reviews after it are unanswered feedback.
    An approval stands until a later commit or a later owner comment or review; an agent's
    review doesn't void it. The later of the standing approval and the latest unanswered
    feedback wins. Comments carrying ``MARKER`` are ignored. Logins compare
    case-insensitively. When the run started plays no part.
    """
    owner, agent = owner_login.casefold(), agent_login.casefold()
    events = [
        (_when(c.get("createdAt")), c, None)
        for c in comments
        if MARKER not in str(c.get("body") or "")
    ]
    events += [
        (_when(r.get("submittedAt")), r, r.get("state"))
        for r in reviews
        if r.get("state") != "PENDING"
    ]
    commit_times = [at for c in commits if (at := _when(c.get("committedDate")))]
    agent_times = [at for at, item, _ in events if at and _login(item) == agent]
    mark = max([*agent_times, *commit_times], default=None)
    owner_events = [(at, item, state) for at, item, state in events if at and _login(item) == owner]
    feedback = [e for e in owner_events if e[2] != "APPROVED"]
    unanswered = [e for e in feedback if mark is None or e[0] > mark]
    # An approval stands until new commits arrive or the owner says something after it;
    # an agent's review or reply doesn't answer it.
    last_commit = max(commit_times, default=None)
    approvals = [
        e
        for e in owner_events
        if e[2] == "APPROVED"
        and (last_commit is None or e[0] > last_commit)
        and not any(f[0] > e[0] for f in feedback)
    ]
    latest_feedback = max(unanswered, key=lambda e: e[0], default=None)
    latest_approval = max(approvals, key=lambda e: e[0], default=None)
    if latest_approval and (latest_feedback is None or latest_approval[0] > latest_feedback[0]):
        return OwnerActivity("approved", latest_approval[1].get("submittedAt") or "")
    if latest_feedback:
        _, item, state = latest_feedback
        stamp = item.get("submittedAt") if state is not None else item.get("createdAt")
        return OwnerActivity("feedback", stamp or "")
    return OwnerActivity("none", "")


def _check_state(check: dict) -> tuple[str, str]:
    """(name, pass|fail|pending) of one statusCheckRollup entry."""
    if check.get("__typename") == "StatusContext" or "context" in check:
        name, state = str(check.get("context") or ""), str(check.get("state") or "").upper()
        if state in FAILED:
            return name, "fail"
        return name, "pending" if state in STATUS_PENDING or not state else "pass"
    name = str(check.get("name") or "")
    if str(check.get("conclusion") or "").upper() in FAILED:
        return name, "fail"
    if str(check.get("status") or "").upper() != "COMPLETED":
        return name, "pending"
    return name, "pass"


def checks_state(pr: dict, required: list[str]) -> Literal["pass", "fail", "pending", "none"]:
    """The PR's CI state, counting only the ``required`` checks when any are named.

    A required check that hasn't reported yet is pending.
    """
    states = [_check_state(check) for check in pr.get("statusCheckRollup") or []]
    if required:
        names = set(required)
        states = [(name, state) for name, state in states if name in names]
        if {name for name, _ in states} != names:
            return "fail" if any(state == "fail" for _, state in states) else "pending"
    if not states:
        return "none"
    if any(state == "fail" for _, state in states):
        return "fail"
    if any(state == "pending" for _, state in states):
        return "pending"
    return "pass"


def failed_checks(pr: dict, required: list[str]) -> list[str]:
    """Names of the counted checks that failed."""
    names = set(required)
    return [
        name
        for check in pr.get("statusCheckRollup") or []
        for name, state in [_check_state(check)]
        if state == "fail" and (not names or name in names)
    ]


def take_snapshot(github: GitHub, config: Config) -> Snapshot:
    """Read the open issues and PRs, each open PR in detail, the answers to owner asks, and
    the bets no unit links yet.

    Closed issues are read only when an open one doesn't already link every bet. Label
    problems are found among open items only: closed ones aren't acted on. Assignee drift
    covers the open items and the merged PRs.
    """
    issues = github.list_issues("open")
    units = build_units(issues)
    prs = {pr["number"]: github.pr_detail(pr["number"]) for pr in github.list_prs("open")}
    decisions = {
        number: owner_activity(
            github.issue_comments(number), [], [], config.owner_login, config.agent_login
        )
        for number, unit in sorted(units.items())
        if DECISION in unit.labels
    }
    problems = label_problems(issues, [], list(prs.values()), [])
    merged = github.list_prs("merged")
    drift = assignee_drift(issues, [], list(prs.values()), merged, Logins.of(config))
    bets = unsplit_bets(merged, issues)
    if bets:
        bets = unsplit_bets(merged, issues + github.list_issues("closed"))
    return Snapshot(
        units=units,
        prs=prs,
        decisions=decisions,
        problems=problems,
        unsplit={bet.number: bet for bet in bets},
        drift=drift,
    )
