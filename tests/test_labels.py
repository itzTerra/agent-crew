import json
import shutil
import subprocess
from pathlib import Path

import pytest

from crew.cli import main
from crew.github import GitHub
from crew.labels import (
    FLOW,
    IDEA,
    LABELS,
    LabelProblem,
    Logins,
    StateResult,
    assignee_change,
    label_problems,
    set_state,
    wanted_assignees,
)
from tests.test_github import FakeGh
from tests.test_graph import issue
from tests.test_inbox import pr

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"
REPO = "example/app"
LOGINS = Logins("owner", "bot")


def labels_json(*names, assignees=()):
    return json.dumps(
        {"labels": [{"name": n} for n in names], "assignees": [{"login": a} for a in assignees]}
    )


class AssigningGh(FakeGh):
    """FakeGh whose add-assignees call echoes the logins, leaving out ``refused`` ones."""

    def __init__(self, answers=(), refused=()):
        super().__init__(answers)
        self.refused = set(refused)

    def __call__(self, argv, **kwargs):
        if "POST" in argv and argv[argv.index("POST") + 1].endswith("/assignees"):
            self.calls.append(argv)
            logins = [a.split("=", 1)[1] for a in argv if a.startswith("assignees[]=")]
            kept = [{"login": login} for login in logins if login not in self.refused]
            return subprocess.CompletedProcess(argv, 0, json.dumps({"assignees": kept}), "")
        return super().__call__(argv, **kwargs)


def gh_with(prs, labels_by_number, merged=(), assigned=None, refused=()):
    assigned = assigned or {}
    answers = [
        (["pr", "list", "open"], json.dumps(prs), 0),
        (["pr", "list", "merged"], json.dumps(list(merged)), 0),
    ]
    answers += [
        ([f"repos/{REPO}/issues/{n}"], labels_json(*names, assignees=assigned.get(n, ())), 0)
        for n, names in labels_by_number.items()
    ]
    fake = AssigningGh(answers, refused)
    return GitHub(REPO, run=fake), fake


def assignee_calls(fake):
    """(method, number, login) for each assignee write."""
    out = []
    for argv in fake.calls:
        if "--method" not in argv:
            continue
        method, path = argv[argv.index("--method") + 1], argv[argv.index("--method") + 2]
        if path.endswith("/assignees"):
            number = int(path.split("/issues/")[1].split("/")[0])
            logins = [a.split("=", 1)[1] for a in argv if a.startswith("assignees[]=")]
            out += [(method, number, login) for login in logins]
    return out


def label_calls(fake):
    """(method, number, label or None) for each label write."""
    out = []
    for argv in fake.calls:
        if "--method" not in argv:
            continue
        method, path = argv[argv.index("--method") + 1], argv[argv.index("--method") + 2]
        number = int(path.split("/issues/")[1].split("/")[0])
        if path.endswith("/assignees"):
            continue
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
    assert set_state(github, 9, "in-review", LOGINS).numbers == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 9, "crew:owner-accept"),
        ("POST", 9, "crew:in-review"),
    ]


def test_set_state_from_issue_reaches_its_open_prs():
    github, fake = gh_with(
        [pr(9, closes=[5]), pr(10, closes=[6])],
        {5: ["crew:in-progress"], 9: []},
    )
    assert set_state(github, 5, "in-review", LOGINS).numbers == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 5, "crew:in-progress"),
        ("POST", 5, "crew:in-review"),
        ("POST", 9, "crew:in-review"),
    ]


def test_set_state_from_one_issue_moves_every_issue_its_pr_closes():
    # A PR closing #5 and #6: moving #5 (as the implementer does) moves the PR and #6 too.
    github, fake = gh_with(
        [pr(9, closes=[5, 6])],
        {
            5: ["crew:changes-requested"],
            6: ["crew:changes-requested"],
            9: ["crew:in-review"],
        },
    )
    assert set_state(github, 5, "in-review", LOGINS).numbers == [5, 6, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 5, "crew:changes-requested"),
        ("DELETE", 6, "crew:changes-requested"),
        ("POST", 5, "crew:in-review"),
        ("POST", 6, "crew:in-review"),
    ]


def test_set_state_keeps_owner_decision():
    github, fake = gh_with([], {3: ["crew:rough", "crew:owner-decision"]})
    assert set_state(github, 3, "ready", LOGINS).numbers == [3]
    assert sorted(label_calls(fake)) == [("DELETE", 3, "crew:rough"), ("POST", 3, "crew:ready")]


def test_set_state_done_clears_flow_labels():
    github, fake = gh_with(
        [],
        {5: ["crew:in-review", "crew:internal"], 9: ["crew:in-review", "crew:changes-requested"]},
        merged=[pr(9, closes=[5])],
    )
    assert set_state(github, 5, "done", LOGINS).numbers == [5, 9]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 5, "crew:in-review"),
        ("DELETE", 9, "crew:changes-requested"),
        ("DELETE", 9, "crew:in-review"),
    ]


