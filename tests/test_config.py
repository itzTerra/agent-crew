from pathlib import Path

import pytest

from crew.config import Config, ConfigError, Paths, load_config

MINIMAL = "repo: example/app\nowner_login: owner-a\nagent_login: agent-b\n"


def write_config(root: Path, text: str) -> None:
    (root / ".crew").mkdir()
    (root / ".crew" / "config.yaml").write_text(text, encoding="utf-8")


def test_load_defaults(tmp_path):
    write_config(tmp_path, MINIMAL)
    config = load_config(tmp_path)
    assert config == Config(
        repo="example/app",
        owner_login="owner-a",
        agent_login="agent-b",
        paths=Paths(),
        budget_cap_percent=75,
        max_agents=2,
        docker_run="",
        ci_checks=[],
        owner_decisions_extra=[],
        merge_rules="",
    )


def test_paths_override(tmp_path):
    write_config(tmp_path, MINIMAL + "paths:\n  adr: decisions\n")
    assert load_config(tmp_path).paths == Paths(adr="decisions")


def test_missing_required_key_raises(tmp_path):
    write_config(tmp_path, "repo: example/app\nowner_login: owner-a\n")
    with pytest.raises(ConfigError, match="agent_login"):
        load_config(tmp_path)


@pytest.mark.parametrize("value", [0, 101, -5])
def test_budget_out_of_range_raises(tmp_path, value):
    write_config(tmp_path, MINIMAL + f"budget_cap_percent: {value}\n")
    with pytest.raises(ConfigError, match="budget_cap_percent"):
        load_config(tmp_path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="crew init"):
        load_config(tmp_path)


def test_invalid_yaml_raises(tmp_path):
    write_config(tmp_path, "repo: [unclosed\n")
    with pytest.raises(ConfigError, match="config.yaml"):
        load_config(tmp_path)
