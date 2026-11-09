import json
import shutil
from pathlib import Path

import pytest

from crew.cli import main
from crew.github import GitHub
from crew.labels import FLOW, LabelProblem, label_problems, set_state
from tests.test_github import FakeGh
from tests.test_graph import issue
from tests.test_inbox import pr

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"
REPO = "example/app"


def labels_json(*names):
    return json.dumps({"labels": [{"name": n} for n in names]})


def gh_with(prs, labels_by_number, merged=()):
    answers = [
        (["pr", "list", "open"], json.dumps(prs), 0),
        (["pr", "list", "merged"], json.dumps(list(merged)), 0),
    ]
    answers += [
        ([f"repos/{REPO}/issues/{n}"], labels_json(*names), 0)
        for n, names in labels_by_number.items()
    ]
    fake = FakeGh(answers)
    return GitHub(REPO, run=fake), fake


def label_calls(fake):
    """(method, number, label or None) for each label write."""
    out = []
    for argv in fake.calls:
        if "--method" not in argv:
            continue
        method, path = argv[argv.index("--method") + 1], argv[argv.index("--method") + 2]
        number = int(path.split("/issues/")[1].split("/")[0])
        if method == "POST" and path.endswith("/labels"):
            out += [("POST", number, a.split("=", 1)[1]) for a in argv if a.startswith("labels[]=")]
        elif method == "DELETE":
            out.append(("DELETE", number, path.rsplit("/", 1)[1].replace("%3A", ":")))
    return out


def test_set_state_moves_issue_and_pr_together():
    github, fake = gh_with(
        [pr(9, labels=["crew:owner-accept"], closes=[5])],
        {5: ["crew:in-review"], 9: ["crew:owner-accept", "crew:owner-facing"]},
    )
    assert set_state(github, 9, "in-review") == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 9, "crew:owner-accept"),
        ("POST", 9, "crew:in-review"),
    ]


def test_set_state_from_issue_reaches_its_open_prs():
    github, fake = gh_with(
        [pr(9, closes=[5]), pr(10, closes=[6])],
        {5: ["crew:in-progress"], 9: []},
    )
    assert set_state(github, 5, "in-review") == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 5, "crew:in-progress"),
        ("POST", 5, "crew:in-review"),
        ("POST", 9, "crew:in-review"),
    ]


def test_set_state_keeps_owner_decision():
    github, fake = gh_with([], {3: ["crew:rough", "crew:owner-decision"]})
    assert set_state(github, 3, "ready") == [3]
    assert sorted(label_calls(fake)) == [("DELETE", 3, "crew:rough"), ("POST", 3, "crew:ready")]


def test_set_state_done_clears_flow_labels():
    github, fake = gh_with(
        [],
        {5: ["crew:in-review", "crew:internal"], 9: ["crew:in-review", "crew:changes-requested"]},
        merged=[pr(9, closes=[5])],
    )
    assert set_state(github, 5, "done") == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 5, "crew:in-review"),
        ("DELETE", 9, "crew:changes-requested"),
        ("DELETE", 9, "crew:in-review"),
    ]


