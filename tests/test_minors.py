"""Smaller edge cases: shared inbox numbers, ID cleanup, name clashes, rough order, 404s."""

import subprocess
from pathlib import Path

from crew.cli import main
from crew.docs.specs import parse_delta, parse_spec
from crew.github import GitHub
from crew.graph import build_units, rough_order
from crew.inbox import owner_inbox
from tests.test_graph import issue
from tests.test_inbox import FakeGitHub, pr

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT = FIXTURES / "project"


def test_issue_and_pr_asks_on_same_number_both_listed():
    units = build_units([issue(5, labels=["crew:owner-decision"])])
    items = owner_inbox(units, [pr(10, labels=["crew:owner-accept"], closes=[5])])
    assert sorted((i.number, i.ask) for i in items) == [(5, "accept"), (5, "decision")]


def test_same_ask_on_issue_and_pr_listed_once_with_pr_link():
    units = build_units([issue(5, labels=["crew:owner-accept"])])
    items = owner_inbox(units, [pr(10, labels=["crew:owner-accept"], closes=[5])])
    assert [(i.number, i.url) for i in items] == [(5, "https://github.com/example/app/pull/10")]


def test_satisfies_ids_are_cleaned(tmp_path):
    text = (FIXTURES / "specs/valid.md").read_text(encoding="utf-8")
    text = text.replace(
        "Satisfies: REQ-ARCH-1, REQ-SRC-2", "**Satisfies:** `REQ-ARCH-1`, REQ-SRC-2."
    )
    path = tmp_path / "spec.md"
    path.write_text(text, encoding="utf-8")
    assert parse_spec(path)[0].requirements[0].satisfies == ["REQ-ARCH-1", "REQ-SRC-2"]


def test_added_name_already_in_target():
    target = parse_spec(FIXTURES / "specs/valid.md")[0]
    text = (FIXTURES / "specs/delta-no-target.md").read_text(encoding="utf-8")
    text = "Target: docs/specs/imports/spec.md\n" + text.replace("Accept PDF", "accept plain text")
    findings = parse_delta(text, FIXTURES / "x.md", target)[1]
    assert [(f.code, f.line) for f in findings] == [("DELTA-EXISTS", 4)]


def test_rough_order():
    units = build_units(
        [
            issue(1, labels=["crew:rough"], created="2026-01-02T00:00:00Z"),
            issue(2, labels=["crew:rough"], created="2026-01-01T00:00:00Z"),
            issue(3, labels=["crew:rough", "crew:must"], created="2026-01-03T00:00:00Z"),
            issue(4, labels=["crew:rough"], deps=[1]),
            issue(5, labels=["crew:rough", "crew:owner-decision"]),
            issue(6, labels=["crew:ready"]),
        ]
    )
    assert rough_order(units) == [3, 1, 2, 4]


def test_next_rough_cli(monkeypatch, capsys):
    fake = FakeGitHub([issue(1, labels=["crew:rough"]), issue(2, labels=["crew:ready"])], [], [])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["next", "--rough", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == ["#1 Unit 1"]


def test_removing_absent_label_is_not_an_error():
    def run(argv, **kwargs):
        if "DELETE" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "gh: Label does not exist (HTTP 404)")
        return subprocess.CompletedProcess(argv, 0, "", "")

    GitHub("example/app", run=run).set_labels(5, add=[], remove=["crew:rough"])
