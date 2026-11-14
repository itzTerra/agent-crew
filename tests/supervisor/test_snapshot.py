import json
from pathlib import Path

from crew.config import load_config
from crew.github import PR_DETAIL_FIELDS, GitHub
from crew.supervisor.snapshot import (
    MARKER,
    OwnerActivity,
    checks_state,
    owner_activity,
    take_snapshot,
)
from tests.test_github import FakeGh
from tests.test_graph import issue

PROJECT = Path(__file__).resolve().parent.parent / "fixtures" / "project"
OWNER, AGENT = "owner-a", "agent-b"


def comment(login, at, body="x"):
    return {"author": {"login": login}, "body": body, "createdAt": at}


def review(login, at, state="COMMENTED"):
    return {"author": {"login": login}, "state": state, "submittedAt": at, "body": ""}


def commit(at):
    return {"oid": "abc", "committedDate": at}


def activity(comments=(), reviews=(), commits=()):
    return owner_activity(list(comments), list(reviews), list(commits), OWNER, AGENT)


def test_owner_comment_before_run_is_unanswered():
    # The owner commented in the evening; the run starts later. Only the order of events counts.
    result = activity(
        comments=[comment(AGENT, "2026-11-09T10:00:00Z"), comment(OWNER, "2026-11-09T19:00:00Z")],
        commits=[commit("2026-11-09T09:00:00Z")],
    )
    assert result == OwnerActivity("feedback", "2026-11-09T19:00:00Z")


def test_latest_owner_action_wins():
    base = [commit("2026-11-09T09:00:00Z")]
    approve_last = activity(
        comments=[comment(OWNER, "2026-11-09T10:00:00Z")],
        reviews=[review(OWNER, "2026-11-09T11:00:00Z", "APPROVED")],
        commits=base,
    )
    assert approve_last == OwnerActivity("approved", "2026-11-09T11:00:00Z")
    comment_last = activity(
        comments=[comment(OWNER, "2026-11-09T12:00:00Z")],
        reviews=[review(OWNER, "2026-11-09T11:00:00Z", "APPROVED")],
        commits=base,
    )
    assert comment_last == OwnerActivity("feedback", "2026-11-09T12:00:00Z")


def test_agent_reply_answers_owner():
    result = activity(
        comments=[comment(OWNER, "2026-11-09T10:00:00Z"), comment(AGENT, "2026-11-09T11:00:00Z")]
    )
    assert result == OwnerActivity("none", "")
    later_commit = activity(
        comments=[comment(OWNER, "2026-11-09T10:00:00Z")], commits=[commit("2026-11-09T10:30:00Z")]
    )
    assert later_commit.kind == "none"
    assert activity() == OwnerActivity("none", "")


def test_owner_login_case_insensitive():
    result = owner_activity(
        [comment("Owner-A", "2026-11-09T10:00:00Z")], [], [], "owner-a", "Agent-B"
    )
    assert result.kind == "feedback"
    answered = owner_activity(
        [comment("owner-a", "2026-11-09T10:00:00Z"), comment("AGENT-B", "2026-11-09T11:00:00Z")],
        [],
        [],
        "Owner-A",
        "agent-b",
    )
    assert answered.kind == "none"


