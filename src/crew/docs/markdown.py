"""Line-level Markdown helpers shared by the document parsers."""

import re
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


class DocumentReadError(Exception):
    """A document can't be read as UTF-8 text."""


def split_lines(text: str) -> list[str]:
    """Split into lines, accepting CRLF, and strip trailing whitespace from each."""
    return [line.rstrip() for line in text.splitlines()]


def read_lines(path: Path) -> list[str]:
    """Read a UTF-8 file with :func:`split_lines`.

    Raises:
        DocumentReadError: the file can't be read or isn't UTF-8.
    """
    try:
        return split_lines(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise DocumentReadError(f"{path} is not UTF-8 text") from None
    except OSError as exc:
        raise DocumentReadError(f"cannot read {path}: {exc.strerror}") from None


def headings(lines: list[tuple[int, str]]) -> list[tuple[int, str, tuple[int, str] | None]]:
    """Each numbered line with its heading ``(level, text)``, or None.

    Lines inside fenced code blocks (and the fence lines) are never headings.
    """
    result = []
    fence: str | None = None
    for number, line in lines:
        match = _FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)[0] * len(match.group(1))
            result.append((number, line, None))
        elif fence is not None:
            if line.strip().startswith(fence) and not line.strip().strip(fence[0]):
                fence = None
            result.append((number, line, None))
        else:
            result.append((number, line, heading(line)))
    return result


def heading(line: str) -> tuple[int, str] | None:
    """Return ``(level, text)`` for a Markdown ATX heading, or None."""
    match = _HEADING.match(line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def normalize(text: str) -> str:
    """Lower-case and collapse whitespace, for case-insensitive heading matches."""
    return " ".join(text.lower().split())


def prefixed(text: str, prefix: str) -> str | None:
    """If ``text`` starts with ``prefix`` (case-insensitive), return the trimmed rest."""
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip()
    return None
