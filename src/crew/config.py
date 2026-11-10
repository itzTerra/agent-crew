"""Per-project settings, read from ``.crew/config.yaml``."""

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

CONFIG_PATH = Path(".crew") / "config.yaml"
REQUIRED_KEYS = ("repo", "owner_login", "agent_login")
BUDGET_MIN, BUDGET_MAX = 1, 100
# Minutes each kind of supervisor action is expected to take; a run doesn't start an action
# it can't plausibly finish before its end time.
DEFAULT_ESTIMATES = {
    "merge": 15,
    "fix": 30,
    "review": 20,
    "followup": 30,
    "resume": 60,
    "implement": 90,
    "refine": 20,
    "split": 30,
}


class ConfigError(Exception):
    """The project's config is missing or invalid."""


@dataclass(frozen=True)
class Paths:
    """Where the project keeps each kind of document, relative to the repo root."""

    requirements: str = "docs/requirements"
    specs: str = "docs/specs"
    adr: str = "docs/adr"
    pitches: str = "docs/pitches"
    practices: str = "CLAUDE.md"


@dataclass(frozen=True)
class Config:
    """The project's crew settings."""

    repo: str
    owner_login: str
    agent_login: str
    paths: Paths = field(default_factory=Paths)
    budget_cap_percent: int = 75
    max_agents: int = 2
    docker_run: str = ""
    ci_checks: list[str] = field(default_factory=list)
    owner_decisions_extra: list[str] = field(default_factory=list)
    merge_rules: str = ""
    poll_seconds: int = 120
    refine_ahead: int = 2
    stop_grace_minutes: int = 15
    estimates: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_ESTIMATES))


def load_config(root: Path) -> Config:
    """Read and validate ``root/.crew/config.yaml``.

    Raises:
        ConfigError: the file is missing, isn't valid YAML, or has missing or invalid keys.
    """
    path = root / CONFIG_PATH
    if not path.is_file():
        raise ConfigError(f"no {CONFIG_PATH} in {root}; run `crew init` first")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{CONFIG_PATH} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{CONFIG_PATH} must be a mapping of keys to values")

    missing = [key for key in REQUIRED_KEYS if not data.get(key)]
    if missing:
        raise ConfigError(f"{CONFIG_PATH} is missing required key(s): {', '.join(missing)}")

    paths_data = data.get("paths") or {}
    if not isinstance(paths_data, dict):
        raise ConfigError(f"{CONFIG_PATH}: paths must be a mapping of document kind to directory")
    path_names = {f.name for f in fields(Paths)}
    unknown = set(paths_data) - path_names
    if unknown:
        raise ConfigError(f"{CONFIG_PATH}: unknown paths key(s): {', '.join(sorted(unknown))}")
    paths = Paths(**{key: str(value) for key, value in paths_data.items()})

    budget = _int(data, "budget_cap_percent", 75)
    if not BUDGET_MIN <= budget <= BUDGET_MAX:
        raise ConfigError(
            f"{CONFIG_PATH}: budget_cap_percent must be {BUDGET_MIN}–{BUDGET_MAX}, got {budget}"
        )
    max_agents = _int(data, "max_agents", 2)
    if max_agents < 1:
        raise ConfigError(f"{CONFIG_PATH}: max_agents must be at least 1, got {max_agents}")

    poll_seconds = _int_at_least(data, "poll_seconds", 120, 30)
    refine_ahead = _int_at_least(data, "refine_ahead", 2, 0)
    stop_grace_minutes = _int_at_least(data, "stop_grace_minutes", 15, 1)
    estimates = _estimates(data)

    return Config(
        repo=str(data["repo"]),
        owner_login=str(data["owner_login"]),
        agent_login=str(data["agent_login"]),
        paths=paths,
        budget_cap_percent=budget,
        max_agents=max_agents,
        docker_run=str(data.get("docker_run") or ""),
        ci_checks=_str_list(data, "ci_checks"),
        owner_decisions_extra=_str_list(data, "owner_decisions_extra"),
        merge_rules=str(data.get("merge_rules") or ""),
        poll_seconds=poll_seconds,
        refine_ahead=refine_ahead,
        stop_grace_minutes=stop_grace_minutes,
        estimates=estimates,
    )


def _int_at_least(data: dict, key: str, default: int, minimum: int) -> int:
    value = _int(data, key, default)
    if value < minimum:
        raise ConfigError(f"{CONFIG_PATH}: {key} must be at least {minimum}, got {value}")
    return value


def _estimates(data: dict) -> dict[str, int]:
    given = data.get("estimates") or {}
    if not isinstance(given, dict):
        raise ConfigError(f"{CONFIG_PATH}: estimates must be a mapping of action kind to minutes")
    unknown = set(given) - set(DEFAULT_ESTIMATES)
    if unknown:
        raise ConfigError(
            f"{CONFIG_PATH}: unknown estimates key(s): {', '.join(sorted(map(str, unknown)))}; "
            f"use {', '.join(DEFAULT_ESTIMATES)}"
        )
    estimates = dict(DEFAULT_ESTIMATES)
    for key in given:
        estimates[key] = _int_at_least(given, key, DEFAULT_ESTIMATES[key], 0)
    return estimates


def _int(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{CONFIG_PATH}: {key} must be a whole number, got {value!r}")
    return value


def _str_list(data: dict, key: str) -> list[str]:
    value = data.get(key) or []
    if not isinstance(value, list):
        raise ConfigError(f"{CONFIG_PATH}: {key} must be a list")
    return [str(item) for item in value]
