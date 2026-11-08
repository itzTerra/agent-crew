from pathlib import Path

from crew.docs.specs import parse_delta, parse_spec
from crew.findings import Finding

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "specs"


def codes(findings: list[Finding]) -> list[tuple[str, int]]:
    return [(f.code, f.line) for f in findings]


def spec(name: str):
    return parse_spec(FIXTURES / name)


def delta(name: str, target_name: str | None = "valid.md"):
    target = spec(target_name)[0] if target_name else None
    path = FIXTURES / name
    return parse_delta(path.read_text(encoding="utf-8"), path, target)


def test_valid_spec_has_no_findings():
    parsed, findings = spec("valid.md")
    assert findings == []
    assert parsed.title == "Imports"
    assert [r.name for r in parsed.requirements] == ["Accept plain text", "Reject locked files"]
    assert parsed.requirements[0].line == 9
    assert parsed.requirements[0].scenarios == ["Import a small file"]
    assert "shall import it as a recipe" in parsed.requirements[0].statement


def test_missing_purpose():
    assert codes(spec("missing-purpose.md")[1]) == [("SPEC-PURPOSE", 1)]


def test_statement_without_shall():
    assert codes(spec("no-shall.md")[1]) == [("SPEC-SHALL", 11)]


def test_duplicate_requirement_name():
    assert codes(spec("duplicate.md")[1]) == [("SPEC-DUP", 18)]


def test_requirement_without_scenario():
    assert codes(spec("no-scenario.md")[1]) == [("SPEC-NOSCEN", 9)]


def test_scenario_without_then():
    findings = spec("no-then.md")[1]
    assert codes(findings) == [("SPEC-SCEN", 13)]
    assert "THEN" in findings[0].message


def test_delta_heading_in_living_spec():
    assert codes(spec("delta-in-spec.md")[1]) == [("SPEC-DELTA", 18)]


def test_spec_tolerates_crlf_and_case(tmp_path):
    text = (FIXTURES / "valid.md").read_text(encoding="utf-8")
    text = text.replace("## Purpose", "##  PURPOSE ")
    text = text.replace("### Requirement:", "### requirement:")
    text = text.replace("- **WHEN**", "- **when**").replace("\n", "  \r\n")
    path = tmp_path / "spec.md"
    path.write_bytes(text.encode("utf-8"))
    parsed, findings = parse_spec(path)
    assert findings == []
    assert [r.name for r in parsed.requirements] == ["Accept plain text", "Reject locked files"]


def test_satisfies_parsed():
    parsed, _ = spec("valid.md")
    assert parsed.requirements[0].satisfies == ["REQ-ARCH-1", "REQ-SRC-2"]
    assert parsed.requirements[1].satisfies == []


def test_delta_valid_against_target():
    parsed, findings = delta("delta-valid.md")
    assert findings == []
    assert parsed.target == "docs/specs/imports/spec.md"
    assert [r.name for r in parsed.added] == ["Accept PDF"]
    assert parsed.added[0].satisfies == ["REQ-ARCH-1"]
    assert [r.name for r in parsed.modified] == ["Reject locked files"]
    assert parsed.removed == ["Accept plain text"]
    assert parsed.renamed == [("Reject locked files", "Refuse locked files")]


def test_delta_modifies_unknown_requirement():
    findings = delta("delta-unknown.md")[1]
    assert codes(findings) == [("DELTA-UNKNOWN", 5), ("DELTA-UNKNOWN", 16), ("DELTA-UNKNOWN", 20)]


def test_delta_without_target():
    assert codes(delta("delta-no-target.md", target_name=None)[1]) == [("DELTA-TARGET", 1)]


def test_delta_target_missing_file():
    findings = delta("delta-valid.md", target_name=None)[1]
    assert codes(findings) == [("DELTA-TARGET", 1)]
    assert "docs/specs/imports/spec.md" in findings[0].message


def test_delta_without_sections():
    text = "Target: docs/specs/imports/spec.md\n"
    findings = parse_delta(text, FIXTURES / "x.md", spec("valid.md")[0])[1]
    assert codes(findings) == [("DELTA-EMPTY", 1)]


def test_delta_added_requirement_is_checked():
    text = (FIXTURES / "delta-no-target.md").read_text(encoding="utf-8")
    text = text.replace("- THEN the cookbook lists one recipe\n", "")
    text = "Target: docs/specs/imports/spec.md\n" + text
    findings = parse_delta(text, FIXTURES / "x.md", spec("valid.md")[0])[1]
    assert codes(findings) == [("SPEC-SCEN", 8)]


def test_finding_format(tmp_path):
    finding = Finding(tmp_path / "docs" / "a.md", 3, "SPEC-SHALL", "no shall")
    assert finding.format(tmp_path) == "docs/a.md:3: SPEC-SHALL no shall"
    warning = Finding(Path("<issue>"), 2, "XREF-UNCITED", "uncited", severity="warning")
    assert warning.format(tmp_path) == "<issue>:2: warning: XREF-UNCITED uncited"
