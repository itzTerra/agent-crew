import json
import subprocess
from pathlib import Path

import pytest

from crew.supervisor.herdr import Herdr, HerdrError


class FakeRun:
    def __init__(self, answers=()):
        self.calls = []
        self.answers = list(answers)  # (argv prefix, returncode, stdout, stderr)

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        for prefix, code, out, err in self.answers:
            if argv[: len(prefix)] == prefix:
                return subprocess.CompletedProcess(argv, code, out, err)
        return subprocess.CompletedProcess(argv, 0, "", "")


def error(code, message="boom"):
    return json.dumps({"error": {"code": code, "message": message}, "id": "x"})


def test_create_workspace_and_open_tab_return_ids():
    fake = FakeRun(
        [
            (["herdr", "workspace", "create"], 0,
             json.dumps({"result": {"workspace": {"workspace_id": "w6"}}}), ""),
            (["herdr", "tab", "create"], 0,
             json.dumps({"result": {"root_pane": {"pane_id": "w6:p2"}}}), ""),
        ]
    )  # fmt: skip
    herdr = Herdr(run=fake)
    assert herdr.create_workspace(Path("/r"), "crew run") == "w6"
    assert herdr.open_tab("w6", Path("/r/wt"), "implement #5") == "w6:p2"
    assert fake.calls == [
        ["herdr", "workspace", "create", "--cwd", "/r", "--label", "crew run", "--no-focus"],
        ["herdr", "tab", "create", "--workspace", "w6", "--cwd", "/r/wt",
         "--label", "implement #5", "--no-focus"],
    ]  # fmt: skip


def test_status_reads_agent_status():
    answer = json.dumps({"result": {"agent": {"agent": "claude", "agent_status": "working"}}})
    fake = FakeRun([(["herdr", "agent", "get"], 0, answer, "")])
    assert Herdr(run=fake).status("w6:p2") == "working"
    assert fake.calls == [["herdr", "agent", "get", "w6:p2"]]


def test_status_none_when_pane_gone():
    for code in ("agent_not_found", "pane_not_found"):
        fake = FakeRun([(["herdr", "agent", "get"], 1, "", error(code))])
        assert Herdr(run=fake).status("w6:p2") is None


def test_close_gone_pane_is_fine():
    fake = FakeRun([(["herdr", "pane", "close"], 1, "", error("pane_not_found"))])
    Herdr(run=fake).close("w6:p2")


def test_herdr_failure_is_herdr_error():
    fake = FakeRun([(["herdr", "pane", "run"], 1, "", error("server_down", "no server running"))])
    with pytest.raises(HerdrError, match="no server running"):
        Herdr(run=fake).run_command("w6:p2", "crew agent lead")

    def missing(argv, **kwargs):
        raise FileNotFoundError(2, "No such file", "herdr")

    with pytest.raises(HerdrError, match="herdr is not installed"):
        Herdr(run=missing).status("w6:p2")


def test_prompt_read_and_run_argv():
    fake = FakeRun([(["herdr", "pane", "read"], 0, "line 1\nline 2\n", "")])
    herdr = Herdr(run=fake)
    herdr.run_command("w6:p2", "crew agent lead --auto")
    herdr.prompt("w6:p2", "Continue.")
    assert herdr.read("w6:p2", lines=20) == "line 1\nline 2\n"
    assert fake.calls == [
        ["herdr", "pane", "run", "w6:p2", "crew agent lead --auto"],
        ["herdr", "agent", "prompt", "w6:p2", "Continue."],
        ["herdr", "pane", "read", "w6:p2", "--source", "recent-unwrapped", "--lines", "20"],
    ]


def test_open_tab_passes_env():
    answer = json.dumps({"result": {"root_pane": {"pane_id": "w6:p2"}}})
    fake = FakeRun([(["herdr", "tab", "create"], 0, answer, "")])
    Herdr(run=fake).open_tab("w6", Path("/r"), "t", env={"A": "1", "B": "x y"})
    assert fake.calls[0][-4:] == ["--env", "A=1", "--env", "B=x y"]
