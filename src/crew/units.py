"""Units (GitHub issues) and the Definition of Ready check.

A unit body has the ``## `` sections Goal, Bet, Spec delta, Owns, Depends on and Kind.
The Spec delta section may hold its own ``## ADDED Requirements`` (and similar)
headings; only the six unit section names start a new section.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from crew.config import Config
from crew.docs.markdown import headings, normalize, split_lines
from crew.docs.specs import Spec, parse_delta, parse_spec
from crew.findings import Finding

ISSUE = Path("<issue>")
SECTIONS = ("Goal", "Bet", "Spec delta", "Owns", "Depends on", "Kind")
KINDS = ("owner-facing", "internal")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DELTA_NONE = re.compile(r"^none\s*[—–-]+\s*\S", re.IGNORECASE)
_BULLET = re.compile(r"^[-*]\s+(.*\S)\s*$")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_DEP = re.compile(r"^[-*]\s+#(\d+)\s*$")
_ISSUE_REF = re.compile(r"#\d+\b")
_TARGET = re.compile(r"^\s*(?:\*\*)?Target:(?:\*\*)?\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class UnitBody:
    """The parsed sections of a unit's issue body. Missing sections give empty values."""

    goal: str = ""
    bet: str = ""
    delta_text: str | None = None  # None when the section says "none — <reason>" or is absent
    owns: list[str] = field(default_factory=list)
    depends_on: list[int] = field(default_factory=list)
    kind: Literal["owner-facing", "internal"] | None = None


@dataclass
class _Section:
    line: int  # heading line
    body: list[tuple[int, str]]

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.body).strip()

    @property
    def content(self) -> list[tuple[int, str]]:
        return [(n, t.strip()) for n, t in self.body if t.strip()]


def parse_unit_body(body: str) -> UnitBody:
    """Parse a unit body. Never raises: malformed parts give empty values."""
    sections = _sections(body)
    unit = UnitBody()
    if "goal" in sections:
        unit.goal = sections["goal"].text
    if "bet" in sections:
        unit.bet = sections["bet"].text
    if "spec delta" in sections:
        text = sections["spec delta"].text
        unit.delta_text = None if (not text or _DELTA_NONE.match(text)) else text
    if "owns" in sections:
        unit.owns = [
            path
            for _, t in sections["owns"].content
            if (m := _BULLET.match(t))
            for path in _owned_paths(m.group(1))
        ]
    if "depends on" in sections:
        unit.depends_on = [
            int(m.group(1)) for _, t in sections["depends on"].content if (m := _DEP.match(t))
        ]
    if "kind" in sections:
        content = sections["kind"].content
        value = content[0][1].lower() if content else ""
        if value in KINDS:
            unit.kind = value  # type: ignore[assignment]
    return unit


def delta_target(delta_text: str | None) -> str | None:
    """The ``Target:`` spec file named in a spec delta, or None."""
    match = _TARGET.search(delta_text or "")
    return match.group(1).strip("`").strip() if match else None


def _owned_paths(text: str) -> list[str]:
    """The paths of one Owns bullet: each backticked path, or the whole bullet without any."""
    quoted = _CODE_SPAN.findall(text)
    if quoted:
        return [_clean_path(q) for q in quoted if q.strip()]
    return [_clean_path(text)]


def _clean_path(text: str) -> str:
    """Strip code backticks and a leading ``./`` from an owned path."""
    path = text.strip().strip("`").strip()
    while path.startswith("./"):
        path = path[2:]
    return path


def check_unit(body: str, root: Path, config: Config) -> list[Finding]:
    """Check a unit body against the Definition of Ready.

    Findings use the path ``<issue>`` and line numbers within the body.
    """
    sections = _sections(body)
    findings: list[Finding] = []
    for name in SECTIONS:
        if normalize(name) not in sections:
            findings.append(Finding(ISSUE, 1, "DOR-SECTION", f"missing `## {name}` section"))

    if bet := sections.get("bet"):
        pitches = config.paths.pitches.rstrip("/") + "/"
        if pitches not in bet.text and not _ISSUE_REF.search(bet.text):
            findings.append(
                Finding(ISSUE, bet.line, "DOR-BET", f"Bet must link a `{pitches}` path or an #N")
            )

    if delta := sections.get("spec delta"):
        findings.extend(_check_delta(delta, root))

    if owns := sections.get("owns"):
        if not any(_BULLET.match(t) for _, t in owns.content):
            findings.append(
                Finding(ISSUE, owns.line, "DOR-OWNS", "Owns needs at least one path bullet")
            )

    if deps := sections.get("depends on"):
        content = deps.content
        is_none = len(content) == 1 and content[0][1].lower() == "none"
        if not is_none:
            bad = [(n, t) for n, t in content if not _DEP.match(t)]
            if not content or bad:
                at = bad[0][0] if bad else deps.line
                findings.append(
                    Finding(
                        ISSUE,
                        at,
                        "DOR-DEPS",
                        "Depends on must be bullet items `- #N`, or exactly `none`",
                    )
                )

    if kind := sections.get("kind"):
        content = kind.content
        value = content[0][1] if content else ""
        if value.lower() not in KINDS or len(content) > 1:
            at = content[0][0] if content else kind.line
            findings.append(
                Finding(ISSUE, at, "DOR-KIND", f"Kind must be one of {', '.join(KINDS)}")
            )

    findings.sort(key=lambda f: f.line)
    return findings


def _check_delta(section: _Section, root: Path) -> list[Finding]:
    text = section.text
    if not text:
        return [
            Finding(ISSUE, section.line, "DOR-DELTA", "Spec delta is empty; use `none — <reason>`")
        ]
    if _DELTA_NONE.match(text):
        return []
    first_line = next(n for n, t in section.body if t.strip())
    offset = first_line - 1
    target_match = _TARGET.search(text)
    target: Spec | None = None
    if target_match:
        target_path = root / target_match.group(1).strip("`").strip()
        if target_path.is_file():
            target, _ = parse_spec(target_path)
    _, delta_findings = parse_delta(text, ISSUE, target)
    return [
        Finding(ISSUE, f.line + offset, "DOR-DELTA", f"{f.code} {f.message}")
        for f in delta_findings
    ]


def _sections(body: str) -> dict[str, _Section]:
    """Split at the unit's own ``## `` headings; comments are blanked, keeping line numbers."""
    text = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), body)
    names = {normalize(n) for n in SECTIONS}
    sections: dict[str, _Section] = {}
    current: _Section | None = None
    numbered = list(enumerate(split_lines(text), start=1))
    for number, line, parsed in headings(numbered):
        if parsed and parsed[0] == 2 and normalize(parsed[1]) in names:
            current = _Section(number, [])
            sections.setdefault(normalize(parsed[1]), current)
        elif current is not None:
            current.body.append((number, line))
    return sections
