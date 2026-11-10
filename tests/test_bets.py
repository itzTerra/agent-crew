from crew.bets import Bet, unsplit_bets
from tests.test_graph import issue


def pitch_pr(number, pitch="0003", title=None, branch=None):
    return {
        "number": number,
        "title": title or f"Pitch {pitch}: Something",
        "labels": [{"name": "crew:owner-accept"}],
        "headRefName": branch or f"pitch/{pitch}",
        "closingIssuesReferences": [],
        "mergedAt": "2026-11-09T10:00:00Z",
        "url": f"https://github.com/example/app/pull/{number}",
    }


def unit(number, bet, state="OPEN"):
    item = issue(number, body=f"## Goal\n\nUnit {number}.\n\n## Bet\n\n{bet}\n")
    item["state"] = state
    return item


def test_merged_pitch_without_units_is_unsplit():
    assert unsplit_bets([pitch_pr(12)], []) == [
        Bet(12, "0003", "Pitch 0003: Something", "https://github.com/example/app/pull/12")
    ]


def test_unit_linking_the_pitch_path_splits_it():
    issues = [unit(20, "docs/pitches/0003-shopping-list.md")]
    assert unsplit_bets([pitch_pr(12)], issues) == []


def test_unit_linking_the_pitch_pr_splits_it():
    assert unsplit_bets([pitch_pr(12)], [unit(20, "#12")]) == []
    assert unsplit_bets([pitch_pr(12)], [unit(20, "https://github.com/example/app/pull/12")]) == []


def test_closed_units_count():
    issues = [unit(20, "docs/pitches/0003-shopping-list.md", state="CLOSED")]
    assert unsplit_bets([pitch_pr(12)], issues) == []


def test_other_pitches_and_numbers_do_not_count():
    issues = [
        unit(20, "docs/pitches/0004-other.md"),
        unit(21, "#123"),
        unit(22, "docs/pitches/10003-x.md"),
    ]
    assert [bet.number for bet in unsplit_bets([pitch_pr(12)], issues)] == [12]


def test_pitch_mentioned_outside_the_bet_section_does_not_count():
    body = "## Goal\n\nFollow up on docs/pitches/0003-shopping-list.md and #12.\n\n## Bet\n\n#5\n"
    assert [bet.number for bet in unsplit_bets([pitch_pr(12)], [issue(20, body=body)])] == [12]


def test_only_pitch_branches_are_bets():
    prs = [pitch_pr(12, branch="unit/12-x"), pitch_pr(13, pitch="0005"), pitch_pr(11, pitch="0002")]
    assert [bet.number for bet in unsplit_bets(prs, [])] == [11, 13]