def test_wanted_assignees():
    assert wanted_assignees({"crew:owner-decision", "crew:in-progress"}, LOGINS) == {"owner"}
    assert wanted_assignees({"crew:owner-accept"}, LOGINS) == {"owner"}
    assert wanted_assignees({"crew:in-review"}, LOGINS) == {"bot"}
    assert wanted_assignees({"crew:in-progress"}, LOGINS) == {"bot"}
    assert wanted_assignees({"crew:changes-requested"}, LOGINS) == {"bot"}
    assert wanted_assignees({"crew:ready"}, LOGINS) == set()
    assert wanted_assignees({"crew:idea"}, LOGINS) == set()
    assert wanted_assignees({"crew:owner-facing", "crew:ready"}, LOGINS) == set()
    assert wanted_assignees({"bug"}, LOGINS) is None
    assert wanted_assignees(set(), LOGINS, closed=True) is None
    assert wanted_assignees({"crew:in-review"}, LOGINS, closed=True) == set()
    assert wanted_assignees({"crew:owner-decision"}, LOGINS, closed=True) == set()


def test_assignee_change_leaves_others():
    assert assignee_change({"crew:ready"}, {"owner", "carol"}, LOGINS) == ([], ["owner"])
    assert assignee_change({"crew:owner-stuck"}, {"bot", "carol"}, LOGINS) == (["owner"], ["bot"])
    assert assignee_change({"bug"}, {"owner", "bot"}, LOGINS) == ([], [])
    assert assignee_change({"crew:in-review"}, {"bot"}, LOGINS) == ([], [])


def test_set_state_assigns_agent_and_owner():
    # PR 9 closes 5 and 6; only 5 waits on an owner decision.
    github, fake = gh_with(
        [pr(9, closes=[5, 6])],
        {5: ["crew:in-progress", "crew:owner-decision"], 6: ["crew:in-progress"], 9: []},
        assigned={5: ["bot"], 6: ["bot", "carol"]},
    )
    result = set_state(github, 9, "in-review", LOGINS)
    assert result == StateResult([5, 6, 9], [])
    assert sorted(assignee_calls(fake)) == [
        ("DELETE", 5, "bot"),
        ("POST", 5, "owner"),
        ("POST", 9, "bot"),
    ]


def test_set_state_warns_when_login_dropped():
    github, fake = gh_with([], {9: ["crew:in-progress"]}, refused={"bot"})
    result = set_state(github, 9, "in-review", LOGINS)
    assert result.warnings == ["#9: GitHub did not assign bot; is it a collaborator?"]
    assert sorted(label_calls(fake)) == [
        ("DELETE", 9, "crew:in-progress"),
        ("POST", 9, "crew:in-review"),
    ]


def test_set_state_done_unassigns_everyone_managed():
    github, fake = gh_with(
        [],
        {5: ["crew:in-review", "crew:owner-decision"], 9: ["crew:in-review"]},
        merged=[pr(9, closes=[5])],
        assigned={5: ["owner"], 9: ["bot", "carol"]},
    )
    assert set_state(github, 5, "done", LOGINS).numbers == [5, 9]
    assert sorted(assignee_calls(fake)) == [("DELETE", 5, "owner"), ("DELETE", 9, "bot")]


