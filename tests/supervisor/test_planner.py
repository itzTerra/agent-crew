from pathlib import Path

from crew.config import load_config
from crew.graph import build_units
from crew.labels import LabelProblem
from crew.supervisor.planner import (
    OWNER_IDLE,
    Action,
    Housekeeping,
    Live,
    idle_reason,
    plan,
    slug,
    unit_branch,
)
from crew.supervisor.snapshot import OwnerActivity, Snapshot
from tests.test_graph import issue

PROJECT = Path(__file__).resolve().parent.parent / "fixtures" / "project"
CONFIG = load_config(PROJECT)
OWNER, AGENT = CONFIG.owner_login, CONFIG.agent_login
EARLY, LATE = "2026-11-09T09:00:00Z", "2026-11-09T19:00:00Z"


def pr(number, closes, labels, checks="pass", comments=(), reviews=(), commits=(EARLY,)):
    rollup = {
        "pass": [{"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}],
        "fail": [{"name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}],
        "pending": [{"name": "test", "status": "IN_PROGRESS", "conclusion": ""}],
        "none": [],
    }[checks]
    return {
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/example/app/pull/{number}",
        "state": "OPEN",
        "labels": [{"name": n} for n in labels],
        "headRefName": f"unit/{closes}-unit-{closes}",
        "closingIssuesReferences": [{"number": closes}],
        "reviews": list(reviews),
        "comments": list(comments),
        "commits": [{"committedDate": at} for at in commits],
        "statusCheckRollup": rollup,
    }


def owner_comment(at=LATE):
    return {"author": {"login": OWNER}, "body": "please change", "createdAt": at}


def owner_approval(at=LATE):
    return {"author": {"login": OWNER}, "state": "APPROVED", "submittedAt": at, "body": ""}


def snap(issues, prs=(), decisions=None, problems=()):
    return Snapshot(
        units=build_units(list(issues)),
        prs={p["number"]: p for p in prs},
        decisions=decisions or {},
        problems=list(problems),
    )


def make_plan(snapshot, live=(), paused=(), free_slots=2, minutes_left=600, config=CONFIG):
    return plan(snapshot, list(live), list(paused), config, free_slots, minutes_left)


def kinds(result):
    return [(a.kind, a.number) for a in result.actions]


def test_slug_and_unit_branch():
    assert slug("Add CSV export (v2)!") == "add-csv-export-v2"
    assert unit_branch(12, "Add CSV export (v2)!") == "unit/12-add-csv-export-v2"
    long = slug("Make the import wizard remember the last folder used for every kind of file")
    assert len(long) <= 40 and not long.endswith("-")
    assert long == "make-the-import-wizard-remember-the-last"
    assert len(slug("x" * 60)) == 40


def test_owner_feedback_becomes_housekeeping_then_fix():
    issues = [issue(5, labels=["crew:owner-accept"], owns=["a/"])]
    first = make_plan(snap(issues, [pr(9, 5, ["crew:owner-accept"], comments=[owner_comment()])]))
    assert first.housekeeping == [Housekeeping(9, "changes-requested", None)]
    assert first.actions == []
    issues = [issue(5, labels=["crew:changes-requested"], owns=["a/"])]
    second = make_plan(
        snap(issues, [pr(9, 5, ["crew:changes-requested"], comments=[owner_comment()])])
    )
    assert second.housekeeping == []
    assert second.actions == [
        Action(
            "fix", 9, 5, "implementer", None,
            "Use crew:implement on issue #5: changes are requested on PR #9 "
            "(https://github.com/example/app/pull/9).",
            "unit/5-unit-5",
        )
    ]  # fmt: skip


def test_fix_waits_for_open_dependencies():
    # A fix, like an implement, starts only once the unit's dependencies are closed.
    issues = [
        issue(132, deps=[143, 151], labels=["crew:changes-requested"], owns=["a/"]),
        issue(143, labels=["crew:rough"], owns=["b/"]),
        issue(151, labels=["crew:rough"], owns=["c/"]),
    ]
    result = make_plan(snap(issues, [pr(149, 132, ["crew:changes-requested"])]))
    assert ("fix", 149) not in kinds(result)
    assert "#149: depends on open #143, #151" in result.waiting


def test_ready_unit_with_open_pr_does_not_block_its_dependency():
    # #132 is back at ready with PR #149 open; its owned paths overlap #144, which it needs.
    issues = [
        issue(132, deps=[144], labels=["crew:ready"], owns=["app/"]),
        issue(144, labels=["crew:ready"], owns=["app/editor/"]),
    ]
    result = make_plan(snap(issues, [pr(149, 132, [])]))
    assert kinds(result) == [("implement", 144)]
    assert "#144: owns overlap with #132" not in result.waiting


def test_ci_failure_housekeeping_names_checks():
    issues = [issue(5, labels=["crew:in-review"], owns=["a/"])]
    result = make_plan(snap(issues, [pr(9, 5, ["crew:in-review"], checks="fail")]))
    assert result.housekeeping == [
        Housekeeping(9, "changes-requested", "CI failed: test. (crew run)")
    ]
    assert result.actions == []


def test_approved_owner_accept_merges():
    issues = [issue(5, labels=["crew:owner-accept"], owns=["a/"])]
    result = make_plan(snap(issues, [pr(9, 5, ["crew:owner-accept"], reviews=[owner_approval()])]))
    (action,) = result.actions
    assert (action.kind, action.number, action.issue, action.role) == ("merge", 9, 5, "implementer")
    assert action.branch == "unit/5-unit-5"
    assert action.prompt.startswith(
        "Use crew:merge on PR #9 (https://github.com/example/app/pull/9). The owner approved it;"
    )


def test_review_model_by_kind():
    internal = make_plan(
        snap([issue(5, labels=["crew:in-review"], owns=["a/"])], [pr(9, 5, ["crew:in-review"])])
    )
    assert internal.actions == [
        Action("review", 9, 5, "reviewer", "sonnet",
               "Use crew:review on PR #9 (https://github.com/example/app/pull/9).",
               "unit/5-unit-5", detach=True)
    ]  # fmt: skip
    facing = make_plan(
        snap(
            [issue(5, labels=["crew:in-review", "crew:owner-facing"], owns=["a/"])],
            [pr(9, 5, ["crew:in-review"], checks="none")],
        )
    )
    assert facing.actions[0].model is None


def test_pending_checks_wait_and_not_idle():
    result = make_plan(
        snap(
            [issue(5, labels=["crew:in-review"], owns=["a/"])],
            [pr(9, 5, ["crew:in-review"], checks="pending")],
        )
    )
    assert result.actions == [] and result.housekeeping == []
    assert any("#9" in line and "checks" in line for line in result.waiting)
    assert result.idle is False


def test_followup_on_answered_decision():
    issues = [
        issue(3, labels=["crew:rough", "crew:owner-decision"], owns=["c/"]),
        issue(4, labels=["crew:rough", "crew:owner-decision"], owns=["d/"]),
    ]
    decisions = {3: OwnerActivity("feedback", LATE), 4: OwnerActivity("none", "")}
    result = make_plan(snap(issues, decisions=decisions))
    assert result.actions == [
        Action(
            "followup", 3, None, "architect", None,
            "The owner answered on #3 (https://github.com/example/app/issues/3). Continue from "
            "their answer: for a unit, use crew:refine on issue #3 only; for a decision "
            "document, write the ADR per your brief.",
            None,
        )
    ]  # fmt: skip


def test_followup_on_decision_pr_not_housekeeping():
    issues = [issue(5, labels=["crew:owner-accept"], owns=["a/"])]
    prs = [pr(9, 5, ["crew:owner-accept", "crew:owner-decision"], comments=[owner_comment()])]
    result = make_plan(snap(issues, prs))
    assert result.housekeeping == []
    assert kinds(result) == [("followup", 9)]


def test_resume_only_paused_units():
    issues = [
        issue(5, labels=["crew:in-progress"], owns=["a/"]),
        issue(6, labels=["crew:in-progress"], owns=["b/"]),
        issue(7, labels=["crew:ready"], owns=["b/x.py"]),
        issue(8, labels=["crew:ready"], owns=["a/y.py"]),
    ]
    paused = [{"number": 5, "branch": "unit/5-unit-5"}, {"number": 99, "branch": "unit/99-x"}]
    result = make_plan(snap(issues), paused=paused, free_slots=3)
    assert kinds(result) == [("resume", 5)]
    assert result.actions[0].prompt == (
        "Use crew:implement on issue #5: resume the work pushed on branch unit/5-unit-5 in an "
        "earlier run."
    )
    assert result.actions[0].branch == "unit/5-unit-5"
    assert "#7: owns overlap with #6" in result.waiting
    assert "#8: owns overlap with #5" in result.waiting


def test_priority_order_and_free_slots():
    issues = [
        issue(5, labels=["crew:owner-accept"], owns=["a/"]),
        issue(6, labels=["crew:changes-requested"], owns=["b/"]),
        issue(7, labels=["crew:ready"], owns=["c/"]),
    ]
    prs = [
        pr(9, 5, ["crew:owner-accept"], reviews=[owner_approval()]),
        pr(10, 6, ["crew:changes-requested"]),
    ]
    one = make_plan(snap(issues, prs), free_slots=1)
    assert kinds(one) == [("merge", 9)]
    assert one.idle is False
    three = make_plan(snap(issues, prs), free_slots=3)
    assert kinds(three) == [("merge", 9), ("fix", 10), ("implement", 7)]
    assert three.actions[2].branch == "unit/7-unit-7"
    assert three.actions[2].prompt == (
        "Use crew:implement on issue #7 (https://github.com/example/app/issues/7)."
    )


def test_not_enough_time_drops_action():
    issues = [issue(7, labels=["crew:ready"], owns=["c/"])]
    result = make_plan(snap(issues), minutes_left=60)
    assert result.actions == []
    assert "not enough time for implement #7 (90 min)" in result.waiting
    assert result.idle is False


def test_refine_ahead_keeps_one_refiner():
    issues = [
        issue(1, labels=["crew:rough"], owns=["a/"]),
        issue(2, labels=["crew:rough"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(4, deps=[2], labels=["crew:ready"], owns=["d/"]),
    ]
    result = make_plan(snap(issues), free_slots=3)
    assert kinds(result) == [("implement", 3), ("refine", 2)]
    assert result.actions[1].prompt == (
        "Use crew:refine on issue #2 only (https://github.com/example/app/issues/2)."
    )
    assert result.actions[1].branch is None
    busy = make_plan(snap(issues), live=[Live("refine", 2, None)], free_slots=3)
    assert kinds(busy) == [("implement", 3)]


def test_stall_refines_the_blocker():
    issues = [
        issue(140, labels=["crew:rough"], owns=["a/"]),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132], labels=["crew:ready"], owns=["c/"]),
        issue(58, labels=["crew:rough", "crew:must"], owns=["d/"]),
        issue(59, labels=["crew:rough", "crew:must"], owns=["e/"]),
    ]
    result = make_plan(snap(issues), free_slots=3)
    assert kinds(result) == [("refine", 140)]
    assert result.idle is False


def test_blocker_refined_even_with_enough_ready():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:ready"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(7, labels=["crew:ready"], owns=["g/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["d/"]),
        issue(5, labels=["crew:rough"], owns=["e/"]),
        issue(6, labels=["crew:rough", "crew:must"], owns=["f/"]),
    ]
    # Two picks fill the slots; #3 and #7 can still start, so the count alone plans no refine.
    result = make_plan(snap(issues), free_slots=2)
    assert kinds(result) == [("implement", 1), ("implement", 2)]
    assert "no free agent slot for refine #5" in result.waiting


def test_blocked_ready_units_dont_count():
    issues = [
        issue(1, labels=["crew:in-review"], owns=["a/"]),
        issue(2, deps=[1], labels=["crew:ready"], owns=["b/"]),
        issue(3, deps=[1], labels=["crew:ready"], owns=["c/"]),
        issue(4, labels=["crew:rough"], owns=["d/"]),
    ]
    prs = [pr(9, 1, ["crew:in-review"], checks="pending")]
    result = make_plan(snap(issues, prs), free_slots=2)
    assert kinds(result) == [("refine", 4)]


def test_occupied_blocker_leaves_no_other_refine():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:ready"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(7, labels=["crew:ready"], owns=["g/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["d/"]),
        issue(5, labels=["crew:rough"], owns=["e/"]),
        issue(6, labels=["crew:rough"], owns=["f/"]),
    ]
    # One live agent plus one slot: #1 and #2 are picked, #3 and #7 can still start.
    result = make_plan(snap(issues), live=[Live("followup", 5, None)], free_slots=1)
    assert [a for a in result.actions if a.kind == "refine"] == []
    assert not any("slot for refine" in line for line in result.waiting)
    assert "#6: not refined yet: 2 ready units can start (refine_ahead 2)" in result.waiting