def test_set_state_unknown_state_is_cli_error(capsys):
    assert main(["labels", "set-state", "5", "finished", "--root", str(PROJECT)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and "owner-accept" in err and err.count("\n") == 1


def closed(number, labels):
    item = issue(number, labels=labels)
    item["state"] = "CLOSED"
    return item


def test_label_problems_kinds():
    problems = label_problems(
        open_issues=[
            issue(1, labels=["crew:ready", "crew:in-progress"]),
            issue(5, labels=["crew:in-review"]),
        ],
        closed_issues=[closed(2, ["crew:in-review", "crew:internal"])],
        open_prs=[pr(9, labels=["crew:owner-accept"], closes=[5])],
        merged_prs=[pr(8, labels=["crew:owner-accept"], merged_at="2026-01-01T00:00:00Z")],
    )
    assert problems == [
        LabelProblem(2, "closed issue still has crew:in-review", ("crew:in-review",)),
        LabelProblem(8, "merged PR still has crew:owner-accept", ("crew:owner-accept",)),
        LabelProblem(1, "has more than one state label: crew:ready, crew:in-progress", ()),
        LabelProblem(9, "PR #9 has crew:owner-accept, its issue #5 has crew:in-review", ()),
    ]
    assert FLOW[0] == "crew:rough"


class FakeLabelsGitHub:
    def __init__(self, open_issues=(), closed_issues=(), open_prs=(), merged_prs=()):
        self.data = {
            "issues": {"open": list(open_issues), "closed": list(closed_issues)},
            "prs": {"open": list(open_prs), "merged": list(merged_prs)},
        }
        self.removed = []

    def list_issues(self, state="open"):
        return self.data["issues"][state]

    def list_prs(self, state="open"):
        return self.data["prs"][state]

    def set_labels(self, number, add, remove):
        self.removed.append((number, list(add), list(remove)))


def test_labels_check_fix_cli(monkeypatch, capsys):
    fake = FakeLabelsGitHub(closed_issues=[closed(2, ["crew:in-review"])])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["labels", "check", "--root", str(PROJECT)]) == 1
    assert capsys.readouterr().out.splitlines() == ["#2: closed issue still has crew:in-review"]
    assert main(["labels", "check", "--fix", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "#2: closed issue still has crew:in-review",
        "fixed #2",
    ]
    assert fake.removed == [(2, [], ["crew:in-review"])]

    fake = FakeLabelsGitHub(open_issues=[issue(1, labels=["crew:ready", "crew:rough"])])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["labels", "check", "--fix", "--root", str(PROJECT)]) == 1
    assert fake.removed == []


def test_labels_check_clean(monkeypatch, capsys):
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeLabelsGitHub())
    assert main(["labels", "check", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.strip() == "no label problems"


def test_inbox_lists_label_problems(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    fake = FakeLabelsGitHub(
        open_issues=[issue(1, labels=["crew:ready", "crew:rough"])],
        closed_issues=[closed(2, ["crew:in-review"])],
    )
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["inbox", "--peek", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith(
        "Label problems\n"
        "  #2: closed issue still has crew:in-review\n"
        "  #1: has more than one state label: crew:rough, crew:ready"
    )


def unit_pr(number, unit, closes):
    item = pr(number, labels=["crew:owner-decision"], closes=closes)
    item["headRefName"] = f"unit/{unit}-design-system"
    return item


def test_label_problems_unit_pr_that_closes_another_issue():
    problems = label_problems(
        open_issues=[issue(4, labels=["crew:in-progress"])],
        closed_issues=[],
        open_prs=[unit_pr(11, 4, closes=[1]), unit_pr(12, 6, closes=[6])],
        merged_prs=[],
    )
    assert problems == [
        LabelProblem(
            11,
            "PR #11 is on branch unit/4-design-system but doesn't close #4; "
            "put `Closes #4` in its body",
            (),
        )
    ]


def test_set_state_refuses_a_unit_pr_that_closes_another_issue():
    github, fake = gh_with([unit_pr(11, 4, closes=[1])], {4: ["crew:in-progress"]})
    with pytest.raises(ValueError, match=r"PR #11 is on branch unit/4-design-system but doesn't"):
        set_state(github, 4, "in-review")
    with pytest.raises(ValueError, match=r"doesn't close #4"):
        set_state(github, 11, "in-review")
    assert label_calls(fake) == []


def test_set_state_cli_reports_unit_pr_problem(monkeypatch, capsys):
    github, _ = gh_with([unit_pr(11, 4, closes=[1])], {4: ["crew:in-progress"]})
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    assert main(["labels", "set-state", "4", "in-review", "--root", str(PROJECT)]) != 0
    assert "put `Closes #4` in its body" in capsys.readouterr().err