def run(name, status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


def test_checks_state_cases():
    def pr(*checks):
        return {"statusCheckRollup": list(checks)}

    assert checks_state(pr(run("test"), run("lint")), []) == "pass"
    assert checks_state(pr(run("test"), run("lint", conclusion="FAILURE")), []) == "fail"
    assert checks_state(pr(run("test", conclusion="TIMED_OUT")), []) == "fail"
    assert checks_state(pr(run("test", status="IN_PROGRESS", conclusion="")), []) == "pending"
    assert checks_state(pr(), []) == "none"
    assert checks_state(pr(run("lint")), ["test"]) == "pending"
    assert checks_state(pr(run("test"), run("other", conclusion="FAILURE")), ["test"]) == "pass"
    status = {"__typename": "StatusContext", "context": "ci/x", "state": "FAILURE"}
    assert checks_state(pr(status), []) == "fail"


def test_take_snapshot_calls():
    issues = [
        issue(1, labels=["crew:ready"]),
        issue(2, labels=["crew:rough", "crew:owner-decision"]),
    ]
    detail = {
        "number": 9,
        "title": "PR 9",
        "url": "u",
        "state": "OPEN",
        "labels": [{"name": "crew:in-review"}],
        "headRefName": "unit/1-x",
        "closingIssuesReferences": [{"number": 1}],
        "reviews": [],
        "comments": [],
        "commits": [],
        "statusCheckRollup": [],
    }
    comments = {"comments": [comment(OWNER, "2026-11-09T10:00:00Z")]}
    fake = FakeGh(
        [
            (["issue", "list"], json.dumps(issues), 0),
            (["pr", "list"], json.dumps([{"number": 9}]), 0),
            (["pr", "view", "9"], json.dumps(detail), 0),
            (["issue", "view", "2"], json.dumps(comments), 0),
        ]
    )
    snapshot = take_snapshot(GitHub("example/app", run=fake), load_config(PROJECT))
    assert sorted(snapshot.units) == [1, 2]
    assert snapshot.prs == {9: detail}
    assert snapshot.decisions == {2: OwnerActivity("feedback", "2026-11-09T10:00:00Z")}
    views = [c for c in fake.calls if "view" in c]
    assert [c[1:4] for c in views] == [["pr", "view", "9"], ["issue", "view", "2"]]
    assert PR_DETAIL_FIELDS in views[0]
    assert snapshot.problems == [
        type(snapshot.problems[0])(
            9, "PR #9 has crew:in-review, its issue #1 has crew:ready", (), "in-review"
        )
    ]


def test_marked_comments_are_not_owner_activity():
    marked = comment(OWNER, "2026-11-09T19:00:00Z", f"crew run: stuck\n\n{MARKER}")
    assert activity(comments=[marked], commits=[commit("2026-11-09T09:00:00Z")]).kind == "none"


def test_early_owner_approval_survives_the_agent_review():
    # M10: the owner approves while the PR is still in agent review.
    result = activity(
        comments=[comment(AGENT, "2026-11-09T12:00:00Z", "Review round 1: pass")],
        reviews=[review(OWNER, "2026-11-09T11:00:00Z", "APPROVED")],
        commits=[commit("2026-11-09T10:00:00Z")],
    )
    assert result == OwnerActivity("approved", "2026-11-09T11:00:00Z")


def test_new_commits_or_later_feedback_void_an_approval():
    voided = activity(
        reviews=[review(OWNER, "2026-11-09T11:00:00Z", "APPROVED")],
        commits=[commit("2026-11-09T12:00:00Z")],
    )
    assert voided.kind == "none"
    superseded = activity(
        comments=[comment(OWNER, "2026-11-09T12:00:00Z"), comment(AGENT, "2026-11-09T13:00:00Z")],
        reviews=[review(OWNER, "2026-11-09T11:00:00Z", "APPROVED")],
        commits=[commit("2026-11-09T10:00:00Z")],
    )
    assert superseded.kind == "none"


def test_take_snapshot_finds_assignee_drift():
    from crew.labels import AssigneeDrift

    issues = [issue(1, labels=["crew:owner-stuck"]), issue(2, labels=["bug"])]
    issues[1]["assignees"] = [{"login": "owner-a"}]
    merged = [
        {"number": 8, "labels": [{"name": "crew:internal"}], "assignees": [{"login": "agent-b"}]}
    ]
    fake = FakeGh(
        [
            (["issue", "list"], json.dumps(issues), 0),
            (["pr", "list", "merged"], json.dumps(merged), 0),
            (["pr", "list"], "[]", 0),
        ]
    )
    snapshot = take_snapshot(GitHub("example/app", run=fake), load_config(PROJECT))
    assert snapshot.drift == [
        AssigneeDrift(1, ("owner-a",), ()),
        AssigneeDrift(8, (), ("agent-b",)),
    ]


def test_take_snapshot_unsplit_bets_read_closed_issues_only_when_needed():
    pitch = {"number": 27, "title": "Pitch 0001: Core", "headRefName": "pitch/0001", "url": "u"}
    linked = issue(40, body="## Goal\n\nA.\n\n## Bet\n\n#27\n")
    linked["state"] = "CLOSED"
    answers = [
        (["issue", "list", "closed"], json.dumps([linked]), 0),
        (["issue", "list"], json.dumps([]), 0),
        (["pr", "list", "merged"], json.dumps([pitch]), 0),
        (["pr", "list"], json.dumps([]), 0),
    ]
    fake = FakeGh(answers)
    snapshot = take_snapshot(GitHub("example/app", run=fake), load_config(PROJECT))
    assert snapshot.unsplit == {}
    assert fake.calls[-1][1:7] == ["issue", "list", "--repo", "example/app", "--state", "closed"]

    fake = FakeGh(answers[1:])
    snapshot = take_snapshot(GitHub("example/app", run=fake), load_config(PROJECT))
    assert list(snapshot.unsplit) == [27]

    fake = FakeGh([(["issue", "list", "open"], json.dumps([{**linked, "state": "OPEN"}]), 0),
                   *answers])  # fmt: skip
    take_snapshot(GitHub("example/app", run=fake), load_config(PROJECT))
    assert not any("closed" in call for call in fake.calls)