def test_units_held_by_owner_accept_paths_dont_stop_refinement():
    # #135 and #136 wait behind #5's paths until the owner accepts it: refine meanwhile.
    issues = [
        issue(5, labels=["crew:owner-accept"], owns=["app/"]),
        issue(135, labels=["crew:ready"], owns=["app/upload/"]),
        issue(136, labels=["crew:ready"], owns=["app/export/"]),
        issue(58, labels=["crew:rough"], owns=["d/"]),
        issue(133, labels=["crew:rough"], owns=["e/"]),
    ]
    result = make_plan(snap(issues, [pr(9, 5, ["crew:owner-accept"])]), free_slots=2)
    assert kinds(result) == [("refine", 58)]


def test_rough_units_left_unrefined_say_why():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:ready"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(4, labels=["crew:ready"], owns=["d/"]),
        issue(58, labels=["crew:rough"], owns=["e/"]),
        issue(133, labels=["crew:rough"], owns=["f/"]),
    ]
    result = make_plan(snap(issues), free_slots=2)
    assert kinds(result) == [("implement", 1), ("implement", 2)]
    reason = "not refined yet: 2 ready units can start (refine_ahead 2)"
    assert f"#58: {reason}" in result.waiting
    assert f"#133: {reason}" in result.waiting


def test_parked_idea_is_never_picked():
    issues = [issue(1, labels=["crew:idea"], owns=["a/"])]
    result = make_plan(snap(issues), free_slots=3)
    assert result.actions == []


