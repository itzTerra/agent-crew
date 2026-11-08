from pathlib import Path

import pytest

from crew.config import DEFAULT_ESTIMATES, Config, ConfigError, Paths, load_config

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
        poll_seconds=120,
        refine_ahead=2,
        stop_grace_minutes=15,
        estimates=dict(DEFAULT_ESTIMATES),
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


def test_config_run_keys_defaults_and_validation(tmp_path):
    assert DEFAULT_ESTIMATES == {
        "merge": 15, "fix": 30, "review": 20, "followup": 30,
        "resume": 60, "implement": 90, "refine": 20,
    }  # fmt: skip
    write_config(
        tmp_path,
        MINIMAL + "poll_seconds: 60\nrefine_ahead: 0\nstop_grace_minutes: 5\n"
        "estimates:\n  implement: 120\n",
    )
    config = load_config(tmp_path)
    assert (config.poll_seconds, config.refine_ahead, config.stop_grace_minutes) == (60, 0, 5)
    assert config.estimates == {**DEFAULT_ESTIMATES, "implement": 120}
    for bad, key in (
        ("poll_seconds: 29\n", "poll_seconds"),
        ("refine_ahead: -1\n", "refine_ahead"),
        ("stop_grace_minutes: 0\n", "stop_grace_minutes"),
        ("estimates:\n  deploy: 5\n", "deploy"),
        ("estimates:\n  merge: -5\n", "merge"),
        ("estimates: 5\n", "estimates"),
    ):
        (tmp_path / ".crew" / "config.yaml").write_text(MINIMAL + bad, encoding="utf-8")
        with pytest.raises(ConfigError, match=key):
            load_config(tmp_path)
