"""Mark a run's own worktree as trusted in Claude Code's config.

Claude Code asks "trust this folder?" once per git root, and every worktree is its own git
root. A run creates its worktrees inside a project the owner already works in, so before an
agent starts there, the run sets the same flag the dialog's "Yes" sets, for that path only.
"""

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

TRUST_FLAG = "hasTrustDialogAccepted"


class TrustError(Exception):
    """Claude Code's config can't be read or written."""


def claude_config_file(env: Mapping[str, str]) -> Path:
    """``$CLAUDE_CONFIG_DIR/.claude.json``, or ``~/.claude.json`` when it is unset."""
    if env.get("CLAUDE_CONFIG_DIR"):
        return Path(env["CLAUDE_CONFIG_DIR"]).expanduser() / ".claude.json"
    home = Path(env["HOME"]) if env.get("HOME") else Path.home()
    return home / ".claude.json"


def trust_folder(path: Path, env: Mapping[str, str]) -> None:
    """Set the trust flag for ``path`` in Claude Code's config, keeping everything else.

    The file is replaced atomically with its mode kept.

    Raises:
        TrustError: the config is missing, isn't a JSON object, or can't be written.
    """
    config = claude_config_file(env)
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        mode = config.stat().st_mode & 0o777
    except (OSError, ValueError) as exc:
        raise TrustError(f"cannot read Claude Code's config {config}: {exc}") from None
    if not isinstance(data, dict):
        raise TrustError(f"Claude Code's config {config} is not a JSON object")
    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise TrustError(f"Claude Code's config {config} has no projects mapping")
    key = str(path)
    entry = projects.get(key) if isinstance(projects.get(key), dict) else {}
    if entry.get(TRUST_FLAG) is True:
        return
    projects[key] = {**entry, TRUST_FLAG: True}
    try:
        fd, tmp = tempfile.mkstemp(dir=config.parent, prefix=f".{config.name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2)
        os.chmod(tmp, mode)
        os.replace(tmp, config)
    except OSError as exc:
        Path(tmp).unlink(missing_ok=True)
        raise TrustError(f"cannot write Claude Code's config {config}: {exc}") from None
