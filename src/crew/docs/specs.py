"""Living specs (OpenSpec structure, EARS statements) and spec deltas.

A living spec::

    # <Area name>
    ## Purpose
    ## Requirements
    ### Requirement: <name>
    <one EARS statement containing "shall">
    Satisfies: REQ-…, REQ-…        (optional)
    #### Scenario: <name>
    - GIVEN / WHEN / THEN / AND lines

A delta has a ``Target: <path>`` line and any of the sections ADDED, MODIFIED, REMOVED
(``### Requirement:`` blocks) and RENAMED (``- FROM: <old> TO: <new>`` lines).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from crew.docs.markdown import heading, headings, normalize, prefixed, read_lines, split_lines
from crew.findings import Finding

DELTA_SECTIONS = {
    "added requirements": "added",
    "modified requirements": "modified",
    "removed requirements": "removed",
    "renamed requirements": "renamed",
}
_SHALL = re.compile(r"\bshall\b", re.IGNORECASE)
_SCENARIO_STEP = re.compile(r"^[-*]\s+(?:\*\*)?(GIVEN|WHEN|THEN|AND)\b", re.IGNORECASE)
_RENAME = re.compile(r"^[-*]\s+FROM:\s*(.+?)\s+TO:\s*(.+?)$", re.IGNORECASE)
_SATISFIES = re.compile(r"^\**Satisfies:\**\s*(.*)$", re.IGNORECASE)
_TARGET = re.compile(r"^\s*(?:\*\*)?Target:(?:\*\*)?\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class SpecRequirement:
    """One ``### Requirement:`` block."""

    name: str
    line: int
    statement: str
    satisfies: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)


@dataclass
class Spec:
    """A parsed living spec."""

    path: Path
    title: str
    requirements: list[SpecRequirement]


@dataclass
class Delta:
    """A parsed spec delta."""

    target: str | None
    added: list[SpecRequirement] = field(default_factory=list)
    modified: list[SpecRequirement] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)


Numbered = list[tuple[int, str]]  # (1-based line number, line text)


def parse_spec(path: Path) -> tuple[Spec, list[Finding]]:
    """Parse a living spec file and check its structure."""
    lines = list(enumerate(read_lines(path), start=1))
    findings: list[Finding] = []

    title = ""
    first = next(((n, text) for n, text in lines if text.strip()), (1, ""))
    parsed = heading(first[1])
    if parsed and parsed[0] == 1:
        title = parsed[1]
    else:
        findings.append(Finding(path, first[0], "SPEC-TITLE", "first line must be a `# ` title"))

    sections = _level2_sections(lines)
    names = [normalize(name) for _, name, _ in sections]
    if "purpose" not in names:
        findings.append(Finding(path, 1, "SPEC-PURPOSE", "missing `## Purpose` section"))
    if "requirements" not in names:
        findings.append(Finding(path, 1, "SPEC-REQS", "missing `## Requirements` section"))

    requirements: list[SpecRequirement] = []
    for line, name, body in sections:
        key = normalize(name)
        if key in DELTA_SECTIONS:
            findings.append(
                Finding(path, line, "SPEC-DELTA", f"delta heading `## {name}` in a living spec")
            )
        elif key == "requirements":
            reqs, req_findings = _parse_requirements(body, path)
            requirements.extend(reqs)
            findings.extend(req_findings)

    seen: set[str] = set()
    for req in requirements:
        key = normalize(req.name)
        if key in seen:
            findings.append(
                Finding(path, req.line, "SPEC-DUP", f"requirement `{req.name}` is repeated")
            )
        seen.add(key)

    findings.sort(key=lambda f: f.line)
    return Spec(path=path, title=title, requirements=requirements), findings


