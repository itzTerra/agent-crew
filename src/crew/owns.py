"""``crew check-owns``: a PR changes only the paths its unit owns.

Owned-path globs: ``**`` matches across ``/``; ``*`` and ``?`` stay within one path segment.
A pattern without wildcards matches that exact path and, read as a directory, everything
under it (``docs/`` or ``docs`` matches ``docs/a.md``).
"""

import re
import subprocess
from pathlib import Path

_WILDCARD = re.compile(r"[*?\[]")

# Seam for tests: how ``git diff`` is run.
RUN = subprocess.run


class OwnsError(Exception):
    """``git diff`` failed; reported as ``crew: error:``."""


def _glob_regex(glob: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        elif glob[i] == "[" and (end := glob.find("]", i + 2)) != -1:
            out.append(glob[i : end + 1])
            i = end + 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    if glob.endswith("/"):
        out.append(".*")
    return re.compile("".join(out))


def owns_match(path: str, glob: str) -> bool:
    """Whether the changed ``path`` falls under the owned ``glob`` (rules in the module doc)."""
    if not _WILDCARD.search(glob):
        directory = glob.rstrip("/")
        return path == directory or path.startswith(directory + "/")
    return _glob_regex(glob).fullmatch(path) is not None


def outside_owns(paths: list[str], owns: list[str], allowed: list[str] = ()) -> list[str]:
    """The paths that match none of ``owns`` or ``allowed``, in their given order."""
    globs = [*owns, *allowed]
    return [path for path in paths if not any(owns_match(path, glob) for glob in globs)]


def changed_paths(root: Path, rev_range: str) -> list[str]:
    """Paths ``git diff --name-only <rev_range>`` lists, run in ``root``.

    Raises:
        OwnsError: git is missing or the diff fails.
    """
    try:
        result = RUN(
            ["git", "diff", "--name-only", rev_range],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise OwnsError("git is not installed or not on PATH") from None
    if result.returncode != 0:
        detail = " ".join((result.stderr or "").split()) or f"exit {result.returncode}"
        raise OwnsError(f"git diff {rev_range} failed: {detail}")
    return [line for line in result.stdout.splitlines() if line.strip()]