def test_set_state_cli_prints_warnings(monkeypatch, capsys):
    github, _ = gh_with([], {9: ["crew:in-progress"]}, refused={"agent-b"})
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    assert main(["labels", "set-state", "9", "in-review", "--root", str(PROJECT)]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["#9: crew:in-review"]
    assert captured.err.splitlines() == ["#9: GitHub did not assign agent-b; is it a collaborator?"]


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
        LabelProblem(
            9, "PR #9 has crew:owner-accept, its issue #5 has crew:in-review", (), "owner-accept"
        ),
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


def test_label_problems_issue_out_of_step_with_its_only_pr_is_fixable():
    problems = label_problems(
        open_issues=[
            issue(5, labels=["crew:in-review"]),
            issue(6, labels=["crew:changes-requested"]),
            issue(7, labels=["crew:ready"]),
        ],
        closed_issues=[],
        open_prs=[
            pr(9, labels=["crew:in-review"], closes=[5, 6]),
            pr(10, labels=["crew:in-review"], closes=[7]),
            pr(11, labels=["crew:changes-requested"], closes=[7]),
        ],
        merged_prs=[],
    )
    assert [(p.number, p.fix_state) for p in problems] == [(9, "in-review"), (10, None), (11, None)]


def test_labels_check_fix_moves_issue_to_its_prs_state(monkeypatch, capsys):
    fake = FakeLabelsGitHub(
        open_issues=[issue(5, labels=["crew:in-review"]), issue(6, labels=["crew:rough"])],
        open_prs=[pr(9, labels=["crew:in-review"], closes=[5, 6])],
    )
    moved = []
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    monkeypatch.setattr(
        "crew.labels.set_state",
        lambda github, n, state, logins: (
            moved.append((n, state, logins)) or StateResult([5, 6, 9], [])
        ),
    )
    assert main(["labels", "check", "--fix", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "#9: PR #9 has crew:in-review, its issue #6 has crew:rough",
        "fixed #9: #5, #6, #9 now in-review",
    ]
    assert moved == [(9, "in-review", Logins("owner-a", "agent-b"))]


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
        set_state(github, 4, "in-review", LOGINS)
    with pytest.raises(ValueError, match=r"doesn't close #4"):
        set_state(github, 11, "in-review", LOGINS)
    assert label_calls(fake) == []


def test_set_state_cli_reports_unit_pr_problem(monkeypatch, capsys):
    github, _ = gh_with([unit_pr(11, 4, closes=[1])], {4: ["crew:in-progress"]})
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    assert main(["labels", "set-state", "4", "in-review", "--root", str(PROJECT)]) != 0
    assert "put `Closes #4` in its body" in capsys.readouterr().err


def test_idea_label_exists():
    assert IDEA == "crew:idea"
    assert IDEA in {label.name for label in LABELS}
    assert IDEA not in FLOW


def test_label_problems_idea_with_work_or_proposal_label():
    problems = label_problems(
        open_issues=[
            issue(3, labels=["crew:idea"]),
            issue(4, labels=["crew:idea", "crew:rough"]),
            issue(5, labels=["crew:idea", "crew:later"]),
            issue(6, labels=["crew:idea", "crew:owner-proposal"]),
        ],
        closed_issues=[],
        open_prs=[],
        merged_prs=[],
    )
    assert problems == [
        LabelProblem(4, "parked idea also has crew:rough", ()),
        LabelProblem(6, "parked idea also has crew:owner-proposal", ()),
    ]


def test_label_problems_two_priorities():
    problems = label_problems(
        open_issues=[issue(3, labels=["crew:must"]), issue(4, labels=["crew:must", "crew:later"])],
        closed_issues=[],
        open_prs=[pr(9, labels=["crew:should", "crew:later"])],
        merged_prs=[],
    )
    assert problems == [
        LabelProblem(4, "has more than one priority label: crew:must, crew:later", ()),
        LabelProblem(9, "has more than one priority label: crew:should, crew:later", ()),
    ]


def test_ask_adds_label_and_assigns_owner_removing_agent():
    from crew.labels import set_ask

    github, fake = gh_with([], {4: ["crew:in-progress"]}, assigned={4: ["bot", "carol"]})
    assert set_ask(github, 4, "decision", True, LOGINS) is None
    assert label_calls(fake) == [("POST", 4, "crew:owner-decision")]
    assert sorted(assignee_calls(fake)) == [("DELETE", 4, "bot"), ("POST", 4, "owner")]


def test_clear_hands_back_to_agent():
    from crew.labels import set_ask

    github, fake = gh_with(
        [], {4: ["crew:in-progress", "crew:owner-decision"]}, assigned={4: ["owner"]}
    )
    assert set_ask(github, 4, "decision", False, LOGINS) is None
    assert label_calls(fake) == [("DELETE", 4, "crew:owner-decision")]
    assert sorted(assignee_calls(fake)) == [("DELETE", 4, "owner"), ("POST", 4, "bot")]


def test_clear_on_a_ready_issue_unassigns_everyone_managed():
    from crew.labels import set_ask

    github, fake = gh_with([], {4: ["crew:ready", "crew:owner-proposal"]}, assigned={4: ["owner"]})
    set_ask(github, 4, "proposal", False, LOGINS)
    assert assignee_calls(fake) == [("DELETE", 4, "owner")]


def test_ask_rejects_accept():
    from crew.labels import set_ask

    github, fake = gh_with([], {4: ["crew:in-progress"]})
    with pytest.raises(ValueError, match="decision, proposal"):
        set_ask(github, 4, "accept", True, LOGINS)
    assert fake.calls == []


def test_labels_ask_cli(monkeypatch, capsys):
    github, fake = gh_with([], {4: ["crew:in-progress"]}, refused={"owner-a"})
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    assert main(["labels", "ask", "4", "decision", "--root", str(PROJECT)]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["#4: crew:owner-decision"]
    assert captured.err.splitlines() == ["#4: GitHub did not assign owner-a; is it a collaborator?"]


def test_labels_clear_cli(monkeypatch, capsys):
    github, fake = gh_with([], {4: ["crew:in-progress", "crew:owner-proposal"]})
    monkeypatch.setattr("crew.cli.make_github", lambda repo: github)
    assert main(["labels", "clear", "4", "proposal", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.splitlines() == ["#4: removed crew:owner-proposal"]
    assert label_calls(fake) == [("DELETE", 4, "crew:owner-proposal")]


def test_labels_ask_cli_rejects_other_asks(capsys):
    assert main(["labels", "ask", "4", "stuck", "--root", str(PROJECT)]) == 2
    assert "decision" in capsys.readouterr().err
