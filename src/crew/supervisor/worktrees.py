"""Worktrees for the run's agents, under ``<root>/.crew/worktrees/``.

Inside the project, so Claude Code's trust in the project folder covers them; the folder
holds a ``.gitignore`` of ``*`` so the main checkout never sees them.
"""

import re
import subprocess
from pathlib import Path

WORKTREES = Path(".crew") / "worktrees"
_UNIT = re.compile(r"^unit/(\d+)-")


class WorktreeError(Exception):
    """A git command for a worktree failed."""


def worktree_path(root: Path, branch: str, detach: bool = False) -> Path:
    """``unit-<n>`` for unit branches, ``review-<branch>`` when detached, else ``<branch>``."""
    flat = branch.replace("/", "-")
    if detach:
        name = f"review-{flat}"
    elif match := _UNIT.match(branch):
        name = f"unit-{match.group(1)}"
    else:
        name = flat
    return root / WORKTREES / name


def worktree_for(
    root: Path,
    branch: str,
    detach: bool = False,
    run=subprocess.run,
    ignore_dir: bool = True,
) -> Path:
    """A worktree for ``branch`` (or, detached, at ``origin/<branch>``), made or reused.

    Fetches first. An existing worktree for the branch is reused; a reused detached one is
    moved to the branch's current remote commit.

    Raises:
        WorktreeError: a git command failed.
    """

    def git(*args: str, at: Path = root, check: bool = True) -> subprocess.CompletedProcess:
        argv = ["git", "-C", str(at), *args]
        try:
            result = run(argv, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise WorktreeError("git is not installed or not on PATH") from None
        if check and result.returncode != 0:
            detail = " ".join((result.stderr or "").split()) or f"exit {result.returncode}"
            raise WorktreeError(f"git {' '.join(args[:2])} failed: {detail}")
        return result

    def exists(ref: str) -> bool:
        return git("rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0

    git("fetch", "origin")
    path = worktree_path(root, branch, detach)
    if ignore_dir:
        _ignore_worktrees(root)
    listed = _list_worktrees(git("worktree", "list", "--porcelain").stdout)
    if detach:
        if path in listed:
            git("checkout", "--detach", f"origin/{branch}", at=path)
            return path
        git("worktree", "add", "--detach", str(path), f"origin/{branch}")
        return path
    remote = f"refs/remotes/origin/{branch}"
    for existing, checked_out in listed.items():
        if checked_out == branch:
            if exists(remote):
                _fast_forward(git, existing, branch)
            return existing
    if exists(f"refs/heads/{branch}"):
        git("worktree", "add", str(path), branch)
        if exists(remote):
            _fast_forward(git, path, branch)
    elif exists(remote):
        git("worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}")
    else:
        git("worktree", "add", "-b", branch, str(path), "origin/main")
    return path


def _fast_forward(git, path: Path, branch: str) -> None:
    """Bring a reused local branch up to its remote, so a later --force-with-lease push
    can't overwrite commits pushed by someone else. A branch that can't fast-forward is left
    for the agent."""
    git("merge", "--ff-only", f"origin/{branch}", at=path, check=False)


def _list_worktrees(porcelain: str) -> dict[Path, str | None]:
    """Worktree path -> checked-out branch (None when detached)."""
    found: dict[Path, str | None] = {}
    current: Path | None = None
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            current = Path(line.removeprefix("worktree "))
            found[current] = None
        elif line.startswith("branch refs/heads/") and current is not None:
            found[current] = line.removeprefix("branch refs/heads/")
    return found


def _ignore_worktrees(root: Path) -> None:
    folder = root / WORKTREES
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
