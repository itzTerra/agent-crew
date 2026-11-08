"""A thin driver for the herdr CLI: workspaces, tabs, commands and agent status."""

import json
import subprocess
from pathlib import Path

GONE = frozenset({"agent_not_found", "pane_not_found"})


class HerdrError(Exception):
    """A herdr call failed; the message is herdr's own error text."""


class _Gone(HerdrError):
    """The pane, or the agent in it, no longer exists."""


class Herdr:
    """herdr calls. ``run`` is injectable for tests."""

    def __init__(self, run=subprocess.run):
        self._run = run

    def create_workspace(self, cwd: Path, label: str) -> str:
        """Create a workspace without focusing it; return its id."""
        data = self._json("workspace", "create", "--cwd", str(cwd), "--label", label, "--no-focus")
        return str(data["result"]["workspace"]["workspace_id"])

    def open_tab(
        self, workspace: str, cwd: Path, label: str, env: dict[str, str] | None = None
    ) -> str:
        """Open a tab in ``workspace`` without focusing it; return its pane id.

        A pane doesn't inherit the caller's environment, only herdr's; ``env`` is set in it.
        """
        env_args = [
            arg for key, value in (env or {}).items() for arg in ("--env", f"{key}={value}")
        ]
        data = self._json(
            "tab", "create", "--workspace", workspace, "--cwd", str(cwd),
            "--label", label, "--no-focus", *env_args,
        )  # fmt: skip
        return str(data["result"]["root_pane"]["pane_id"])

    def run_command(self, pane: str, command: str) -> None:
        """Run a shell command in ``pane``."""
        self._herdr("pane", "run", pane, command)

    def status(self, pane: str) -> str | None:
        """The agent's status in ``pane``; None when no agent is there or the pane is gone."""
        try:
            data = self._json("agent", "get", pane)
        except _Gone:
            return None
        return str(data["result"]["agent"].get("agent_status") or "unknown")

    def prompt(self, pane: str, text: str) -> None:
        """Submit ``text`` to the agent in ``pane`` without waiting for its turn."""
        self._herdr("agent", "prompt", pane, text)

    def read(self, pane: str, lines: int = 40) -> str:
        """The last ``lines`` lines of the pane's output."""
        return self._herdr(
            "pane", "read", pane, "--source", "recent-unwrapped", "--lines", str(lines)
        )

    def close(self, pane: str) -> None:
        """Close ``pane``; a pane that is already gone is fine."""
        try:
            self._herdr("pane", "close", pane)
        except _Gone:
            pass

    def _json(self, *args: str) -> dict:
        out = self._herdr(*args)
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise HerdrError(f"herdr {args[0]} {args[1]} returned invalid JSON") from None

    def _herdr(self, *args: str) -> str:
        try:
            result = self._run(["herdr", *args], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise HerdrError("herdr is not installed or not on PATH") from None
        if result.returncode == 0:
            return result.stdout
        code, message = _error(result.stderr or result.stdout or "")
        if code in GONE:
            raise _Gone(message)
        raise HerdrError(f"herdr {args[0]} {args[1]} failed: {message}")


def _error(text: str) -> tuple[str, str]:
    try:
        error = json.loads(text)["error"]
        return str(error.get("code", "")), str(error.get("message", "")) or "no message"
    except (ValueError, KeyError, TypeError):
        return "", " ".join(text.split()) or "no output"