def test_live_agent_target_skipped():
    issues = [issue(5, labels=["crew:in-review"], owns=["a/"])]
    prs = [pr(9, 5, ["crew:in-review"])]
    result = make_plan(snap(issues, prs), live=[Live("implement", 5, None)])
    assert result.actions == []
    assert "#9: an agent is working on it" in result.waiting


def test_label_problem_target_skipped():
    issues = [issue(5, labels=["crew:in-review"], owns=["a/"])]
    prs = [pr(9, 5, ["crew:in-review"])]
    problem = LabelProblem(9, "has more than one state label: x, y", ())
    result = make_plan(snap(issues, prs, problems=[problem]))
    assert result.actions == []
    assert "#9: label problem: has more than one state label: x, y" in result.waiting


def test_idle_when_everything_waits_on_owner():
    issues = [
        issue(5, labels=["crew:owner-accept"], owns=["a/"]),
        issue(6, labels=["crew:rough", "crew:owner-decision"], owns=["b/"]),
    ]
    result = make_plan(
        snap(issues, [pr(9, 5, ["crew:owner-accept"])], decisions={6: OwnerActivity("none", "")})
    )
    assert result.actions == [] and result.housekeeping == []
    assert result.idle is True


def test_approval_after_feedback_returns_to_owner_accept():
    # I10: the owner comments, housekeeping sets changes-requested, then the owner approves.
    issues = [issue(5, labels=["crew:changes-requested"], owns=["a/"])]
    prs = [
        pr(9, 5, ["crew:changes-requested"],
           comments=[owner_comment("2026-11-09T19:00:00Z")],
           reviews=[owner_approval("2026-11-09T19:30:00Z")])
    ]  # fmt: skip
    result = make_plan(snap(issues, prs))
    assert result.housekeeping == [Housekeeping(9, "owner-accept", None)]
    assert result.actions == []


