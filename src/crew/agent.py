"""``crew agent``: start a crew agent session under the agents' own GitHub identity.

The agents' token reaches the session only through ``GH_TOKEN``; git gets the agents' name,
noreply email and gh's credential helper through ``GIT_CONFIG_*`` variables, so nothing the
agent does can come from the owner's account.
"""

import json
import os
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from crew.usage import USAGE_FILE_ENV, usage_path

ROLES = ("lead", "architect", "designer", "implementer", "reviewer")
TOKEN_FILE_ENV = "CREW_AGENT_TOKEN_FILE"
DEFAULT_TOKEN_FILE = "~/.config/crew/agent-token"
GITHUB_HTTPS = "https://github.com"
CHECK_PUSH_LINE = "push: https via gh (ssh rewritten)"
# Inherited variables that would make gh or other tools act for another account or host.
CLEARED_VARS = ("GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_HOST")
# Every ssh transport refuses, so no URL form, alias or pushInsteadOf can reach the owner's key.
SSH_REFUSED = "sh -c 'echo \"crew: ssh disabled for agent sessions; push over https\" >&2; exit 1'"

PLUGIN_INSTALL = (
    "claude plugin marketplace add https://github.com/itzTerra/agent-crew"
    " && claude plugin install crew@agent-crew"
)
PLUGIN_PREFIX = "crew@"
STATUS_LINE = {"type": "command", "command": "crew usage record"}
STATUS_LINE_SETTINGS = json.dumps({"statusLine": STATUS_LINE})
# Roles that merge PRs (crew:merge). Auto mode's classifier refuses `gh pr merge` as a merge
# without review, but for these roles the review gate is the crew's own, so it is allowed.
MERGING_ROLES = frozenset({"implementer", "reviewer"})
MERGE_ALLOW = ["Bash(gh pr merge:*)"]


def session_settings(role: str) -> str:
    """The ``--settings`` JSON for a ``role`` session: the status line, and merging for
    the roles that merge."""
    settings: dict = {"statusLine": STATUS_LINE}
    if role in MERGING_ROLES:
        settings["permissions"] = {"allow": MERGE_ALLOW}
    return json.dumps(settings)


# Seams for tests: how ``gh`` is run and how the session replaces this process.
RUN = subprocess.run
EXEC = os.execvpe


class AgentError(Exception):
    """The agent session can't start safely; reported by ``main()`` as ``crew: error:``."""


def token_path(env: Mapping[str, str]) -> Path:
    """The token file: ``$CREW_AGENT_TOKEN_FILE`` if set, else the default location.

    Args:
        env: the environment to read the override from.

    Returns:
        The token file's path, with ``~`` expanded.
    """
    return Path(env.get(TOKEN_FILE_ENV) or DEFAULT_TOKEN_FILE).expanduser()


