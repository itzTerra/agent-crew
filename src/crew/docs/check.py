"""``crew check-docs``: every document check plus cross-references between documents."""

from pathlib import Path

from crew.config import Config
from crew.docs.adrs import Adr, parse_adr
from crew.docs.pitches import parse_pitch
from crew.docs.requirements import Requirement, parse_requirements
from crew.docs.specs import Spec, parse_spec
from crew.findings import Finding

SKIPPED_NAMES = {"template.md", "readme.md"}


def check_docs(root: Path, config: Config, strict: bool = False) -> list[Finding]:
    """Check all requirements, living specs, ADRs and pitches under ``root``.

    With ``strict``, a requirement no spec cites is an error instead of a warning.
    Missing directories are fine: a new project may have none yet.
    """
    paths = config.paths
    findings: list[Finding] = []

    requirements: list[Requirement] = []
    for path in _files(root / paths.requirements, "*.md"):
        reqs, found = parse_requirements(path)
        requirements.extend(reqs)
        findings.extend(found)

    specs: list[Spec] = []
    for path in _files(root / paths.specs, "**/spec.md"):
        spec, found = parse_spec(path)
        specs.append(spec)
        findings.extend(found)

    adrs: list[Adr] = []
    for path in _files(root / paths.adr, "*.md"):
        adr, found = parse_adr(path)
        if adr is not None:
            adrs.append(adr)
        findings.extend(found)

    for path in _files(root / paths.pitches, "*.md"):
        findings.extend(parse_pitch(path))

    findings.extend(_cross_references(requirements, specs, adrs, strict))
    return findings


def _files(directory: Path, pattern: str) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.glob(pattern) if p.is_file() and p.name.lower() not in SKIPPED_NAMES
    )


def _cross_references(
    requirements: list[Requirement], specs: list[Spec], adrs: list[Adr], strict: bool
) -> list[Finding]:
    findings: list[Finding] = []

    defined: dict[str, Requirement] = {}
    for req in requirements:
        first = defined.setdefault(req.id, req)
        if first is not req:
            findings.append(
                Finding(
                    req.path,
                    req.line,
                    "REQ-DUP",
                    f"{req.id} is already defined at {first.path.name}:{first.line}",
                )
            )

    cited: set[str] = set()
    for spec in specs:
        for spec_req in spec.requirements:
            for req_id in spec_req.satisfies:
                cited.add(req_id)
                if req_id not in defined:
                    findings.append(
                        Finding(
                            spec.path,
                            spec_req.line,
                            "XREF-REQ",
                            f"`{spec_req.name}` satisfies {req_id}, which no requirements file "
                            "defines",
                        )
                    )

    numbers = {adr.number for adr in adrs}
    for adr in adrs:
        if adr.superseded_by is not None and adr.superseded_by not in numbers:
            findings.append(
                Finding(
                    adr.path,
                    1,
                    "ADR-REF",
                    f"superseded by ADR-{adr.superseded_by:04d}, which does not exist",
                )
            )

    severity = "error" if strict else "warning"
    for req in defined.values():
        if req.id not in cited and not req.covered_elsewhere:
            findings.append(
                Finding(
                    req.path,
                    req.line,
                    "XREF-UNCITED",
                    f"{req.id} is cited by no living spec; cite it in a `Satisfies:` line or mark "
                    "it `[covered: <how>]`",
                    severity=severity,
                )
            )
    return findings
