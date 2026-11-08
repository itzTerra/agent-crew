"""Structure checks for the plugin's agents and skills."""

from pathlib import Path

import pytest
import yaml

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
    ):
        assert phrase in text, f"{name}.md lacks {phrase!r}"