def test_design_units_go_to_the_designer():
    issues = [
        issue(3, labels=["crew:ready"], owns=["a/"]),
        issue(4, labels=["crew:ready", "crew:design"], owns=["b/"]),
        issue(5, labels=["crew:in-progress", "crew:design"], owns=["c/"]),
        issue(6, labels=["crew:changes-requested", "crew:design"], owns=["d/"]),
    ]
    prs = [pr(10, 6, ["crew:changes-requested", "crew:design"])]
    paused = [{"number": 5, "branch": "unit/5-unit-5"}]
    result = make_plan(snap(issues, prs), paused=paused, free_slots=4)
    roles = {(a.kind, a.number): a.role for a in result.actions}
    assert roles == {
        ("fix", 10): "designer",
        ("resume", 5): "designer",
        ("implement", 3): "implementer",
        ("implement", 4): "designer",
    }
    design = next(a for a in result.actions if a.number == 4)
    assert design.prompt == (
        "Use crew:implement on issue #4 (https://github.com/example/app/issues/4). It is design "
        "work: deliver the alternatives as mockups per your brief."
    )
    assert design.branch == "unit/4-unit-4"


def test_design_label_on_the_unit_alone_routes_the_fix():
    issues = [issue(6, labels=["crew:changes-requested", "crew:design"], owns=["d/"])]
    result = make_plan(snap(issues, [pr(10, 6, ["crew:changes-requested"])]))
    assert [(a.kind, a.role) for a in result.actions] == [("fix", "designer")]