def read_token(path: Path) -> str:
    """Read the agents' token from ``path``.

    Args:
        path: the token file.

    Returns:
        The token, stripped of surrounding whitespace.

    Raises:
        AgentError: the file is missing, unreadable, empty, or readable by group or others.
    """
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        raise AgentError(
            f"no agents' token at {path}; store it there (mode 600) or set {TOKEN_FILE_ENV}"
        ) from None
    except OSError as exc:
        raise AgentError(f"cannot read the agents' token at {path}: {exc.strerror}") from None
    if stat.S_IMODE(mode) & 0o077:
        raise AgentError(
            f"the agents' token at {path} is readable by others; run `chmod 600 {path}`"
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        reason = getattr(exc, "strerror", None) or "not UTF-8 text"
        raise AgentError(f"cannot read the agents' token at {path}: {reason}") from None
    if not token:
        raise AgentError(f"the agents' token file {path} is empty")
    return token


def plugin_installed(env: Mapping[str, str], root: Path | None = None) -> bool | None:
    """Whether Claude Code's plugin registry has the crew plugin for sessions in ``root``.

    A user-scope install counts anywhere; a project or local install counts when its
    project is ``root`` or a folder above it (a run's worktrees sit inside the project), or
    when ``.claude/settings.json`` there enables the plugin.

    Args:
        env: the environment to read ``CLAUDE_CONFIG_DIR`` from (default ``~/.claude``).
        root: where the session will run; None counts every install.

    Returns:
        True or False from ``plugins/installed_plugins.json``; None when that file is
        missing or has another shape, so the check can be skipped.
    """
    config_dir = Path(env.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()
    try:
        data = json.loads((config_dir / "plugins" / "installed_plugins.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return None
    keys = [str(key) for key in plugins if str(key).startswith(PLUGIN_PREFIX)]
    for key in keys:
        installs = plugins[key]
        if not isinstance(installs, list):
            return True  # an older registry shape without scopes
        if any(_install_covers(install, root) for install in installs):
            return True
    # Installed for another project, but enabled in this one's own settings.
    return bool(keys) and root is not None and _enabled_in_settings(root, set(keys))


def _enabled_in_settings(root: Path, keys: set[str]) -> bool:
    """Whether ``root`` or a folder above it enables one of ``keys`` in .claude/settings*."""
    target = root.expanduser().resolve()
    for folder in (target, *target.parents):
        for name in ("settings.local.json", "settings.json"):
            try:
                data = json.loads((folder / ".claude" / name).read_text("utf-8"))
            except (OSError, ValueError):
                continue
            enabled = data.get("enabledPlugins") if isinstance(data, dict) else None
            if isinstance(enabled, dict):
                values = [enabled[key] for key in keys if key in enabled]
                if values:
                    return values[0] is True
    return False


def _install_covers(install: object, root: Path | None) -> bool:
    if not isinstance(install, dict):
        return False
    scope = install.get("scope", "user")
    if scope == "user" or root is None:
        return True
    project = install.get("projectPath")
    if not project:
        return False
    project_path = Path(str(project)).expanduser().resolve()
    target = root.expanduser().resolve()
    return target == project_path or project_path in target.parents


def noreply_email(login: str, user_id: int) -> str:
    """The GitHub noreply address that attributes commits to ``login``.

    Args:
        login: the GitHub login.
        user_id: that account's numeric id.

    Returns:
        ``"<id>+<login>@users.noreply.github.com"``.
    """
    return f"{user_id}+{login}@users.noreply.github.com"


def new_gh_config_dir(env: Mapping[str, str]) -> Path:
    """A fresh, empty, owner-only gh config directory for one agent session.

    The session's gh then never reads the owner's gh config or stored accounts.

    Args:
        env: the environment to read ``XDG_RUNTIME_DIR`` from.

    Returns:
        A new mode-700 directory under ``$XDG_RUNTIME_DIR``, or the temp dir when unset.
    """
    parent = env.get("XDG_RUNTIME_DIR") or None
    return Path(tempfile.mkdtemp(prefix="crew-gh-", dir=parent))


def agent_env(
    base: Mapping[str, str], token: str, login: str, user_id: int, gh_config_dir: Path
) -> dict[str, str]:
    """The environment for an agent session: the token and the agents' git identity.

    Git settings are appended after any ``GIT_CONFIG_COUNT`` entries already in ``base``.

    Args:
        base: the environment to start from; it is not modified.
        token: the agents' GitHub token.
        login: the agents' GitHub login.
        user_id: the agents' numeric GitHub id.
        gh_config_dir: the session's own gh config directory.

    Returns:
        A new environment mapping.

    Raises:
        AgentError: ``GIT_CONFIG_COUNT`` in ``base`` is not a whole number of at least 0.
    """
    env = _without_cleared(base)
    env["GH_TOKEN"] = token
    env["GH_CONFIG_DIR"] = str(gh_config_dir)
    # Pinned here, so the status line writes where crew run reads, whatever the session's
    # launcher does to CLAUDE_CONFIG_DIR.
    env[USAGE_FILE_ENV] = str(usage_path(base))
    env["GIT_SSH_COMMAND"] = SSH_REFUSED
    settings = [
        ("user.name", login),
        ("user.email", noreply_email(login, user_id)),
        (f"url.{GITHUB_HTTPS}/.insteadOf", "git@github.com:"),
        (f"url.{GITHUB_HTTPS}/.insteadOf", "ssh://git@github.com/"),
        # The empty value resets the helper list, so the owner's stored credentials
        # (e.g. a global credential.helper=store) never answer an agent's push.
        (f"credential.{GITHUB_HTTPS}.helper", ""),
        (f"credential.{GITHUB_HTTPS}.helper", "!gh auth git-credential"),
    ]
    start = _git_config_count(env.get("GIT_CONFIG_COUNT"))
    for offset, (key, value) in enumerate(settings):
        env[f"GIT_CONFIG_KEY_{start + offset}"] = key
        env[f"GIT_CONFIG_VALUE_{start + offset}"] = value
    env["GIT_CONFIG_COUNT"] = str(start + len(settings))
    return env


def _git_config_count(value: str | None) -> int:
    if not value:
        return 0
    if not value.strip().isdigit():
        raise AgentError(f"GIT_CONFIG_COUNT is '{value}', not a whole number ≥ 0; unset or fix it")
    return int(value)


def _without_cleared(base: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in base.items() if key not in CLEARED_VARS}


def agent_argv(role: str, prompt: str | None, model: str | None, auto: bool = False) -> list[str]:
    """The ``claude`` command line for ``role``.

    The session's status line is always ``crew usage record``, which stores the usage
    reading for ``crew budget`` and ``crew run``.

    Args:
        role: one of ``ROLES``.
        prompt: the first message, or None to start without one.
        model: a model override, or None for the agent definition's model.
        auto: run in Claude Code's auto permission mode.

    Returns:
        The argv, starting with ``claude``.

    Raises:
        AgentError: ``role`` is not one of ``ROLES``.
    """
    if role not in ROLES:
        raise AgentError(f"unknown role {role!r}; choose one of {', '.join(ROLES)}")
    argv = ["claude", "--agent", f"crew:{role}"]
    if model:
        argv += ["--model", model]
    if auto:
        argv += ["--permission-mode", "auto"]
    argv += ["--settings", session_settings(role)]
    if prompt:
        argv.append(prompt)
    return argv


def whoami(token: str, run=subprocess.run) -> tuple[str, int]:
    """Ask GitHub which account ``token`` belongs to, via ``gh api user``.

    Args:
        token: the token to check; passed only through ``GH_TOKEN``.
        run: a ``subprocess.run`` stand-in.

    Returns:
        ``(login, id)`` of the token's account.

    Raises:
        AgentError: gh is missing, the call fails, or the answer isn't a user.
    """
    try:
        result = run(
            ["gh", "api", "user"],
            env={**_without_cleared(os.environ), "GH_TOKEN": token},
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise AgentError("gh is not installed; install the GitHub CLI") from None
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit {result.returncode}"
        raise AgentError(f"cannot check the agents' token with `gh api user`: {reason}")
    try:
        data = json.loads(result.stdout)
        return str(data["login"]), int(data["id"])
    except (ValueError, KeyError, TypeError):
        raise AgentError("`gh api user` did not return a user") from None


def agent_token(agent_login: str, owner_login: str) -> tuple[str, str, int]:
    """Read the agents' token and check that it belongs to ``agent_login``.

    Args:
        agent_login: the login the project's config expects.
        owner_login: the owner's login; a token of this account is always refused.

    Returns:
        ``(token, login, id)`` of the agents' account.

    Raises:
        AgentError: no or unreadable token, or a token of the owner or of another account.
    """
    token = read_token(token_path(os.environ))
    login, user_id = whoami(token, run=RUN)
    if login.casefold() == owner_login.casefold():
        raise AgentError(
            f"the agents' token belongs to the owner ({login}); "
            "agents need their own account, set as agent_login"
        )
    if login.casefold() != agent_login.casefold():
        raise AgentError(
            f"the agents' token belongs to {login}, but agent_login is {agent_login}; "
            "refusing to act under another account"
        )
    return token, login, user_id


def run_agent(
    role: str,
    prompt: str | None,
    model: str | None,
    agent_login: str,
    owner_login: str,
    check: bool,
    root: Path,
    auto: bool = False,
) -> None:
    """Verify the agents' identity, then print it (``check``) or replace this process.

    Args:
        role: the agent role to start.
        prompt: the first message, or None.
        model: a model override, or None.
        agent_login: the login the project's config expects.
        owner_login: the owner's login; a token of this account is always refused.
        check: print the identity and launch nothing.
        root: the session's working directory.
        auto: run in Claude Code's auto permission mode.

    Raises:
        AgentError: bad role, bad token, a token of another account, or no ``claude``.
    """
    argv = agent_argv(role, prompt, model, auto)
    plugin = plugin_installed(os.environ, root)
    if plugin is False:
        raise AgentError(f"the crew plugin is not installed; install it with: {PLUGIN_INSTALL}")
    token, login, user_id = agent_token(agent_login, owner_login)
    gh_config_dir = new_gh_config_dir(os.environ)
    try:
        env = agent_env(os.environ, token, login, user_id, gh_config_dir)
    except AgentError:
        gh_config_dir.rmdir()
        raise
    if check:
        gh_config_dir.rmdir()
        print(f"gh: {login}")
        print("gh config: isolated")
        print(f"git: {login} {noreply_email(login, user_id)}")
        print(CHECK_PUSH_LINE)
        print("plugin: crew installed" if plugin else "plugin: unknown (registry not found)")
        return
    os.chdir(root)
    try:
        EXEC(argv[0], argv, env)
    except FileNotFoundError:
        raise AgentError("claude is not installed or not on PATH") from None
