"""In-memory GitHub, herdr, clock and worktree stand-ins for the run loop tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crew.usage import record_statusline
from tests.test_graph import issue

START = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


class FakeGitHub:
    """Open issues and PRs with mutable labels; records comments."""

    def __init__(self, issues=(), prs=(), merged=()):
        self.issues = {i["number"]: i for i in issues}
        self.prs = {p["number"]: p for p in prs}
        self.merged = list(merged)  # merged PRs, as gh pr list gives them
        self.comments: list[tuple[int, str]] = []
        self.label_calls: list[tuple[int, list, list]] = []
        self.assignee_calls: list[tuple[int, list, list]] = []
        self.refused: set[str] = set()  # logins GitHub silently won't assign

    def _item(self, number):
        return self.issues.get(number) or self.prs[number]

    def list_issues(self, state="open"):
        wanted = "CLOSED" if state == "closed" else "OPEN"
        return [i for i in self.issues.values() if i.get("state", "OPEN") == wanted]

    def list_prs(self, state="open"):
        if state == "merged":
            return list(self.merged)
        if state != "open":
            return []
        return [
            {"number": p["number"], "closingIssuesReferences": p["closingIssuesReferences"]}
            for p in self.prs.values()
        ]

    def pr_detail(self, number):
        return json.loads(json.dumps(self.prs[number]))

    def issue_comments(self, number):
        return []

    def labels_of(self, number):
        return {label["name"] for label in self._item(number)["labels"]}

    def item_state(self, number):
        item = self._item(number)
        return self.labels_of(number), {a["login"] for a in item.get("assignees") or []}

    def set_assignees(self, number, add, remove):
        self.assignee_calls.append((number, list(add), list(remove)))
        item = self._item(number)
        logins = [a["login"] for a in item.get("assignees") or [] if a["login"] not in remove]
        logins += [a for a in add if a not in logins and a not in self.refused]
        item["assignees"] = [{"login": login} for login in logins]
        return set(add) & self.refused

    def set_labels(self, number, add, remove):
        self.label_calls.append((number, list(add), list(remove)))
        item = self._item(number)
        names = [label["name"] for label in item["labels"] if label["name"] not in remove]
        item["labels"] = [{"name": n} for n in names + [a for a in add if a not in names]]

    def comment(self, number, body):
        self.comments.append((number, body))

    def relabel(self, number, *names):
        self._item(number)["labels"] = [{"name": n} for n in names]


class FakeHerdr:
    """Panes with scripted agent statuses (default ``working``)."""

    def __init__(self, never_starts=False):
        self.never_starts = never_starts
        self.statuses: dict[str, str | None] = {}
        self.commands: list[tuple[str, str]] = []
        self.prompts: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self.tabs: list[tuple[str, Path, str]] = []
        self.workspaces = 0
        self.output = "line one\nlast words of the agent\n"
        self.tab_env: list[dict] = []
        self.stale_workspaces: set[str] = set()
        self.next_workspace = "w1"

    def create_workspace(self, cwd, label):
        self.workspaces += 1
        return self.next_workspace

    def open_tab(self, workspace, cwd, label, env=None):
        if workspace in self.stale_workspaces:
            from crew.supervisor.herdr import HerdrError

            raise HerdrError(f"herdr tab create failed: workspace {workspace} not found")
        self.tab_env.append(dict(env or {}))
        pane = f"{workspace}:p{len(self.tabs) + 1}"
        self.tabs.append((pane, cwd, label))
        self.statuses[pane] = None if self.never_starts else "working"
        return pane

    def run_command(self, pane, command):
        self.commands.append((pane, command))

    def status(self, pane):
        return self.statuses.get(pane)

    def prompt(self, pane, text):
        self.prompts.append((pane, text))

    def read(self, pane, lines=40):
        return self.output

    def close(self, pane):
        self.closed.append(pane)
        self.statuses[pane] = None


class Clock:
    def __init__(self, start=START):
        self.now = start
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


class FakeWorktree:
    def __init__(self, base: Path):
        self.base = base
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, root, branch, detach=False):
        self.calls.append((branch, detach))
        return self.base / branch.replace("/", "-")


def ready(number, owns, labels=("crew:ready",)):
    return issue(number, labels=list(labels), owns=[owns])


def write_usage(path: Path, at: datetime, week=10, five=5, five_reset=None):
    five_reset = five_reset or at + timedelta(hours=3)
    data = {
        "rate_limits": {
            "seven_day": {
                "used_percentage": week,
                "resets_at": int((at + timedelta(days=3)).timestamp()),
            },
            "five_hour": {"used_percentage": five, "resets_at": int(five_reset.timestamp())},
        }
    }
    record_statusline(json.dumps(data), path, at)


class FakeGitRun:
    """``subprocess.run`` for the wind-down's pushed check: clean and pushed unless told."""

    def __init__(self):
        self.unpushed: set[str] = set()  # worktree paths with work not pushed yet
        self.calls = []

    def __call__(self, argv, **kwargs):
        import subprocess

        self.calls.append(argv)
        path = argv[2]
        if "status" in argv:
            out = " M file.py\n" if path in self.unpushed else ""
            return subprocess.CompletedProcess(argv, 0, out, "")
        if "rev-parse" in argv:
            out = "aaa\nbbb\n" if path in self.unpushed else "aaa\naaa\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        return subprocess.CompletedProcess(argv, 0, "", "")
