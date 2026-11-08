"""The run loop: each tick reads GitHub, tracks the live agents and starts new ones."""

import json
import os
import shlex
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from crew.config import Config
from crew.github import GitHub, GitHubError
from crew.graph import READY, RUNNING
from crew.labels import FLOW, set_state
from crew.supervisor import worktrees
from crew.supervisor.herdr import Herdr
from crew.supervisor.planner import Action, Kind, Live, Plan, plan
from crew.supervisor.snapshot import Snapshot, owner_activity, take_snapshot
from crew.usage import is_fresh, read_usage, usage_path

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


@dataclass
class _Summary:
    started: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    stuck: list[str] = field(default_factory=list)


def progress_state(snapshot: Snapshot, kind: str, number: int, config: Config) -> list[str]:
    """What must change on the target for its agent to count as finished.

    The flow labels plus ``crew:owner-decision``, or ``closed`` once the target left the open
    set. An implementer moving its unit from ready to in-progress hasn't finished; a followup
    has once the owner's answer is answered.
    """
    item = snapshot.prs.get(number) if kind in PR_KINDS else None
    unit = None if kind in PR_KINDS else snapshot.units.get(number)
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
        self.agents: list[AgentRecord] = []
        self.paused: list[dict] = []
        self.workspace: str | None = None
        self.summary = _Summary()
        self.urls: dict[int, str] = {}

    # --- one tick -------------------------------------------------------------------------

    def tick(self) -> str | None:
        """One pass: usage, snapshot, agents, housekeeping, plan, starts. Returns why to end."""
        now = self.clock()
        usage = read_usage(self.usage_file)
        snapshot = take_snapshot(self.github, self.config)
        self._remember_urls(snapshot)
        if not self.dry_run:
            self._update_agents(snapshot)
        free = self.config.max_agents - len(self.agents)
        if not is_fresh(usage, now):
            free = 1 if not self.agents else 0
        minutes_left = (self.until - now).total_seconds() / 60
        live = [Live(a.kind, a.number, a.issue) for a in self.agents]
        result = plan(snapshot, live, self.paused, self.config, max(free, 0), minutes_left)
        if not is_fresh(usage, now):
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

    def _remember_urls(self, snapshot: Snapshot) -> None:
        for number, unit in snapshot.units.items():
            self.urls[number] = unit.url
        for number, pr in snapshot.prs.items():
            self.urls[number] = pr.get("url", "")

    def _update_agents(self, snapshot: Snapshot) -> None:
        for record in list(self.agents):
            status = self.herdr.status(record.pane)
            if status is None:
                self.agents.remove(record)
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
            elif record.nudges == 0:
                self.herdr.prompt(record.pane, NUDGE)
                record.nudges = 1
                self._log(f"{record.kind} #{record.number}: stopped early; nudged")
            else:
                self._mark_stuck(record)

    def _mark_stuck(self, record: AgentRecord) -> None:
        lines = self.herdr.read(record.pane, STUCK_LINES).rstrip("\n").splitlines()[-STUCK_LINES:]
        body = (
            "crew run: the agent stopped twice without finishing. Last output:\n\n```\n"
            + "\n".join(lines)
            + "\n```"
        )
        self.github.comment(record.number, body)
        set_state(self.github, record.number, "owner-stuck")
        self.herdr.close(record.pane)
        self.agents.remove(record)
        self.summary.stuck.append(self._label(record))
        self._log(f"{record.kind} #{record.number}: stuck; set crew:owner-stuck")

    def _apply(self, result: Plan, snapshot: Snapshot) -> None:
        for item in result.housekeeping:
            set_state(self.github, item.number, item.state)
            if item.comment:
                self.github.comment(item.number, item.comment)
            self._log(f"#{item.number}: set {item.state}")
        for action in result.actions:
            self._start(action, snapshot)

    def _start(self, action: Action, snapshot: Snapshot) -> None:
        cwd = self.worktree(self.root, action.branch, action.detach) if action.branch else self.root
        if self.workspace is None:
            self.workspace = self.herdr.create_workspace(self.root, "crew run")
        pane = self.herdr.open_tab(self.workspace, cwd, f"{action.kind} #{action.number}")
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
                last = lines[-1].strip() if lines else "no output"
                raise RunError(f"agent for {action.kind} #{action.number} did not start: {last}")
            self.sleep(START_POLL)
        record = AgentRecord(
            pane=pane,
            kind=action.kind,
            number=action.number,
            issue=action.issue,
            role=action.role,
            branch=action.branch,
            flow_at_start=progress_state(snapshot, action.kind, action.number, self.config),
            started_at=self.clock().isoformat(),
        )
        self.agents.append(record)
        self.paused = [p for p in self.paused if p.get("number") != (action.issue or action.number)]
        self.summary.started.append(self._label(record))
        self._log(f"{action.kind} #{action.number}: started in {cwd}")

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

    def _write_run(self, alive: bool) -> None:
        data = {
            "until": self.until.isoformat(),
            "cap": self.cap,
            "workspace": self.workspace,
            "paused": self.paused,
        }
        if alive:
            data = {"pid": os.getpid(), **data, "agents": [asdict(a) for a in self.agents]}
        path = self._run_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def _adopt(self) -> None:
        data = self._read_run()
        pid = data.get("pid")
        if not self.dry_run and isinstance(pid, int) and pid != os.getpid() and _pid_alive(pid):
            raise RunError(f"a run is already active (pid {pid})")
        self.workspace = data.get("workspace") or None
        self.paused = [p for p in data.get("paused") or [] if isinstance(p, dict)]
        for raw in data.get("agents") or []:
            try:
                record = AgentRecord(**raw)
            except TypeError:
                continue
            if self.herdr.status(record.pane) is not None:
                self.agents.append(record)
                self._log(f"{record.kind} #{record.number}: adopted the live agent")

    # --- the loop -------------------------------------------------------------------------

    def run(self, once: bool = False) -> int:
        """Tick until an end reason; returns the exit code. Raises RunError on failure."""
        self._adopt()
        if not self.dry_run:
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
                self.sleep(self.config.poll_seconds)
        finally:
            if not self.dry_run:
                self._finish()
        if reason:
            self._log(f"run ended: {reason}")
        return 0

    def _finish(self) -> None:
        self._write_run(alive=False)
        data = self._read_run()
        data["agents"] = [asdict(a) for a in self.agents]
        self._run_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # --- helpers --------------------------------------------------------------------------

    def _label(self, record: AgentRecord) -> str:
        url = self.urls.get(record.number, "")
        return f"{record.kind} #{record.number}" + (f" {url}" if url else "")

    def _log(self, message: str) -> None:
        self.out(f"{self.clock().astimezone().strftime('%H:%M')} {message}")