def test_followup_on_design_decision_pr_goes_to_the_designer():
    issues = [issue(5, labels=["crew:owner-accept", "crew:design"], owns=["a/"])]
    prs = [pr(9, 5, ["crew:owner-accept", "crew:owner-decision"], comments=[owner_comment()])]
    (action,) = make_plan(snap(issues, prs)).actions
    assert (action.kind, action.number, action.role) == ("followup", 9, "designer")
    assert action.prompt == (
        "The owner answered on #9 (https://github.com/example/app/pull/9). Continue from their "
        "answer: if they chose an alternative, record the chosen design per your brief; "
        "otherwise revise the alternatives."
    )


def bet(number=27, pitch="0001"):
    from crew.bets import Bet

    return Bet(
        number, pitch, f"Pitch {pitch}: Core loop", f"https://github.com/example/app/pull/{number}"
    )


def test_unsplit_bet_starts_the_architect_after_implement_before_refine():
    snapshot = snap([issue(1, labels=["crew:ready"]), issue(2, labels=["crew:rough"])])
    snapshot.unsplit = {27: bet(), 30: bet(30, "0002")}
    result = make_plan(snapshot, free_slots=4)
    assert kinds(result) == [("implement", 1), ("split", 27), ("refine", 2)]
    split = result.actions[1]
    assert (split.role, split.model, split.branch, split.issue) == ("architect", None, None, None)
    assert "pitch 0001" in split.prompt and "https://github.com/example/app/pull/27" in split.prompt


def test_one_split_at_a_time():
    snapshot = snap([])
    snapshot.unsplit = {27: bet(), 30: bet(30, "0002")}
    result = make_plan(snapshot, live=[Live("split", 27, None)])
    assert kinds(result) == []


def test_idle_reason_names_the_stall():
    issues = [
        issue(140, labels=["crew:idea"], owns=["a/"]),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132, 77], labels=["crew:ready"], owns=["c/"]),
        issue(77, owns=["d/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["e/"]),
        issue(5, deps=[4], labels=["crew:rough"], owns=["f/"]),
    ]
    assert idle_reason(snap(issues)) == (
        "nothing can start: #4 is in a dependency cycle; "
        "#48 depends on open #132, #77 (not a crew unit); "
        "#132 depends on open #140 (parked idea)"
    )


def test_idle_reason_blames_owner_only_with_inbox():
    waiting = [
        issue(5, labels=["crew:rough", "crew:owner-decision"], owns=["a/"]),
        issue(6, deps=[5], labels=["crew:ready"], owns=["b/"]),
    ]
    assert idle_reason(snap(waiting)) == OWNER_IDLE
    assert idle_reason(snap([])) == "nothing to do"


def test_idle_reason_names_units_stuck_without_open_dependencies():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:in-progress"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["b/x/"]),
        issue(4, labels=["crew:rough"], owns=["c/"]),
    ]
    problems = [
        LabelProblem(1, "has more than one priority label: crew:must, crew:later", ()),
        LabelProblem(4, "has more than one state label: x, y", ()),
    ]
    assert idle_reason(snap(issues, problems=problems)) == (
        "nothing can start: "
        "#1 has a label problem: has more than one priority label: crew:must, crew:later; "
        "#3 owns overlap with #2; "
        "#4 has a label problem: has more than one state label: x, y"
    )
