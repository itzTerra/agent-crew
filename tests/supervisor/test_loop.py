import json
import os
import shlex
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from crew.cli import main
from crew.config import load_config
from crew.supervisor.events import EVENTS_PATH, read_events
from crew.supervisor.loop import NUDGE, RUN_PATH, AgentRecord, RunError, Supervisor
from tests.supervisor.fakes import (
    START,
    Clock,
    FakeGitHub,
    FakeGitRun,
    FakeHerdr,
    FakeWorktree,
    ready,
    write_usage,
)
from tests.test_graph import issue

PROJECT = Path(__file__).resolve().parent.parent / "fixtures" / "project"


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    return root


def make(
    root, tmp_path, github, herdr=None, clock=None, fresh=True, dry_run=False, until=None, pane=None
):
    clock = clock or Clock()
    usage_file = tmp_path / "usage.json"
    if fresh:
        write_usage(usage_file, clock())
    out, trusted = [], []
    supervisor = Supervisor(
        root, load_config(root), github, herdr or FakeHerdr(),
        until=until or START + timedelta(hours=10), cap=None, dry_run=dry_run,
        clock=clock, sleep=clock.sleep, out=out.append,
        worktree=FakeWorktree(tmp_path / "wt"), usage_file=usage_file, git_run=FakeGitRun(),
        trust=lambda path: trusted.append(path), pane=pane,
    )  # fmt: skip
    supervisor.trusted = trusted
    supervisor.log = out
    return supervisor


def test_tick_starts_planned_agents_with_crew_agent_command(root, tmp_path):
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    assert supervisor.tick() is None
    ((pane, command),) = herdr.commands
    worktree = tmp_path / "wt" / "unit-7-unit-7"
    assert shlex.split(command) == [
        "crew", "agent", "implementer", "--auto", "--root", str(worktree),
        "Use crew:implement on issue #7 (https://github.com/example/app/issues/7).",
    ]  # fmt: skip
    assert herdr.tabs == [(pane, worktree, "implement #7")]
    (record,) = supervisor.agents
    assert (record.kind, record.number, record.branch) == ("implement", 7, "unit/7-unit-7")
    run = json.loads((root / RUN_PATH).read_text())
    assert run["pid"] == os.getpid() and run["workspace"] == "w1"
    assert [a["number"] for a in run["agents"]] == [7]


def test_reviewer_gets_model_flag(root, tmp_path):
    from tests.supervisor.test_planner import pr

    github = FakeGitHub(
        [issue(5, labels=["crew:in-review"], owns=["a/"])], [pr(9, 5, ["crew:in-review"])]
    )
    herdr = FakeHerdr()
    make(root, tmp_path, github, herdr).tick()
    argv = shlex.split(herdr.commands[0][1])
    assert argv[:8] == ["crew", "agent", "reviewer", "--auto", "--root",
                        str(tmp_path / "wt" / "unit-5-unit-5"), "--model", "sonnet"]  # fmt: skip


def test_finished_agent_pane_closed(root, tmp_path):
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    pane = herdr.tabs[0][0]
    github.relabel(7, "crew:in-progress")  # started, not finished
    herdr.statuses[pane] = "working"
    supervisor.tick()
    assert supervisor.agents and herdr.closed == []
    github.relabel(7, "crew:in-review")
    herdr.statuses[pane] = "done"
    supervisor.tick()
    assert supervisor.agents == [] and herdr.closed == [pane]
    assert herdr.prompts == []


def test_idle_without_progress_nudged_then_stuck(root, tmp_path):
    github = FakeGitHub([ready(7, "a/"), ready(8, "b/", labels=("crew:rough",))])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.config = load_config(root).__class__(
        **{**load_config(root).__dict__, "refine_ahead": 0}
    )
    supervisor.tick()
    pane = herdr.tabs[0][0]
    github.relabel(7, "crew:in-progress")
    herdr.statuses[pane] = "idle"
    supervisor.tick()
    assert herdr.prompts == [(pane, NUDGE)]
    supervisor.tick()
    assert herdr.prompts == [(pane, NUDGE)]
    ((number, body),) = github.comments
    assert number == 7 and "stopped twice without finishing" in body
    assert "last words of the agent" in body and "```" in body
    assert {label["name"] for label in github.issues[7]["labels"]} == {"crew:owner-stuck"}
    assert pane in herdr.closed and supervisor.agents == []


