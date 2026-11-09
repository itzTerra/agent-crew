"""The run loop: each tick reads GitHub, tracks the live agents and starts new ones."""

import json
import os
import re
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crew.budget import effective_cap
from crew.config import Config
from crew.github import GitHub, GitHubError
from crew.graph import READY, RUNNING
from crew.inbox import owner_inbox
from crew.labels import FLOW, set_state
from crew.state import read_state
from crew.supervisor import worktrees
from crew.supervisor.events import append_event, new_run_id, start_log
from crew.supervisor.herdr import Herdr, HerdrError
from crew.supervisor.planner import Action, Kind, Live, Plan, plan
from crew.supervisor.snapshot import MARKER, Snapshot, owner_activity, take_snapshot
from crew.supervisor.trust import TrustError, trust_folder
from crew.supervisor.until import CONTINUE, FIVE_HOUR_FULL, RESET_SLACK, WIND_DOWN
from crew.usage import Usage, is_fresh, read_usage, usage_path

RUN_PATH = Path(".crew") / "run.json"  # gitignored; separate from state.json
START_TIMEOUT = 120  # seconds for herdr to see the agent
START_POLL = 2  # seconds between status checks while an agent starts
NUDGE = (
    "You stopped before the unit moved on. Continue the task. If you can't, use the safety "
    "valve in your brief: comment, label, push, stop."
)
STUCK_LINES = 20
GITHUB_RETRIES = 3
DECISION = "crew:owner-decision"
PR_KINDS = frozenset({"merge", "fix", "review"})
STOPPED = frozenset({"idle", "done", "blocked"})
NOT_STARTED = frozenset({"unknown"})
IDLE_END = "nothing to do: everything waits on the owner"
END_TIME = "end time reached"
INTERRUPTED = "stopped with Ctrl-C"
WIND_DOWN_POLL = 10  # seconds between status checks while agents wind down
WIND_DOWN_SETTLE = 60  # seconds an idle agent gets to pick up the wind-down prompt
PAUSE_KINDS = frozenset({"implement", "resume", "fix"})
# Text Claude Code shows when a usage limit stops a session.
LIMIT_TEXT = re.compile(
    r"usage limit|hit your (?:\w+ )?limit|limit reached|limit will reset", re.IGNORECASE
)
LIMIT_LINES = 15
LIMIT_RETRY = timedelta(minutes=30)  # when a limit shows but no reset time is known
# Passed into every agent's pane: herdr panes get herdr's environment, not crew run's.
FORWARD_PREFIXES = ("CREW_", "CLAUDE_")
FORWARD_EXCLUDED = ("CLAUDECODE", "CLAUDE_CODE_")


class RunError(Exception):
    """The run can't go on; reported as ``crew: error:``."""


@dataclass
class AgentRecord:
    """A live agent the run started (or adopted from ``run.json``)."""

    pane: str
    kind: Kind
    number: int
    issue: int | None
    role: str
    branch: str | None
    flow_at_start: list[str]
    started_at: str
    nudges: int = 0
    limited: bool = False
    cwd: str | None = None


@dataclass
class _Summary:
    started: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    stuck: list[str] = field(default_factory=list)
    paused: list[str] = field(default_factory=list)


def progress_state(snapshot: Snapshot, kind: str, number: int, config: Config) -> list[str]:
    """What must change on the target for its agent to count as finished.

    The flow labels plus ``crew:owner-decision``, or ``closed`` once the target left the open
    set. An implementer moving its unit from ready to in-progress hasn't finished; a followup
    has once the owner's answer is answered.
    """
    # A followup's target is a decision issue or a decision PR.
    item = snapshot.prs.get(number) if kind in PR_KINDS or kind == "followup" else None
    unit = None if item is not None or kind in PR_KINDS else snapshot.units.get(number)
    if item is None and unit is None:
        return ["closed"]
    names = {label["name"] for label in item.get("labels") or []} if item else unit.labels
    state = [name for name in FLOW if name in names]
    if kind in ("implement", "resume"):
        state = ["working" if name in (READY, RUNNING) else name for name in state]
    if DECISION in names:
        state.append(DECISION)
    if kind == "followup":
        if item is not None:
            answer = owner_activity(
                item.get("comments") or [], item.get("reviews") or [], item.get("commits") or [],
                config.owner_login, config.agent_login,
            ).kind  # fmt: skip
        else:
            decision = snapshot.decisions.get(number)
            answer = decision.kind if decision else "none"
        state.append(f"answer:{answer}")
    return state


