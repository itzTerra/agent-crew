"""``crew agent``: start a crew agent session under the agents' own GitHub identity.

The agents' token reaches the session only through ``GH_TOKEN``; git gets the agents' name,
noreply email and gh's credential helper through ``GIT_CONFIG_*`` variables, so nothing the
agent does can come from the owner's account.
"""

import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

ROLES = ("lead", "architect", "designer", "implementer", "reviewer")
TOKEN_FILE_ENV = "CREW_AGENT_TOKEN_FILE"
DEFAULT_TOKEN_FILE = "~/.config/crew/agent-token"
GITHUB_HTTPS = "https://github.com"
CHECK_PUSH_LINE = "push: https via gh (ssh rewritten)"

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


def noreply_email(login: str, user_id: int) -> str:
    """The GitHub noreply address that attributes commits to ``login``.

    Args:
        login: the GitHub login.
        user_id: that account's numeric id.

    Returns:
        ``"<id>+<login>@users.noreply.github.com"``.
    """
    return f"{user_id}+{login}@users.noreply.github.com"


def agent_env(base: Mapping[str, str], token: str, login: str, user_id: int) -> dict[str, str]:
    """The environment for an agent session: the token and the agents' git identity.

    Git settings are appended after any ``GIT_CONFIG_COUNT`` entries already in ``base``.

    Args:
        base: the environment to start from; it is not modified.
        token: the agents' GitHub token.
        login: the agents' GitHub login.
        user_id: the agents' numeric GitHub id.

    Returns:
        A new environment mapping.
    """
    env = dict(base)
    env["GH_TOKEN"] = token
    settings = [
        ("user.name", login),
        ("user.email", noreply_email(login, user_id)),
        (f"url.{GITHUB_HTTPS}/.insteadOf", "git@github.com:"),
        # The empty value resets the helper list, so the owner's stored credentials
        # (e.g. a global credential.helper=store) never answer an agent's push.
        (f"credential.{GITHUB_HTTPS}.helper", ""),
        (f"credential.{GITHUB_HTTPS}.helper", "!gh auth git-credential"),
    ]
    start = int(env.get("GIT_CONFIG_COUNT") or 0)
    for offset, (key, value) in enumerate(settings):
        env[f"GIT_CONFIG_KEY_{start + offset}"] = key
        env[f"GIT_CONFIG_VALUE_{start + offset}"] = value
    env["GIT_CONFIG_COUNT"] = str(start + len(settings))
    return env


def agent_argv(role: str, prompt: str | None, model: str | None) -> list[str]:
    """The ``claude`` command line for ``role``.

    Args:
        role: one of ``ROLES``.
        prompt: the first message, or None to start without one.
        model: a model override, or None for the agent definition's model.

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
            env={**os.environ, "GH_TOKEN": token},
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


def run_agent(
    role: str, prompt: str | None, model: str | None, agent_login: str, check: bool
) -> None:
    """Verify the agents' identity, then print it (``check``) or replace this process.

    Args:
        role: the agent role to start.
        prompt: the first message, or None.
        model: a model override, or None.
        agent_login: the login the project's config expects.
        check: print the identity and launch nothing.

    Raises:
        AgentError: bad role, bad token, a token of another account, or no ``claude``.
    """
    argv = agent_argv(role, prompt, model)
    token = read_token(token_path(os.environ))
    login, user_id = whoami(token, run=RUN)
    if login != agent_login:
        raise AgentError(
            f"the agents' token belongs to {login}, but agent_login is {agent_login}; "
            "refusing to start an agent under another account"
        )
    env = agent_env(os.environ, token, login, user_id)
    if check:
        print(f"gh: {login}")
        print(f"git: {login} {noreply_email(login, user_id)}")
        print(CHECK_PUSH_LINE)
        return
    try:
        EXEC(argv[0], argv, env)
    except FileNotFoundError:
        raise AgentError("claude is not installed or not on PATH") from None
