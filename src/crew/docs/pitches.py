"""Shaped pitches: five fixed sections, an appetite in share of the weekly limit, a priority.

A missing ``## Priority`` section is only a warning, so pitches written before it existed pass.
"""

import re
from pathlib import Path

from crew.docs.markdown import headings, normalize, read_lines
from crew.docs.requirements import PRIORITIES
from crew.findings import Finding

SECTIONS = ("Problem", "Appetite", "Solution", "Rabbit holes", "No-gos")
_NAME = re.compile(r"^\d{4}-[a-z0-9-]+\.md$")
_TITLE = re.compile(r"^Pitch\s+\d{4}\s*:\s*\S", re.IGNORECASE)
_PERCENT = re.compile(r"\d+\s*%")


def parse_pitch(path: Path) -> list[Finding]:
    """Check one pitch file."""
    findings: list[Finding] = []
    lines = list(enumerate(read_lines(path), start=1))
    marked = headings(lines)
    if not _NAME.match(path.name):
        findings.append(Finding(path, 1, "PITCH-NAME", "file name must be `NNNN-slug.md`"))

    first = next(((n, h) for n, _, h in marked if h), (1, None))
    if not (first[1] and first[1][0] == 1 and _TITLE.match(first[1][1])):
        findings.append(
            Finding(path, first[0], "PITCH-TITLE", "title must be `# Pitch NNNN: <title>`")
        )

    sections: dict[str, tuple[int, list[str]]] = {}
    current: list[str] | None = None
    for number, text, parsed in marked:
        if parsed and parsed[0] <= 2:
            current = []
            sections.setdefault(normalize(parsed[1]), (number, current))
        elif current is not None:
            current.append(text)

    for section in SECTIONS:
        if normalize(section) not in sections:
            findings.append(Finding(path, 1, "PITCH-SECTION", f"missing `## {section}` section"))

    appetite = sections.get("appetite")
    if appetite and not _PERCENT.search(" ".join(appetite[1])):
        findings.append(
            Finding(
                path,
                appetite[0],
                "PITCH-APPETITE",
                "appetite must give a share of the weekly limit, for example `20 %`",
            )
        )
    findings.extend(_priority_findings(path, sections.get("priority")))
    return findings


def _priority_findings(path: Path, section: tuple[int, list[str]] | None) -> list[Finding]:
    """A warning when the priority section is missing, an error when its value is unknown."""
    allowed = ", ".join(PRIORITIES)
    if section is None:
        message = f"missing `## Priority` section ({allowed})"
        return [Finding(path, 1, "PITCH-PRIORITY", message, severity="warning")]
    line, body = section
    value = next((text.strip().strip("`*_ .") for text in body if text.strip()), "")
    if value in PRIORITIES:
        return []
    return [Finding(path, line, "PITCH-PRIORITY", f"priority `{value}` is not one of {allowed}")]
