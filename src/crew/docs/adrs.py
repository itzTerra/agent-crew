"""Architecture decision records in MADR 4.0 structure, bullet-style metadata."""

import re
from dataclasses import dataclass
from pathlib import Path

from crew.docs.markdown import headings, normalize, read_lines
from crew.findings import Finding

SKIPPED = {"template.md", "readme.md"}
REQUIRED_SECTIONS = ("Context and problem statement", "Considered options", "Decision outcome")
STATUSES = ("Proposed", "Accepted", "Rejected", "Deprecated")
_NAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
_TITLE = re.compile(r"^ADR[\s-]*(\d{4})\s*:\s*\S", re.IGNORECASE)
_STATUS = re.compile(r"^[-*]\s+\*\*Status:\*\*\s*(.*?)\s*$", re.IGNORECASE)
_SUPERSEDED = re.compile(r"^Superseded by \[?ADR[\s-]*(\d{4})\b", re.IGNORECASE)


@dataclass
class Adr:
    """One parsed ADR."""

    number: int
    path: Path
    status: str
    superseded_by: int | None


def parse_adr(path: Path) -> tuple[Adr | None, list[Finding]]:
    """Parse and check one ADR file. ``TEMPLATE.md`` and ``README.md`` give ``(None, [])``."""
    if path.name.lower() in SKIPPED:
        return None, []
    findings: list[Finding] = []
    lines = list(enumerate(read_lines(path), start=1))
    marked = headings(lines)

    name_match = _NAME.match(path.name)
    number = int(name_match.group(1)) if name_match else 0
    if not name_match:
        findings.append(Finding(path, 1, "ADR-NAME", "file name must be `NNNN-slug.md`"))

    first = next(((n, h) for n, _, h in marked if h), (1, None))
    title_match = _TITLE.match(first[1][1]) if first[1] and first[1][0] == 1 else None
    if not title_match:
        findings.append(
            Finding(path, first[0], "ADR-TITLE", "first heading must be `# ADR NNNN: <title>`")
        )
    elif name_match and int(title_match.group(1)) != number:
        findings.append(
            Finding(
                path,
                first[0],
                "ADR-TITLE",
                f"title number {title_match.group(1)} doesn't match the file name",
            )
        )
    if not name_match and title_match:
        number = int(title_match.group(1))

    status, superseded_by = "", None
    status_line = next(((n, m) for n, t in lines if (m := _STATUS.match(t.strip()))), None)
    if status_line is None:
        findings.append(Finding(path, 1, "ADR-STATUS", "missing `- **Status:** <value>` line"))
    else:
        number_, match = status_line
        value = match.group(1)
        superseded = _SUPERSEDED.match(value)
        known = {s.lower(): s for s in STATUSES}
        if superseded:
            status, superseded_by = "Superseded", int(superseded.group(1))
        elif value.lower() in known:
            status = known[value.lower()]
        else:
            findings.append(
                Finding(
                    path,
                    number_,
                    "ADR-STATUS",
                    f"status `{value}` is not one of {', '.join(STATUSES)}, Superseded by ADR-NNNN",
                )
            )

    present = {normalize(h[1]) for _, _, h in marked if h and h[0] == 2}
    for section in REQUIRED_SECTIONS:
        if normalize(section) not in present:
            findings.append(Finding(path, 1, "ADR-SECTION", f"missing `## {section}` section"))

    adr = Adr(number=number, path=path, status=status, superseded_by=superseded_by)
    return adr, findings
