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
    ):
        assert phrase in text, f"{name}.md lacks {phrase!r}"


SKILLS = ["inbox", "kickoff", "pitch", "refine", "relay", "implement", "review", "merge"]
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
