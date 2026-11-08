"""Requirements tables: rows whose first cell is a ``REQ-<AREA>-<n>`` ID."""

import re
from dataclasses import dataclass
from pathlib import Path

from crew.docs.markdown import read_lines
from crew.findings import Finding

REQ_ID = re.compile(r"^REQ-[A-Z][A-Z0-9]*-\d+$")
PRIORITIES = ("Must", "Should", "Later")
PRIORITY_COLUMNS = ("pri", "priority")
WHY_COLUMN = "why"
_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_COVERED = re.compile(r"\[covered:\s*[^\]]+\]", re.IGNORECASE)


@dataclass
class Requirement:
    """One requirement row."""

    id: str
    priority: str | None
    path: Path
    line: int
    covered_elsewhere: bool


def parse_requirements(path: Path) -> tuple[list[Requirement], list[Finding]]:
    """Find every requirement row in a Markdown file and check its ID and priority."""
    lines = read_lines(path)
    requirements: list[Requirement] = []
    findings: list[Finding] = []
    pri_column: int | None = None
    # The current table's header line, while its missing Why column is still unreported.
    no_why_header: int | None = None

    for index, line in enumerate(lines):
        number = index + 1
        if not line.lstrip().startswith("|"):
            pri_column = None
            no_why_header = None
            continue
        if _SEPARATOR.match(line.strip()):
            continue
        cells = split_row(line)
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _SEPARATOR.match(following):
            headers = [c.lower() for c in cells]
            pri_column = next((i for i, h in enumerate(headers) if h in PRIORITY_COLUMNS), None)
            no_why_header = None if WHY_COLUMN in headers else number
            continue
        first = cells[0].strip("`*_ ") if cells else ""
        if not first.upper().startswith("REQ-"):
            continue
        if not REQ_ID.match(first):
            findings.append(Finding(path, number, "REQ-ID", f"malformed requirement ID `{first}`"))
            continue
        if no_why_header is not None:
            findings.append(
                Finding(path, no_why_header, "REQ-WHY", "requirements table has no Why column")
            )
            no_why_header = None
        priority = None
        if pri_column is not None:
            priority = cells[pri_column].strip("`*_ ") if pri_column < len(cells) else ""
            if priority not in PRIORITIES:
                findings.append(
                    Finding(
                        path,
                        number,
                        "REQ-PRI",
                        f"{first}: priority `{priority}` is not one of {', '.join(PRIORITIES)}",
                    )
                )
        requirements.append(
            Requirement(
                id=first,
                priority=priority,
                path=path,
                line=number,
                covered_elsewhere=bool(_COVERED.search(line)),
            )
        )
    return requirements, findings


def split_row(line: str) -> list[str]:
    """Split a Markdown table row into trimmed cells, honouring ``\\|`` escapes."""
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", row)]