def _is_crew_run(pid: int) -> bool:
    """Whether ``pid`` is a live ``crew run``. A reused pid of another program isn't one."""
    if not _pid_alive(pid):
        return False
    try:
        parts = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")
    except OSError:
        return True  # no /proc here: trust the pid
    return "run" in parts and any(part == "crew" or part.endswith("/crew") for part in parts)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class Supervisor:
    """Keeps up to ``max_agents`` crew agents busy until ``until``."""

    def __init__(
        self,
        root: Path,
        config: Config,
        github: GitHub,
        herdr: Herdr,
        until: datetime,
        cap: int | None,
        dry_run: bool,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        out: Callable[[str], None] = print,
        worktree=None,
        usage_file: Path | None = None,
        git_run=subprocess.run,
        trust=None,
        pane: str | None = None,
    ):
        self.root = root
        self.config = config
        self.github = github
        self.herdr = herdr
        self.until = until
        self.cap = cap
        self.dry_run = dry_run
        self.clock = clock
        self.sleep = sleep
        self.out = out
        self.worktree = worktree or worktrees.worktree_for
        self.usage_file = usage_file or usage_path(os.environ)
        self.git_run = git_run
        self.trust = trust or (lambda path: trust_folder(path, os.environ))
        self.agents: list[AgentRecord] = []
        self.paused: list[dict] = []
        self.workspace: str | None = None
        self.summary = _Summary()
        self.urls: dict[int, str] = {}
        self.next_sleep: float = config.poll_seconds
        self.window_reset_at: datetime | None = None  # while the 5-hour window is full
        self.pending_states: dict[int, str] = {}  # label moves a GitHub error cut short
        self.pane = pane
        self.run_id: str | None = None  # set once a real run starts; None means no events
        self._inbox_keys: set[tuple[int, str]] | None = None  # None until the baseline tick

    # --- one tick -------------------------------------------------------------------------

    def tick(self) -> str | None:
        """One pass: stop checks, snapshot, agents, housekeeping, plan, starts.

        Returns:
            None to keep going, else the reason the run ends.
        """
        now = self.clock()
        self.next_sleep = self.config.poll_seconds
        if now >= self.until:
            return END_TIME
        usage = read_usage(self.usage_file)
        fresh = is_fresh(usage, now)
        self._retry_label_moves()
        if fresh and usage is not None and usage.week_resets_at > now:
            # (A reading from before the weekly reset says nothing about this week.)
            cap = self.cap if self.cap is not None else self._effective_cap(now)
            if usage.week_percent >= cap:
                return f"budget cap reached ({usage.week_percent:g}% of {cap}%)"
        window_full = self._window_full(usage if fresh else None, now)
        snapshot = take_snapshot(self.github, self.config)
        self._remember_urls(snapshot)
        if self.dry_run:
            if window_full:
                self._log(self._window_message())
                return None
        else:
            stuck_before = len(self.summary.stuck)
            self._update_agents(snapshot, window_full, usage if fresh else None)
            if len(self.summary.stuck) != stuck_before:
                # Labels just changed: plan from GitHub as it is now, not as it was.
                snapshot = take_snapshot(self.github, self.config)
            self._report_inbox(snapshot)
            window_full = window_full or self._window_full(None, now)
            if window_full:
                self._log(self._window_message())
                self._write_run(alive=True)
                return None
            self._continue_limited()
        free = self.config.max_agents - len(self.agents)
        if not fresh:
            free = 1 if not self.agents else 0
        minutes_left = (self.until - now).total_seconds() / 60
        live = [Live(a.kind, a.number, a.issue) for a in self.agents]
        result = plan(snapshot, live, self.paused, self.config, max(free, 0), minutes_left)
        if not fresh:
            result.waiting.append(
                "no fresh usage reading: at most one agent starts until one appears"
            )
        if self.dry_run:
            self._print_plan(result)
        else:
            self._apply(result, snapshot)
            self._write_run(alive=True)
        if result.idle and not self.agents:
            return IDLE_END
        return None

    def _report_inbox(self, snapshot: Snapshot) -> None:
        """Append an ``item`` event for each owner-inbox entry that is new since the last tick.

        The first call only records the inbox as the baseline.

        @param snapshot: this tick's GitHub snapshot
        """
        items = owner_inbox(snapshot.units, list(snapshot.prs.values()))
        keys = {(item.number, item.ask) for item in items}
        previous, self._inbox_keys = self._inbox_keys, keys
        if previous is None or self.run_id is None:
            return
        for item in items:
            if (item.number, item.ask) not in previous:
                self._event(
                    "item", number=item.number, ask=item.ask, title=item.title, url=item.url
                )

    def _event(self, kind: str, **fields) -> None:
        append_event(
            self.root,
            {"run": self.run_id, "type": kind, "at": self.clock().astimezone(UTC).isoformat()}
            | fields,
        )

    def _effective_cap(self, now: datetime) -> int:
        return effective_cap(self.config, read_state(self.root), now)[0]

    def _window_full(self, usage: Usage | None, now: datetime) -> bool:
        """Whether the 5-hour window is used up; remembers its reset across stale readings."""
        if (
            usage is not None
            and usage.five_hour_percent >= FIVE_HOUR_FULL
            and usage.five_hour_resets_at > now
        ):
            self.window_reset_at = usage.five_hour_resets_at
        if self.window_reset_at is None:
            return False
        resume_at = self.window_reset_at + RESET_SLACK
        if now >= resume_at:
            return False
        self.next_sleep = min(self.config.poll_seconds, (resume_at - now).total_seconds())
        return True

    def _window_message(self) -> str:
        local = self.window_reset_at.astimezone().strftime("%H:%M") if self.window_reset_at else ""
        return f"waiting for the 5-hour window to reset at {local}"

    def _continue_limited(self) -> None:
        """After the window resets, tell every agent that stopped on the limit to go on."""
        self.window_reset_at = None
        for record in list(self.agents):
            if record.limited:
                record.limited = False
                if self.herdr.status(record.pane) == "blocked":
                    self._mark_stuck(record, "waits at a dialog it can't answer")
                    continue
                self.herdr.prompt(record.pane, CONTINUE)
                self._log(f"{record.kind} #{record.number}: limit reset; told to continue")

    def _remember_urls(self, snapshot: Snapshot) -> None:
        for number, unit in snapshot.units.items():
            self.urls[number] = unit.url
        for number, pr in snapshot.prs.items():
            self.urls[number] = pr.get("url", "")

    def _update_agents(
        self, snapshot: Snapshot, window_full: bool = False, usage: Usage | None = None
    ) -> None:
        for record in list(self.agents):
            status = self.herdr.status(record.pane)
            if status is None:
                self.agents.remove(record)
                self._pause_gone(record)
                self._log(f"{record.kind} #{record.number}: the agent is gone")
                continue
            if status not in STOPPED:
                continue
            now_state = progress_state(snapshot, record.kind, record.number, self.config)
            if now_state != record.flow_at_start:
                self.herdr.close(record.pane)
                self.agents.remove(record)
                self.summary.finished.append(self._label(record))
                self._log(f"{record.kind} #{record.number}: finished")
            elif window_full or record.limited or self._hit_limit(record, usage):
                if not record.limited:
                    self._log(f"{record.kind} #{record.number}: waiting for the usage reset")
                record.limited = True
            elif status == "blocked":
                # Never type into a dialog: Enter could approve what auto mode stopped to ask.
                self._mark_stuck(record, "waits at a dialog it can't answer")
            elif record.nudges == 0:
                self.herdr.prompt(record.pane, NUDGE)
                record.nudges = 1
                self._log(f"{record.kind} #{record.number}: stopped early; nudged")
            else:
                self._mark_stuck(record, "stopped twice without finishing")

    def _hit_limit(self, record: AgentRecord, usage: Usage | None) -> bool:
        """Whether the pane shows a usage-limit message; if so, remember when to go on."""
        lines = self.herdr.read(record.pane, LIMIT_LINES).splitlines()[-LIMIT_LINES:]
        if not any(LIMIT_TEXT.search(line) for line in lines):
            return False
        now = self.clock()
        if self.window_reset_at is None or self.window_reset_at + RESET_SLACK <= now:
            if usage is not None and usage.five_hour_resets_at > now:
                self.window_reset_at = usage.five_hour_resets_at
            else:
                self.window_reset_at = now + LIMIT_RETRY - RESET_SLACK
        return True

    def _pause_gone(self, record: AgentRecord) -> None:
        """A working agent that vanished leaves its unit to be resumed by the planner."""
        if record.kind not in PAUSE_KINDS:
            return
        number = record.issue or record.number
        if any(p.get("number") == number for p in self.paused):
            return
        self.paused.append({"number": number, "branch": record.branch})

    def _mark_stuck(self, record: AgentRecord, why: str) -> None:
        lines = self.herdr.read(record.pane, STUCK_LINES).rstrip("\n").splitlines()[-STUCK_LINES:]
        body = f"crew run: the agent {why}. Last output:\n\n```\n" + "\n".join(lines) + "\n```"
        # Reported on the unit's issue; PR work names the PR.
        target = record.issue if record.kind in PR_KINDS and record.issue else record.number
        if target != record.number:
            body = f"crew run: on PR #{record.number} ({self.urls.get(record.number, '')}), " + (
                body.removeprefix("crew run: ")
            )
        self._comment(target, body)
        self._set_state(record.number, "owner-stuck")
        self.herdr.close(record.pane)
        self.agents.remove(record)
        self.summary.stuck.append(self._label(record))
        self._log(f"{record.kind} #{record.number}: {why}; set crew:owner-stuck")

    def _set_state(self, number: int, state: str) -> None:
        """set_state, remembering a move that failed halfway so the next tick finishes it."""
        try:
            set_state(self.github, number, state)
        except GitHubError:
            self.pending_states[number] = state
            raise
        self.pending_states.pop(number, None)

    def _retry_label_moves(self) -> None:
        for number, state in list(self.pending_states.items()):
            self._set_state(number, state)
            self._log(f"#{number}: finished moving to {state}")

    def _comment(self, number: int, body: str) -> None:
        self.github.comment(number, f"{body}\n\n{MARKER}")

    def _apply(self, result: Plan, snapshot: Snapshot) -> None:
        for item in result.housekeeping:
            self._set_state(item.number, item.state)
            if item.comment:
                self._comment(item.number, item.comment)
            self._log(f"#{item.number}: set {item.state}")
        for action in result.actions:
            self._start(action, snapshot)

    def _start(self, action: Action, snapshot: Snapshot) -> None:
        cwd = self.worktree(self.root, action.branch, action.detach) if action.branch else self.root
        if action.branch:
            # Every worktree is a new git root to Claude Code, which would stop the agent at
            # its folder-trust dialog. The run trusts only the worktree it just made.
            try:
                self.trust(cwd)
            except TrustError as exc:
                self._log(f"could not pre-trust {cwd}: {exc}")
        pane = self._open_tab(cwd, f"{action.kind} #{action.number}")
        record = AgentRecord(
            pane=pane,
            kind=action.kind,
            number=action.number,
            issue=action.issue,
            role=action.role,
            branch=action.branch,
            flow_at_start=progress_state(snapshot, action.kind, action.number, self.config),
            started_at=self.clock().isoformat(),
            cwd=str(cwd),
        )
        # Tracked before it runs, so an interrupt or error from here on winds it down too.
        self.agents.append(record)
        model = ["--model", action.model] if action.model else []
        command = shlex.join(
            ["crew", "agent", action.role, "--auto", "--root", str(cwd), *model, action.prompt]
        )
        self.herdr.run_command(pane, command)
        deadline = self.clock().timestamp() + START_TIMEOUT
        while True:
            status = self.herdr.status(pane)
            if status is not None and status not in NOT_STARTED:
                break
            if self.clock().timestamp() >= deadline:
                lines = [line for line in self.herdr.read(pane).splitlines() if line.strip()]
                self.herdr.close(pane)
                self.agents.remove(record)
                last = lines[-1].strip() if lines else "no output"
                raise RunError(f"agent for {action.kind} #{action.number} did not start: {last}")
            self.sleep(START_POLL)
        self.paused = [p for p in self.paused if p.get("number") != (action.issue or action.number)]
        self.summary.started.append(self._label(record))
        self._log(f"{action.kind} #{action.number}: started in {cwd}")

    def _open_tab(self, cwd: Path, label: str) -> str:
        """A tab in the run's workspace; a workspace that no longer exists is replaced once."""
        env = self._agent_env()
        if self.workspace is not None:
            try:
                return self.herdr.open_tab(self.workspace, cwd, label, env)
            except HerdrError as exc:
                self._log(f"herdr workspace {self.workspace} unusable ({exc}); opening a new one")
        self.workspace = self.herdr.create_workspace(self.root, "crew run")
        return self.herdr.open_tab(self.workspace, cwd, label, env)

    def _agent_env(self) -> dict[str, str]:
        """crew and Claude settings of this run, which herdr panes don't inherit."""
        env = {
            key: value
            for key, value in os.environ.items()
            if key.startswith(FORWARD_PREFIXES) and not key.startswith(FORWARD_EXCLUDED)
        }
        env["CREW_USAGE_FILE"] = str(self.usage_file)
        return env

    def _print_plan(self, result: Plan) -> None:
        for item in result.housekeeping:
            extra = f" — {item.comment}" if item.comment else ""
            self._log(f"housekeeping: #{item.number} → {item.state}{extra}")
        for action in result.actions:
            self._log(f"start: {action.kind} #{action.number} ({action.role}): {action.prompt}")
        for line in result.waiting:
            self._log(f"waiting: {line}")
        if not (result.housekeeping or result.actions):
            self._log("nothing to start")

    # --- run state ------------------------------------------------------------------------

    def _run_path(self) -> Path:
        return self.root / RUN_PATH

    def _read_run(self) -> dict:
        try:
            data = json.loads(self._run_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_run(self, alive: bool, keep_agents: bool = False) -> None:
        data = {
            "until": self.until.isoformat(),
            "cap": self.cap,
            "workspace": self.workspace,
            "paused": self.paused,
            "window_reset_at": self.window_reset_at.isoformat() if self.window_reset_at else None,
            "run_id": self.run_id,
            "pane": self.pane,
        }
        if alive:
            data = {"pid": os.getpid(), **data}
        if alive or keep_agents:
            data["agents"] = [asdict(a) for a in self.agents]
        path = self._run_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def _adopt(self) -> None:
        data = self._read_run()
        pid = data.get("pid")
        if not self.dry_run and isinstance(pid, int) and pid != os.getpid() and _is_crew_run(pid):
            raise RunError(f"a run is already active (pid {pid}); if it isn't, delete {RUN_PATH}")
        self.workspace = data.get("workspace") or None
        try:
            reset = datetime.fromisoformat(str(data.get("window_reset_at")))
            if reset.tzinfo and reset > self.clock():
                self.window_reset_at = reset
        except ValueError:
            pass
        self.paused = [p for p in data.get("paused") or [] if isinstance(p, dict)]
        for raw in data.get("agents") or []:
            try:
                record = AgentRecord(**raw)
            except TypeError:
                continue
            known = {agent.pane for agent in self.agents}
            if record.pane in known:
                continue
            if self.herdr.status(record.pane) is not None:
                self.agents.append(record)
                self._log(f"{record.kind} #{record.number}: adopted the live agent")
            else:
                self._pause_gone(record)

    # --- the loop -------------------------------------------------------------------------

    def run(self, once: bool = False) -> int:
        """Tick until an end reason; returns the exit code (0).

        Any end, Ctrl-C and errors included, winds the agents down first. ``once`` runs a
        single tick and leaves its agents running for the next run to adopt.

        Raises:
            RunError: the run could not go on.
        """
        self._adopt()
        if not self.dry_run:
            if not once:  # a single tick isn't a run anyone watches: no id, no events
                self.run_id = new_run_id(os.getpid(), self.clock())
                start_log(self.root, self.run_id, self.clock(), self.until, self.pane)
            self._write_run(alive=True)
        failures = 0
        reason = None
        try:
            while True:
                try:
                    reason = self.tick()
                    failures = 0
                except GitHubError as exc:
                    failures += 1
                    self._log(f"GitHub error ({failures} of {GITHUB_RETRIES}): {exc}")
                    if failures >= GITHUB_RETRIES:
                        raise RunError(str(exc)) from None
                if reason or once:
                    break
                self.sleep(self.next_sleep)
        except KeyboardInterrupt:
            reason = INTERRUPTED
        except BaseException as exc:
            if not self.dry_run:
                self._wind_down(f"error: {exc}")
            raise
        if self.dry_run:
            if reason:
                self._log(f"run would end: {reason}")
            return 0
        if reason:
            self._wind_down(reason)
        else:
            self._write_run(alive=False, keep_agents=True)
        return 0

    def _wind_down(self, reason: str) -> None:
        """Tell every agent to commit and push, wait for them, close them, record the pauses.

        An agent counts as done when it is gone, or stopped (after picking up the prompt) with
        its worktree clean and pushed. A second Ctrl-C, or a herdr error, cuts the wait short
        but still closes and records every agent.
        """
        remaining = list(self.agents)
        try:
            self._wait_for_wind_down(remaining)
        except (KeyboardInterrupt, HerdrError) as exc:
            self._log(f"wind-down cut short ({type(exc).__name__})")
        unclosed = []
        for record in remaining:
            try:
                self.herdr.close(record.pane)
            except (KeyboardInterrupt, HerdrError):
                unclosed.append(record)
            self._maybe_pause(record)
        self.agents = unclosed  # kept in run.json so the next run adopts them
        if self.run_id is not None:  # before run.json says the run is over: status never reads none
            self._event(
                "end",
                reason=reason,
                error=reason.startswith("error: "),
                pane=self.pane,
                started=self.summary.started,
                finished=self.summary.finished,
                stuck=self.summary.stuck,
                paused=self.summary.paused,
            )
        self._write_run(alive=False, keep_agents=bool(unclosed))
        self._print_summary(reason)

    def _wait_for_wind_down(self, records: list[AgentRecord]) -> None:
        for record in records:
            if self.herdr.status(record.pane) in ("working", "idle", "done"):
                self.herdr.prompt(record.pane, WIND_DOWN)
        start = self.clock()
        deadline = start + timedelta(minutes=self.config.stop_grace_minutes)
        waiting = list(records)
        seen_working: set[str] = set()
        while waiting and self.clock() < deadline:
            settled = (self.clock() - start).total_seconds() >= WIND_DOWN_SETTLE
            for record in list(waiting):
                status = self.herdr.status(record.pane)
                if status in ("working", "unknown"):
                    seen_working.add(record.pane)
                elif status is None:
                    waiting.remove(record)
                elif (record.pane in seen_working or settled) and self._pushed(record):
                    waiting.remove(record)
            if waiting:
                self.sleep(WIND_DOWN_POLL)

    def _pushed(self, record: AgentRecord) -> bool:
        """Whether the agent's worktree is clean and its branch is on the remote."""
        if record.kind not in PAUSE_KINDS or not record.cwd or not record.branch:
            return True

        def git(*args: str) -> subprocess.CompletedProcess | None:
            try:
                return self.git_run(
                    ["git", "-C", record.cwd, *args], capture_output=True, text=True, check=False
                )
            except OSError:
                return None

        status = git("status", "--porcelain")
        if status is None or status.returncode != 0 or status.stdout.strip():
            return False
        for upstream in (f"refs/remotes/origin/{record.branch}", "refs/remotes/origin/main"):
            heads = git("rev-parse", "HEAD", upstream)
            if heads is not None and heads.returncode == 0:
                lines = heads.stdout.split()
                return len(lines) == 2 and lines[0] == lines[1]
        return False

    def _maybe_pause(self, record: AgentRecord) -> None:
        if record.kind not in PAUSE_KINDS:
            return
        number = record.issue or record.number
        try:
            labels = self.github.labels_of(number)
        except GitHubError:
            return
        if RUNNING in labels:
            branch = record.branch
            self.paused = [p for p in self.paused if p.get("number") != number]
            self.paused.append({"number": number, "branch": branch})
            url = self.urls.get(number, "")
            self.summary.paused.append(f"#{number}" + (f" {url}" if url else ""))

    def _print_summary(self, reason: str) -> None:
        self._log(f"run ended: {reason}")
        for title, items in (
            ("Started", self.summary.started),
            ("Finished", self.summary.finished),
            ("Stuck", self.summary.stuck),
            ("Paused", self.summary.paused),
        ):
            if items:
                self.out(f"{title}:")
                for item in items:
                    self.out(f"  {item}")

    # --- helpers --------------------------------------------------------------------------

    def _label(self, record: AgentRecord) -> str:
        url = self.urls.get(record.number, "")
        return f"{record.kind} #{record.number}" + (f" {url}" if url else "")

    def _log(self, message: str) -> None:
        self.out(f"{self.clock().astimezone().strftime('%H:%M')} {message}")
