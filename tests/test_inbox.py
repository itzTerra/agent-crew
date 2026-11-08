import json
import shutil
from pathlib import Path

from crew.cli import main
from crew.graph import build_units, next_ready
from crew.inbox import InboxItem, merged_without_owner, owner_inbox
from tests.test_graph import issue

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"


def pr(number, labels=(), closes=(), merged_at=None, title=None):
    return {
        "number": number,
        "title": title or f"PR {number}",
        "labels": [{"name": name} for name in labels],
        "headRefName": f"unit/{number}",
        "closingIssuesReferences": [{"number": n} for n in closes],
        "mergedAt": merged_at,
        "author": {"login": "agent-b"},
        "url": f"https://github.com/example/app/pull/{number}",
    }


def test_inbox_order_do_first_then_blocks():
    units = build_units(
        [
            issue(1, labels=["crew:owner-decision"], created="2026-01-03T00:00:00Z"),
            issue(2, labels=["crew:owner-stuck"], created="2026-01-01T00:00:00Z"),
            issue(3, labels=["crew:owner-proposal", "crew:do-first"]),
            issue(4, deps=[1]),
            issue(5, deps=[4]),
            issue(6, labels=["crew:owner-accept"], created="2026-01-02T00:00:00Z"),
        ]
    )
    items = owner_inbox(units, open_prs=[])
    assert [(i.number, i.ask, i.blocks, i.do_first) for i in items] == [
        (3, "proposal", 0, True),
        (1, "decision", 2, False),
        (2, "stuck", 0, False),
        (6, "accept", 0, False),
    ]


def test_pr_maps_to_linked_issue():
    units = build_units([issue(1), issue(2, deps=[1])])
    items = owner_inbox(units, [pr(10, labels=["crew:owner-accept"], closes=[1])])
    assert items == [
        InboxItem(1, "PR 10", "https://github.com/example/app/pull/10", "accept", 1, False)
    ]


def test_pr_without_linked_issue_in_inbox():
    items = owner_inbox({}, [pr(11, labels=["crew:owner-accept"]), pr(12)])
    assert [(i.number, i.ask, i.url) for i in items] == [
        (11, "accept", "https://github.com/example/app/pull/11")
    ]


def test_malformed_issue_is_not_ready_but_listed():
    broken = issue(1, labels=["crew:owner-decision", "crew:ready"], body="no sections at all {{")
    units = build_units([broken, issue(2, labels=["crew:ready"], owns=["src/y/**"])])
    assert [i.number for i in owner_inbox(units, [])] == [1]
    assert next_ready(units, running=[], max_agents=3) == [2]


def test_merged_without_owner_since():
    merged = [
        pr(1, labels=["crew:internal"], merged_at="2026-01-05T10:00:00Z"),
        pr(2, labels=["crew:internal"], merged_at="2026-01-01T10:00:00Z"),
        pr(3, labels=["crew:owner-facing"], merged_at="2026-01-06T10:00:00Z"),
    ]
    assert [p["number"] for p in merged_without_owner(merged, "2026-01-02T00:00:00Z")] == [1]
    assert [p["number"] for p in merged_without_owner(merged, None)] == [1, 2]


class FakeGitHub:
    def __init__(self, issues, open_prs, merged_prs):
        self.issues, self.open_prs, self.merged_prs = issues, open_prs, merged_prs

    def list_issues(self, state="open"):
        return self.issues

    def list_prs(self, state="open"):
        return self.merged_prs if state == "merged" else self.open_prs


def test_inbox_cli_writes_state(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    (root / ".crew/state.json").write_text(json.dumps({"other": 1}), encoding="utf-8")
    fake = FakeGitHub(
        issues=[
            issue(1, labels=["crew:owner-decision"]),
            issue(2, deps=[1]),
            issue(3, deps=[4]),
            issue(4, deps=[3]),
        ],
        open_prs=[],
        merged_prs=[pr(9, labels=["crew:internal"], merged_at="2026-01-05T10:00:00Z")],
    )
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["inbox", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "#1 [decision] blocks 1 — Unit 1 — https://github.com/example/app/issues/1" in out
    assert "#9 PR 9" in out
    assert "#3 → #4 → #3" in out
    state = json.loads((root / ".crew/state.json").read_text(encoding="utf-8"))
    assert state["other"] == 1
    since = state["last_inbox"]
    assert since.endswith("Z")

    fake.merged_prs = [pr(9, labels=["crew:internal"], merged_at="2026-01-05T10:00:00Z")]
    assert main(["inbox", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"Merged without you since {since}" in out
    assert "#9 PR 9" not in out


def test_next_cli(tmp_path, monkeypatch, capsys):
    fake = FakeGitHub(
        issues=[
            issue(1, labels=["crew:ready"], owns=["a/"]),
            issue(2, labels=["crew:in-progress"], owns=["b/"]),
            issue(3, labels=["crew:ready"], owns=["b/c.py"]),
        ],
        open_prs=[],
        merged_prs=[],
    )
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["next", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == ["#1 Unit 1"]
