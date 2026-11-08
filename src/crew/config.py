"""Per-project settings, read from ``.crew/config.yaml``."""

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

CONFIG_PATH = Path(".crew") / "config.yaml"
REQUIRED_KEYS = ("repo", "owner_login", "agent_login")
BUDGET_MIN, BUDGET_MAX = 1, 100


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
    )


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
