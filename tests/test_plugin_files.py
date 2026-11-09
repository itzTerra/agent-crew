"""Structure checks for the plugin's agents and skills."""

import argparse
import re
from pathlib import Path

import pytest
import yaml

from crew.cli import build_parser

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "crew"
AGENTS = ["lead", "architect", "designer", "implementer", "reviewer"]
OPUS = {"lead", "architect", "reviewer"}
MAX_AGENT_BODY_LINES = 150


def split_frontmatter(path: Path) -> tuple[dict, list[str]]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no frontmatter"
    _, front, body = text.split("---\n", 2)
    return yaml.safe_load(front), body.strip().splitlines()


def test_expected_agents_present():
    assert sorted(p.stem for p in (PLUGIN / "agents").glob("*.md")) == sorted(AGENTS)


@pytest.mark.parametrize("name", AGENTS)
def test_agent_frontmatter(name):
    meta, body = split_frontmatter(PLUGIN / "agents" / f"{name}.md")
    assert meta["name"] == name
    assert isinstance(meta.get("description"), str) and meta["description"].strip()
    assert meta["model"] in {"opus", "sonnet"}
    assert meta["model"] == ("opus" if name in OPUS else "sonnet")
    assert len(body) <= MAX_AGENT_BODY_LINES


@pytest.mark.parametrize("name", AGENTS)
def test_agent_brief_covers_shared_rules(name):
    _, body = split_frontmatter(PLUGIN / "agents" / f"{name}.md")
    text = "\n".join(body)
    for phrase in (
        ".crew/config.yaml",
        "owner_login",
        "crew:owner-decision",
        "crew:rough",
        "crew:owner-proposal",
        "docs/superpowers/",
        "owner_decisions_extra",
        "force-push",
        "agent_login",
        "--peek",
        "full URL",
        "crew:idea",
    ):
        assert phrase in text, f"{name}.md lacks {phrase!r}"


@pytest.mark.parametrize("name", AGENTS)
def test_discovered_work_parks_ideas(name):
    text = (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")
    rule = text[text.index("**Discovered work:**") :].split("\n- ")[0]
    for phrase in (
        "crew:rough",
        "crew:owner-proposal",
        "crew:idea",
        "agreed behavior",
        "current bet",
    ):
        assert phrase in rule, f"{name}.md discovered-work rule lacks {phrase!r}"


SKILLS = [
    "inbox", "kickoff", "pitch", "ideas", "refine", "relay", "implement", "review", "merge", "run",
    "budget",
]  # fmt: skip
MAX_SKILL_BODY_LINES = 120
CLI_MENTION = re.compile(r"(?:^|`|\$ )crew ([a-z][a-z-]*)", re.MULTILINE)


def registered_commands() -> set[str]:
    parser = build_parser()
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return set(actions[0].choices)


def test_expected_skills_present():
    assert sorted(p.name for p in (PLUGIN / "skills").iterdir()) == sorted(SKILLS)


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter(name):
    path = PLUGIN / "skills" / name / "SKILL.md"
    assert path.is_file()
    meta, body = split_frontmatter(path)
    assert meta["name"] == name
    assert isinstance(meta.get("description"), str) and meta["description"].strip()
    assert len(body) <= MAX_SKILL_BODY_LINES


def test_skills_reference_existing_cli_commands():
    commands = registered_commands()
    assert {"init", "check-docs", "check-issue", "labels", "inbox", "next"} <= commands
    mentioned = {}
    for path in (PLUGIN / "skills").glob("*/SKILL.md"):
        for match in CLI_MENTION.finditer(path.read_text(encoding="utf-8")):
            mentioned.setdefault(match.group(1), path.parent.name)
    assert mentioned, "skills mention no crew commands"
    unknown = {cmd: skill for cmd, skill in mentioned.items() if cmd not in commands}
    assert not unknown, f"skills mention unregistered commands: {unknown}"


def skill_text(name):
    return (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_merge_rebases_before_squashing():
    text = skill_text("merge")
    assert text.index("git rebase origin/main") < text.lower().index("squash")
    assert "crew check-owns P --range origin/main...HEAD" in text
    assert "<merge-sha>^..<merge-sha>" in text


@pytest.mark.parametrize("name", ["merge", "review", "implement", "refine"])
def test_label_changes_use_set_state(name):
    text = skill_text(name)
    assert "--add-label" not in text and "--remove-label" not in text
    assert "crew labels set-state" in text


def test_implement_squashes_and_flags_size():
    text = skill_text("implement")
    assert "--force-with-lease" in text and "25" in text and "10" in text


def test_refine_one_unit_only():
    assert "only that unit" in skill_text("refine")


def test_lead_and_kickoff_propose_one_requirements_file():
    lead = (PLUGIN / "agents" / "lead.md").read_text(encoding="utf-8")
    assert "propose merging" in lead and "propose merging" in skill_text("kickoff")


def test_lead_and_architect_read_stated_reason():
    for name in ("lead", "architect"):
        assert "reason it prints" in (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")


def test_run_skill_needs_owner_go_ahead():
    text = skill_text("run")
    assert "--dry-run" in text and "go-ahead" in text


def test_implement_reuses_run_worktree():
    assert "a run made it" in skill_text("implement")


def test_lead_points_to_run_skills():
    lead = (PLUGIN / "agents" / "lead.md").read_text(encoding="utf-8")
    assert "## Runs" in lead and "crew:run" in lead and "crew:budget" in lead


def test_merge_runs_gh_pr_merge_on_its_own():
    # crew agent allows `gh pr merge` by prefix; a chained `cd … && gh pr merge` isn't allowed.
    text = skill_text("merge")
    assert "a command of its own" in text and "--delete-branch" not in text
    assert "git push origin --delete" in text


def test_ideas_skill_files_and_promotes():
    text = skill_text("ideas")
    for phrase in ("crew:idea", "gh issue list", "full URL", "crew:pitch", "quoted"):
        assert phrase in text


def test_promoted_idea_is_not_closed_by_the_pitch_pr():
    for text in (skill_text("pitch"), skill_text("ideas")):
        assert "From idea #N" in text
    assert "Closes #N" not in skill_text("pitch")


def test_feedback_for_later_becomes_an_idea():
    for text in (skill_text("implement"), skill_text("relay")):
        assert "crew:idea" in text


def test_kickoff_parks_mvp_epics_and_inbox_mentions_ideas():
    assert "crew:idea" in skill_text("kickoff")
    assert "Parked ideas" in skill_text("inbox")
    lead = (PLUGIN / "agents" / "lead.md").read_text(encoding="utf-8")
    assert "crew:ideas" in lead


PRIORITY_RULE_PHRASES = ("crew:must", "crew:should", "crew:later", "the issue you are working on")


@pytest.mark.parametrize("name", AGENTS)
def test_agent_brief_sets_priority(name):
    text = (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")
    rule = text[text.index("**Priority:**") :].split("\n- ")[0]
    for phrase in PRIORITY_RULE_PHRASES:
        assert phrase in rule, f"{name}.md priority rule lacks {phrase!r}"


def test_no_do_first_left():
    for path in [*PLUGIN.rglob("*.md"), PLUGIN.parent.parent / "docs" / "workflow.md"]:
        assert "do-first" not in path.read_text(encoding="utf-8"), path


@pytest.mark.parametrize("name", ["kickoff", "ideas", "pitch", "relay", "implement", "inbox"])
def test_filing_skills_name_a_priority(name):
    assert "crew:must" in skill_text(name) or "crew:later" in skill_text(name)