def parse_delta(text: str, source: Path, target: Spec | None) -> tuple[Delta, list[Finding]]:
    """Parse a delta and check it against its target spec.

    ``target`` is the parsed spec the ``Target:`` line names, or None when that file
    doesn't exist (or the caller couldn't resolve it). Line numbers count from the
    first line of ``text``.
    """
    lines = list(enumerate(split_lines(text), start=1))
    findings: list[Finding] = []
    delta = Delta(target=None)

    target_line = 1
    for number, line, parsed in headings(lines):
        if parsed:
            break
        match = _TARGET.match(line)
        if match:
            delta.target = match.group(1).strip("`").strip()
            target_line = number
            break
    if delta.target is None:
        findings.append(Finding(source, 1, "DELTA-TARGET", "missing `Target: <spec path>` line"))
    elif target is None:
        findings.append(
            Finding(source, target_line, "DELTA-TARGET", f"target `{delta.target}` does not exist")
        )

    sections = [s for s in _level2_sections(lines) if normalize(s[1]) in DELTA_SECTIONS]
    if not sections:
        findings.append(
            Finding(source, 1, "DELTA-EMPTY", "no ADDED/MODIFIED/REMOVED/RENAMED section")
        )

    unknown: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    for _, name, body in sections:
        kind = DELTA_SECTIONS[normalize(name)]
        if kind in ("added", "modified"):
            reqs, req_findings = _parse_requirements(body, source)
            getattr(delta, kind).extend(reqs)
            findings.extend(req_findings)
            if kind == "modified":
                unknown.extend((r.line, r.name) for r in reqs)
            else:
                added.extend((r.line, r.name) for r in reqs)
        elif kind == "removed":
            for number, _, parsed in headings(body):
                name_ = _requirement_name(parsed)
                if name_ is not None:
                    delta.removed.append(name_)
                    unknown.append((number, name_))
        else:
            for number, line in body:
                match = _RENAME.match(line.strip())
                if match:
                    old, new = (part.strip().strip("`") for part in match.groups())
                    delta.renamed.append((old, new))
                    unknown.append((number, old))

    if target is not None:
        known = {normalize(r.name) for r in target.requirements}
        for number, name_ in unknown:
            if normalize(name_) not in known:
                findings.append(
                    Finding(
                        source,
                        number,
                        "DELTA-UNKNOWN",
                        f"requirement `{name_}` is not in `{delta.target}`",
                    )
                )
        for number, name_ in added:
            if normalize(name_) in known:
                findings.append(
                    Finding(
                        source,
                        number,
                        "DELTA-EXISTS",
                        f"added requirement `{name_}` is already in `{delta.target}`; use MODIFIED",
                    )
                )

    findings.sort(key=lambda f: f.line)
    return delta, findings


def _level2_sections(lines: Numbered) -> list[tuple[int, str, Numbered]]:
    """Split at ``#``/``##`` headings: (heading line, heading text, body lines).

    Deeper headings stay in the body of the section that holds them.
    """
    sections: list[tuple[int, str, Numbered]] = []
    for number, line, parsed in headings(lines):
        if parsed and parsed[0] <= 2:
            sections.append((number, parsed[1], []))
        elif sections:
            sections[-1][2].append((number, line))
    return sections


def _requirement_name(parsed: tuple[int, str] | None) -> str | None:
    if parsed and parsed[0] == 3:
        return prefixed(parsed[1], "Requirement:")
    return None


def _parse_requirements(body: Numbered, path: Path) -> tuple[list[SpecRequirement], list[Finding]]:
    """Parse the ``### Requirement:`` blocks of one section and check each."""
    blocks: list[tuple[int, str, Numbered]] = []
    for number, line, parsed in headings(body):
        name = _requirement_name(parsed)
        if name is not None:
            blocks.append((number, name, []))
        elif blocks:
            blocks[-1][2].append((number, line))

    requirements: list[SpecRequirement] = []
    findings: list[Finding] = []
    for line, name, block in blocks:
        req, block_findings = _parse_requirement(line, name, block, path)
        requirements.append(req)
        findings.extend(block_findings)
    return requirements, findings


def _parse_requirement(
    line: int, name: str, block: Numbered, path: Path
) -> tuple[SpecRequirement, list[Finding]]:
    findings: list[Finding] = []
    statement: Numbered = []
    satisfies: list[str] = []
    scenarios: list[tuple[int, str, set[str]]] = []

    for number, text, parsed in headings(block):
        if parsed and parsed[0] == 4:
            scenario = prefixed(parsed[1], "Scenario:")
            if scenario is not None:
                scenarios.append((number, scenario, set()))
            continue
        if scenarios:
            step = _SCENARIO_STEP.match(text.strip())
            if step:
                scenarios[-1][2].add(step.group(1).upper())
            continue
        match = _SATISFIES.match(text.strip())
        if match:
            cleaned = (
                i.strip().strip("`*_").rstrip(".,;").strip("`*_") for i in match.group(1).split(",")
            )
            satisfies.extend(i for i in cleaned if i)
        elif text.strip() and not text.strip().startswith("<!--"):
            statement.append((number, text.strip()))

    statement_text = " ".join(text for _, text in statement)
    if not _SHALL.search(statement_text):
        at = statement[0][0] if statement else line
        findings.append(
            Finding(path, at, "SPEC-SHALL", f'requirement `{name}` has no "shall" statement')
        )
    if not scenarios:
        findings.append(Finding(path, line, "SPEC-NOSCEN", f"requirement `{name}` has no scenario"))
    for number, scenario, steps in scenarios:
        missing = [k for k in ("WHEN", "THEN") if k not in steps]
        if missing:
            findings.append(
                Finding(
                    path,
                    number,
                    "SPEC-SCEN",
                    f"scenario `{scenario}` lacks {' and '.join(missing)}",
                )
            )

    requirement = SpecRequirement(
        name=name,
        line=line,
        statement=statement_text,
        satisfies=satisfies,
        scenarios=[s for _, s, _ in scenarios],
    )
    return requirement, findings