def test_gone_agent_dropped(root, tmp_path):
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    github.relabel(7, "crew:in-progress")
    herdr.statuses[herdr.tabs[0][0]] = None
    supervisor.tick()
    assert [(a.kind, a.number) for a in supervisor.agents] == [("resume", 7)]
    assert any("gone" in line for line in supervisor.log)


def test_agent_that_never_starts_ends_run_with_error(root, tmp_path, monkeypatch, capsys):
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr(never_starts=True)
    herdr.output = "booting\n--agent 'crew:implementer' not found\n\n"
    clock = Clock()
    write_usage(tmp_path / "usage.json", clock())
    monkeypatch.setenv("CREW_USAGE_FILE", str(tmp_path / "usage.json"))
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    monkeypatch.setattr("crew.cli.make_herdr", lambda: herdr)
    monkeypatch.setattr("crew.cli.run_sleep", clock.sleep)
    monkeypatch.setattr("crew.supervisor.worktrees.worktree_for",
                        FakeWorktree(tmp_path / "wt"))  # fmt: skip
    monkeypatch.setattr("crew.cli.run_clock", clock)
    until = (START + timedelta(hours=5)).isoformat()
    assert main(["run", "--until", until, "--once", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err == (
        "crew: error: agent for implement #7 did not start: --agent 'crew:implementer' not found\n"
    )
    assert herdr.closed == ["w1:p1"]


def test_stale_usage_starts_one_probe_agent_only(root, tmp_path):
    github = FakeGitHub([ready(7, "a/"), ready(8, "b/"), ready(9, "c/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, fresh=False)
    supervisor.config = load_config(root).__class__(
        **{**load_config(root).__dict__, "max_agents": 3}
    )
    supervisor.tick()
    assert [t[2] for t in herdr.tabs] == ["implement #7"]
    supervisor.tick()
    assert len(herdr.tabs) == 1


def test_restart_adopts_live_agents(root, tmp_path):
    github = FakeGitHub([ready(12, "a/", labels=("crew:in-progress",)), ready(13, "b/")])
    herdr = FakeHerdr()
    herdr.statuses["w1:p9"] = "working"
    record = AgentRecord("w1:p9", "implement", 12, None, "implementer", "unit/12-unit-12",
                         ["working"], START.isoformat())  # fmt: skip
    gone = AgentRecord("w1:p8", "implement", 14, None, "implementer", "unit/14-x",
                       ["working"], START.isoformat())  # fmt: skip
    (root / RUN_PATH).write_text(json.dumps({
        "until": START.isoformat(), "workspace": "w1", "paused": [],
        "agents": [record.__dict__, gone.__dict__],
    }))  # fmt: skip
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.run(once=True)
    assert [t[2] for t in herdr.tabs] == ["implement #13"]
    assert sorted(a.number for a in supervisor.agents) == [12, 13]
    assert herdr.workspaces == 0  # the adopted workspace is reused


def test_second_run_refused_while_first_alive(root, tmp_path, monkeypatch, capsys):
    import subprocess
    import sys

    first = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "crew", "run"])
    monkeypatch.setattr(os, "getppid", lambda: first.pid)
    request = None
    try:
        request = _second_run(root, tmp_path, monkeypatch, capsys, first.pid)
    finally:
        first.kill()
        first.wait()
    assert request is None


def _second_run(root, tmp_path, monkeypatch, capsys, pid):
    (root / RUN_PATH).write_text(json.dumps({"pid": pid, "agents": []}))
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeGitHub())
    monkeypatch.setattr("crew.cli.make_herdr", lambda: FakeHerdr())
    until = (START + timedelta(days=400)).isoformat()
    assert main(["run", "--until", until, "--once", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err == (
        f"crew: error: a run is already active (pid {pid}); if it isn't, delete .crew/run.json\n"
    )
    with pytest.raises(RunError):
        make(root, tmp_path, FakeGitHub()).run(once=True)


def test_dry_run_changes_nothing(root, tmp_path):
    from tests.supervisor.test_planner import owner_comment, pr

    github = FakeGitHub(
        [ready(7, "a/"), issue(5, labels=["crew:owner-accept"], owns=["b/"])],
        [pr(9, 5, ["crew:owner-accept"], comments=[owner_comment()])],
    )
    herdr = FakeHerdr()
    worktree = FakeWorktree(tmp_path / "wt")
    supervisor = make(root, tmp_path, github, herdr, dry_run=True)
    supervisor.worktree = worktree
    supervisor.run(once=True)
    assert herdr.tabs == [] and herdr.commands == [] and worktree.calls == []
    assert github.label_calls == [] and github.comments == []
    assert not (root / RUN_PATH).exists()
    text = "\n".join(supervisor.log)
    assert "housekeeping: #9 → changes-requested" in text
    assert "start: implement #7 (implementer)" in text


def test_ends_when_idle_and_no_agents(root, tmp_path):
    github = FakeGitHub([issue(5, labels=["crew:rough", "crew:owner-decision"], owns=["a/"])])
    supervisor = make(root, tmp_path, github)
    assert supervisor.tick() == "nothing to do: everything waits on the owner"
    assert supervisor.run() == 0
    assert any("nothing to do" in line for line in supervisor.log)


def test_github_errors_retried_then_fatal(root, tmp_path):
    from crew.github import GitHubError

    class Flaky(FakeGitHub):
        calls = 0

        def list_issues(self, state="open"):
            Flaky.calls += 1
            raise GitHubError("gh issue list failed: offline")

    supervisor = make(root, tmp_path, Flaky())
    with pytest.raises(RunError, match="offline"):
        supervisor.run()
    assert Flaky.calls == 3


# --- stopping (Task 16) ---------------------------------------------------------------------

from crew.supervisor.until import CONTINUE, FIVE_HOUR_FULL, RESET_SLACK, WIND_DOWN  # noqa: E402


def test_ends_at_until(root, tmp_path):
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    supervisor = make(root, tmp_path, github, clock=clock, until=START + timedelta(minutes=5))
    supervisor.run()
    assert any("end time reached" in line for line in supervisor.log)


def test_ends_at_cap_with_cli_cap_override(root, tmp_path):
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock)
    write_usage(tmp_path / "usage.json", clock(), week=80)
    assert supervisor.tick() == "budget cap reached (80% of 75%)"
    assert herdr.tabs == []
    supervisor.cap = 90
    assert supervisor.tick() is None
    assert len(herdr.tabs) == 1
    write_usage(tmp_path / "usage.json", clock(), week=91)
    assert supervisor.tick() == "budget cap reached (91% of 90%)"


def test_waits_out_five_hour_window_then_continues(root, tmp_path):
    clock = Clock()
    github = FakeGitHub([ready(7, "a/"), ready(8, "b/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock)
    supervisor.tick()
    pane, started = herdr.tabs[0][0], len(herdr.tabs)
    github.relabel(7, "crew:in-progress")
    github.relabel(8, "crew:in-progress")
    reset = clock() + timedelta(minutes=10)
    write_usage(tmp_path / "usage.json", clock(), five=FIVE_HOUR_FULL, five_reset=reset)
    herdr.statuses[pane] = "idle"
    assert supervisor.tick() is None
    assert supervisor.agents[0].limited and herdr.prompts == []
    assert len(herdr.tabs) == started  # nothing new starts while the window is full
    poll = supervisor.config.poll_seconds
    assert supervisor.next_sleep == min(poll, (reset + RESET_SLACK - clock()).total_seconds())
    clock.now = reset + RESET_SLACK - timedelta(seconds=30)
    assert supervisor.tick() is None and herdr.prompts == []
    assert supervisor.next_sleep == 30
    clock.now = reset + RESET_SLACK + timedelta(seconds=1)
    assert supervisor.tick() is None
    assert herdr.prompts == [(pane, CONTINUE)]
    assert not supervisor.agents[0].limited
    herdr.statuses[pane] = "working"
    supervisor.tick()
    assert herdr.prompts == [(pane, CONTINUE)]


def test_wind_down_pushes_and_pauses(root, tmp_path):
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock,
                      until=START + timedelta(hours=2))  # fmt: skip
    supervisor.tick()
    pane = herdr.tabs[0][0]
    github.relabel(7, "crew:in-progress")
    clock.now = START + timedelta(hours=2)
    original_prompt = herdr.prompt

    def prompt_then_finish(target, text):
        original_prompt(target, text)
        herdr.statuses[target] = "working"
        herdr.finish_at = clock() + timedelta(minutes=3)

    herdr.prompt = prompt_then_finish
    original_status = herdr.status
    herdr.status = lambda target: (
        "idle" if getattr(herdr, "finish_at", None) and clock() >= herdr.finish_at
        else original_status(target)
    )  # fmt: skip
    assert supervisor.run() == 0
    assert herdr.prompts == [(pane, WIND_DOWN)]
    assert pane in herdr.closed
    run = json.loads((root / RUN_PATH).read_text())
    assert "pid" not in run and "agents" not in run
    assert run["paused"] == [{"number": 7, "branch": "unit/7-unit-7"}]
    text = "\n".join(supervisor.log)
    assert "end time reached" in text and "Paused" in text
    assert "https://github.com/example/app/issues/7" in text


def test_wind_down_gives_up_after_grace(root, tmp_path):
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock,
                      until=START + timedelta(hours=2))  # fmt: skip
    supervisor.tick()
    clock.now = START + timedelta(hours=2)
    supervisor.run()  # the agent keeps working
    grace = timedelta(minutes=supervisor.config.stop_grace_minutes)
    assert clock() - (START + timedelta(hours=2)) <= grace + timedelta(minutes=1)
    assert herdr.tabs[0][0] in herdr.closed


def test_next_run_resumes_paused_unit(root, tmp_path):
    github = FakeGitHub([ready(7, "a/", labels=("crew:in-progress",))])
    (root / RUN_PATH).write_text(json.dumps({"paused": [{"number": 7, "branch": "unit/7-x"}]}))
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.run(once=True)
    assert [t[2] for t in herdr.tabs] == ["resume #7"]
    assert "resume the work pushed on branch unit/7-x" in herdr.commands[0][1]
    run = json.loads((root / RUN_PATH).read_text())
    assert run["paused"] == []


def test_bad_until_is_clean_error(root, capsys):
    for bad in ("25:00", "2020-01-01T07:00"):
        assert main(["run", "--until", bad, "--root", str(root)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("crew: error: ") and err.count("\n") == 1 and bad in err


# --- final review fixes ---------------------------------------------------------------------

from crew.supervisor.snapshot import MARKER  # noqa: E402
from tests.supervisor.test_planner import owner_comment, pr  # noqa: E402


def test_supervisor_comments_never_count_as_owner_feedback(root, tmp_path):
    # C1: crew run comments with the owner's gh login; its stuck comment must not loop.
    github = FakeGitHub(
        [issue(5, labels=["crew:changes-requested"], owns=["a/"])],
        [pr(9, 5, ["crew:changes-requested"])],
    )
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    pane = herdr.tabs[0][0]
    herdr.statuses[pane] = "idle"
    supervisor.tick()
    supervisor.tick()  # stuck: comment + owner-stuck
    ((number, body),) = github.comments
    assert MARKER in body
    github.prs[9]["comments"].append(
        {"author": {"login": supervisor.config.owner_login}, "body": body,
         "createdAt": "2026-11-10T00:00:00Z"}
    )  # fmt: skip
    tabs = len(herdr.tabs)
    supervisor.tick()
    assert len(herdr.tabs) == tabs and len(github.comments) == 1
    assert {label["name"] for label in github.prs[9]["labels"]} == {"crew:owner-stuck"}


def test_ci_failure_comment_carries_marker(root, tmp_path):
    github = FakeGitHub(
        [issue(5, labels=["crew:in-review"], owns=["a/"])], [pr(9, 5, ["crew:in-review"], "fail")]
    )
    make(root, tmp_path, github).tick()
    ((number, body),) = github.comments
    assert number == 9 and body.startswith("CI failed: test. (crew run)") and MARKER in body


def test_followup_on_decision_pr_finishes_when_answered(root, tmp_path):
    # I1
    github = FakeGitHub(
        [issue(5, labels=["crew:owner-accept"], owns=["a/"])],
        [pr(9, 5, ["crew:owner-accept", "crew:owner-decision"], comments=[owner_comment()])],
    )
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    assert [t[2] for t in herdr.tabs] == ["followup #9"]
    github.prs[9]["comments"].append(
        {"author": {"login": supervisor.config.agent_login}, "body": "ADR written",
         "createdAt": "2026-11-10T00:00:00Z"}
    )  # fmt: skip
    herdr.statuses[herdr.tabs[0][0]] = "idle"
    supervisor.tick()
    assert supervisor.agents == [] and herdr.prompts == [] and github.comments == []


def test_gone_implementer_is_paused(root, tmp_path):
    # I2: in a tick, and when a restart finds the pane gone.
    github = FakeGitHub([ready(7, "a/"), ready(8, "b/", labels=("crew:in-progress",))])
    herdr = FakeHerdr()
    gone = AgentRecord("w1:p8", "implement", 8, None, "implementer", "unit/8-unit-8",
                       ["working"], START.isoformat())  # fmt: skip
    (root / RUN_PATH).write_text(json.dumps({"agents": [gone.__dict__], "paused": []}))
    supervisor = make(root, tmp_path, github, herdr)
    supervisor._adopt()
    assert supervisor.paused == [{"number": 8, "branch": "unit/8-unit-8"}]
    supervisor.tick()
    pane = next(p for p, _, label in herdr.tabs if label == "implement #7")
    github.relabel(7, "crew:in-progress")
    herdr.statuses[pane] = None
    supervisor.tick()
    assert "resume #7" in [label for _, _, label in herdr.tabs]  # paused, then resumed


def test_interrupt_while_starting_winds_that_agent_down(root, tmp_path):
    # I3
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr(never_starts=True)
    supervisor = make(root, tmp_path, github, herdr)

    def interrupt(seconds):
        raise KeyboardInterrupt

    supervisor.sleep = interrupt
    supervisor.run()
    assert herdr.closed == ["w1:p1"]
    assert "agents" not in json.loads((root / RUN_PATH).read_text())


def test_second_ctrl_c_during_wind_down_still_closes_and_pauses(root, tmp_path):
    # I4
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock,
                      until=START + timedelta(hours=2))  # fmt: skip
    supervisor.tick()
    github.relabel(7, "crew:in-progress")
    clock.now = START + timedelta(hours=2)

    def interrupt(seconds):
        raise KeyboardInterrupt

    supervisor.sleep = interrupt
    supervisor.run()
    assert herdr.tabs[0][0] in herdr.closed
    run = json.loads((root / RUN_PATH).read_text())
    assert run["paused"] == [{"number": 7, "branch": "unit/7-unit-7"}]


def test_wind_down_waits_for_push(root, tmp_path):
    # I5: an agent that looks stopped but hasn't pushed keeps its pane.
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock,
                      until=START + timedelta(hours=2))  # fmt: skip
    supervisor.tick()
    pane, cwd = herdr.tabs[0][0], str(herdr.tabs[0][1])
    supervisor.git_run.unpushed.add(cwd)
    herdr.statuses[pane] = "idle"
    clock.now = START + timedelta(hours=2)
    pushed_at = clock() + timedelta(minutes=5)

    def sleep(seconds):
        clock.sleep(seconds)
        if clock() >= pushed_at:
            supervisor.git_run.unpushed.discard(cwd)
        if pane in herdr.closed:
            raise AssertionError("closed before the push")

    supervisor.sleep = sleep
    supervisor.run()
    assert pane in herdr.closed
    assert clock() >= pushed_at
    assert herdr.prompts == [(pane, WIND_DOWN)]


def test_stale_workspace_replaced(root, tmp_path):
    # I6
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    herdr.stale_workspaces = {"w1"}
    herdr.next_workspace = "w2"
    (root / RUN_PATH).write_text(json.dumps({"workspace": "w1", "paused": []}))
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.run(once=True)
    assert [t[0] for t in herdr.tabs] == ["w2:p1"]
    assert supervisor.workspace == "w2"


def test_agent_tabs_get_run_environment(root, tmp_path, monkeypatch):
    # I7: herdr panes don't inherit crew run's environment.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/x/.claude-work")
    monkeypatch.setenv("CREW_AGENT_TOKEN_FILE", "/x/token")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("GH_TOKEN", "owner-secret")
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    (env,) = herdr.tab_env
    assert env["CLAUDE_CONFIG_DIR"] == "/x/.claude-work"
    assert env["CREW_AGENT_TOKEN_FILE"] == "/x/token"
    assert env["CREW_USAGE_FILE"] == str(tmp_path / "usage.json")
    assert not {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "GH_TOKEN"} & set(env)


def test_blocked_agent_never_prompted(root, tmp_path):
    # I8: typing into a dialog could approve what auto mode stopped to ask.
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    herdr.output = "Do you want to proceed?\n> 1. Yes\n  2. No\n"
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    pane = herdr.tabs[0][0]
    github.relabel(7, "crew:in-progress")
    herdr.statuses[pane] = "blocked"
    supervisor.tick()
    assert herdr.prompts == []
    ((number, body),) = github.comments
    assert number == 7 and "dialog" in body and "Do you want to proceed?" in body
    assert pane in herdr.closed


def test_limit_message_in_pane_waits_instead_of_nudging(root, tmp_path):
    # I9: the last reading may be below 98% when the limit hits.
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr, clock=clock)
    reset = clock() + timedelta(minutes=40)
    write_usage(tmp_path / "usage.json", clock(), five=93, five_reset=reset)
    supervisor.tick()
    pane = herdr.tabs[0][0]
    github.relabel(7, "crew:in-progress")
    herdr.statuses[pane] = "idle"
    herdr.output = "working...\nYou've hit your usage limit · resets 9pm\n"
    for _ in range(3):
        supervisor.tick()
    assert herdr.prompts == [] and github.comments == []
    assert supervisor.agents[0].limited
    clock.now = reset + timedelta(minutes=3)
    write_usage(tmp_path / "usage.json", clock(), five=1)
    supervisor.tick()
    assert herdr.prompts == [(pane, CONTINUE)]


def test_unit_marked_stuck_is_not_restarted_in_the_same_tick(root, tmp_path):
    # Smoke test: the tick's snapshot predates the stuck label, so #7 still looked ready.
    github = FakeGitHub([ready(7, "a/")])
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    herdr.statuses[herdr.tabs[0][0]] = "blocked"  # e.g. the folder-trust dialog
    supervisor.tick()
    assert len(github.comments) == 1
    assert [label for _, _, label in herdr.tabs] == ["implement #7"]


def test_start_pretrusts_its_worktree_only(root, tmp_path):
    # Claude Code asks to trust every new git worktree; the run trusts the ones it made.
    github = FakeGitHub([ready(7, "a/"), issue(3, labels=["crew:rough"], owns=["z/"])])
    supervisor = make(root, tmp_path, github)
    supervisor.tick()
    assert supervisor.trusted == [tmp_path / "wt" / "unit-7-unit-7"]  # not the root (refine)


# --- deferred minors -----------------------------------------------------------------------


def test_relative_root_is_resolved(root, tmp_path, monkeypatch):
    # M1: worktree reuse compares git's absolute paths with ours.
    seen = {}

    class Recording:
        def __init__(self, root, *args, **kwargs):
            seen["root"] = root

        def run(self, once=False):
            return 0

    monkeypatch.setattr("crew.supervisor.loop.Supervisor", Recording)
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeGitHub())
    monkeypatch.setattr("crew.cli.make_herdr", lambda: FakeHerdr())
    monkeypatch.chdir(root.parent)
    until = (START + timedelta(days=400)).isoformat()
    assert main(["run", "--until", until, "--once", "--root", root.name]) == 0
    assert seen["root"] == root.resolve() and seen["root"].is_absolute()


def test_live_pid_of_another_program_is_not_a_run(root, tmp_path):
    # M2: after a reboot the stored pid may belong to something else.
    (root / RUN_PATH).write_text(json.dumps({"pid": os.getppid(), "agents": []}))
    make(root, tmp_path, FakeGitHub()).run(once=True)  # no RunError


def test_restart_during_window_wait_keeps_the_reset_time(root, tmp_path):
    # M3
    clock = Clock()
    github = FakeGitHub([ready(7, "a/", labels=("crew:in-progress",))])
    herdr = FakeHerdr()
    herdr.statuses["w1:p9"] = "idle"
    reset = clock() + timedelta(minutes=30)
    record = AgentRecord("w1:p9", "implement", 7, None, "implementer", "unit/7-unit-7",
                         ["working"], START.isoformat(), limited=True)  # fmt: skip
    (root / RUN_PATH).write_text(json.dumps({
        "workspace": "w1", "paused": [], "agents": [record.__dict__],
        "window_reset_at": reset.isoformat(),
    }))  # fmt: skip
    supervisor = make(root, tmp_path, github, herdr, clock=clock, fresh=False)
    supervisor.run(once=True)
    assert herdr.prompts == []  # still waiting: no CONTINUE before the reset
    assert json.loads((root / RUN_PATH).read_text())["window_reset_at"] == reset.isoformat()


def test_failed_label_move_is_retried_next_tick(root, tmp_path):
    # M4: a GitHub error halfway through set_state leaves the issue and PR apart.
    from crew.github import GitHubError

    github = FakeGitHub(
        [issue(5, labels=["crew:in-review"], owns=["a/"])], [pr(9, 5, ["crew:in-review"], "fail")]
    )
    real = github.set_labels
    calls = {"n": 0}

    def flaky(number, add, remove):
        calls["n"] += 1
        if calls["n"] == 2:
            raise GitHubError("gh api failed: HTTP 502")
        real(number, add, remove)

    github.set_labels = flaky
    supervisor = make(root, tmp_path, github)
    supervisor.run(once=True)  # the GitHub error is logged, not fatal
    supervisor.tick()
    names = {n: {label["name"] for label in github._item(n)["labels"]} for n in (5, 9)}
    assert names == {5: {"crew:changes-requested"}, 9: {"crew:changes-requested"}}


def test_stuck_report_for_pr_work_goes_on_the_issue(root, tmp_path):
    # M5: the spec says the stuck agent is reported on the issue.
    github = FakeGitHub(
        [issue(5, labels=["crew:changes-requested"], owns=["a/"])],
        [pr(9, 5, ["crew:changes-requested"])],
    )
    herdr = FakeHerdr()
    supervisor = make(root, tmp_path, github, herdr)
    supervisor.tick()
    herdr.statuses[herdr.tabs[0][0]] = "idle"
    supervisor.tick()
    supervisor.tick()
    ((number, body),) = github.comments
    assert number == 5 and "https://github.com/example/app/pull/9" in body


def test_reading_from_before_the_weekly_reset_does_not_stop_the_run(root, tmp_path):
    # M9
    clock = Clock()
    github = FakeGitHub([ready(7, "a/")])
    supervisor = make(root, tmp_path, github, clock=clock)
    data = {
        "rate_limits": {
            "seven_day": {"used_percentage": 90, "resets_at": int(clock().timestamp()) - 60},
            "five_hour": {"used_percentage": 5, "resets_at": int(clock().timestamp()) + 3600},
        }
    }
    from crew.usage import record_statusline

    record_statusline(json.dumps(data), tmp_path / "usage.json", clock() - timedelta(minutes=5))
    assert supervisor.tick() is None


def _items(root):
    return [e for e in read_events(root) if e["type"] == "item"]


def test_run_writes_start_event_with_pane(root, tmp_path):
    make(root, tmp_path, FakeGitHub(), pane="p9", until=START - timedelta(hours=1)).run()
    first = read_events(root)[0]
    assert first["type"] == "start" and first["pane"] == "p9"
    assert first["run"] == json.loads((root / RUN_PATH).read_text())["run_id"]
    assert json.loads((root / RUN_PATH).read_text())["pane"] == "p9"


def test_first_tick_items_are_a_baseline(root, tmp_path):
    github = FakeGitHub([issue(5, labels=["crew:owner-decision"], owns=["b/"])])
    supervisor = make(root, tmp_path, github)
    supervisor.run(once=True)
    assert _items(root) == []


def test_new_inbox_item_is_reported_once(root, tmp_path):
    github = FakeGitHub([ready(7, "a/")])
    supervisor = make(root, tmp_path, github)
    supervisor.run_id = "r1"
    supervisor.tick()
    github.relabel(7, "crew:owner-accept")
    supervisor.tick()
    supervisor.tick()
    (item,) = _items(root)
    assert (item["number"], item["ask"]) == (7, "accept")
    assert item["url"] == "https://github.com/example/app/issues/7"
    assert item["title"] == "Unit 7"


def test_item_that_returns_is_reported_again(root, tmp_path):
    github = FakeGitHub([ready(7, "a/")])
    supervisor = make(root, tmp_path, github)
    supervisor.run_id = "r1"
    supervisor.tick()
    github.relabel(7, "crew:owner-accept")
    supervisor.tick()
    github.relabel(7)
    supervisor.tick()
    github.relabel(7, "crew:owner-accept")
    supervisor.tick()
    assert [e["number"] for e in _items(root)] == [7, 7]


def test_end_event_carries_reason_and_summary(root, tmp_path):
    supervisor = make(root, tmp_path, FakeGitHub(), until=START - timedelta(hours=1))
    supervisor.summary.started.append("implement #7")
    supervisor.run()
    last = read_events(root)[-1]
    assert last["type"] == "end"
    assert last["reason"] == "end time reached" and last["error"] is False
    assert (last["started"], last["finished"], last["stuck"], last["paused"]) == (
        ["implement #7"], [], [], [],
    )  # fmt: skip


def test_end_event_is_written_before_the_run_is_marked_over(root, tmp_path):
    supervisor = make(root, tmp_path, FakeGitHub(), until=START - timedelta(hours=1))
    seen = []
    write_run = supervisor._write_run
    supervisor._write_run = lambda **kw: (
        seen.append((kw["alive"], read_events(root)[-1]["type"])),
        write_run(**kw),
    )[1]
    supervisor.run()
    assert seen[-1] == (False, "end")


def test_once_run_writes_no_events(root, tmp_path):
    make(root, tmp_path, FakeGitHub([ready(7, "a/")])).run(once=True)
    assert not (root / EVENTS_PATH).exists()


def test_error_end_event(root, tmp_path):
    class Failing(FakeGitHub):
        calls = 0

        def list_issues(self, state="open"):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("boom")
            return super().list_issues(state)

    supervisor = make(root, tmp_path, Failing([ready(7, "a/")]))
    with pytest.raises(RuntimeError):
        supervisor.run()
    last = read_events(root)[-1]
    assert last["error"] is True and last["reason"] == "error: boom"


def test_dry_run_writes_no_events(root, tmp_path):
    make(root, tmp_path, FakeGitHub([ready(7, "a/")]), dry_run=True).run(once=True)
    assert not (root / EVENTS_PATH).exists()


def test_rejected_second_run_keeps_events(root, tmp_path, monkeypatch):
    monkeypatch.setattr("crew.supervisor.loop._is_crew_run", lambda pid: True)
    (root / RUN_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / RUN_PATH).write_text(json.dumps({"pid": 1}))
    (root / EVENTS_PATH).write_text('{"run": "old", "type": "start"}\n')
    with pytest.raises(RunError):
        make(root, tmp_path, FakeGitHub()).run()
    assert (root / EVENTS_PATH).read_text() == '{"run": "old", "type": "start"}\n'


def test_run_parser_takes_pane():
    from crew.cli import build_parser

    args = build_parser().parse_args(
        ["run", "--until", "07:00", "--pane", "p9", "--dry-run", "--once"]
    )
    assert args.pane == "p9"
