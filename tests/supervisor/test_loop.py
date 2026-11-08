import json
import os
import shlex
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from crew.cli import main
from crew.config import load_config
from crew.supervisor.loop import NUDGE, RUN_PATH, AgentRecord, RunError, Supervisor
from tests.supervisor.fakes import (
    START,
    Clock,
    FakeGitHub,
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


def make(root, tmp_path, github, herdr=None, clock=None, fresh=True, dry_run=False, until=None):
    clock = clock or Clock()
    usage_file = tmp_path / "usage.json"
    if fresh:
        write_usage(usage_file, clock())
    out = []
    supervisor = Supervisor(
        root, load_config(root), github, herdr or FakeHerdr(),
        until=until or START + timedelta(hours=10), cap=None, dry_run=dry_run,
        clock=clock, sleep=clock.sleep, out=out.append,
        worktree=FakeWorktree(tmp_path / "wt"), usage_file=usage_file,
    )  # fmt: skip
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
    assert supervisor.agents == []
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
    (root / RUN_PATH).write_text(json.dumps({"pid": os.getppid(), "agents": []}))
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeGitHub())
    monkeypatch.setattr("crew.cli.make_herdr", lambda: FakeHerdr())
    until = (START + timedelta(days=400)).isoformat()
    assert main(["run", "--until", until, "--once", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err == f"crew: error: a run is already active (pid {os.getppid()})\n"
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
