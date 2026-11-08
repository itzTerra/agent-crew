from pathlib import Path

from crew.docs.requirements import parse_requirements

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_mixed_requirements_parse():
    reqs, findings = parse_requirements(FIXTURES / "requirements-mixed.md")
    assert findings == []
    assert len(reqs) == 12
    by_id = {r.id: r for r in reqs}
    assert by_id["REQ-LATER-1"].priority is None
    assert by_id["REQ-ARCH-3"].priority == "Should"
    assert by_id["REQ-DOC-1"].priority == "Must"
    assert by_id["REQ-ARCH-1"].line == 9


def test_bad_priority(tmp_path):
    path = tmp_path / "reqs.md"
    path.write_text(
        "| ID | Pri | Requirement |\n|---|---|---|\n"
        "| REQ-A-1 | Must | Fine. |\n| REQ-A-2 | Maybe | Not a priority. |\n",
        encoding="utf-8",
    )
    reqs, findings = parse_requirements(path)
    assert [(f.code, f.line) for f in findings] == [("REQ-PRI", 4)]
    assert len(reqs) == 2


def test_malformed_id(tmp_path):
    path = tmp_path / "reqs.md"
    path.write_text(
        "| ID | Pri | Requirement |\n|---|---|---|\n| REQ-a-x | Must | Bad id. |\n",
        encoding="utf-8",
    )
    reqs, findings = parse_requirements(path)
    assert [(f.code, f.line) for f in findings] == [("REQ-ID", 3)]
    assert reqs == []


def test_covered_marker():
    reqs, _ = parse_requirements(FIXTURES / "requirements-mixed.md")
    covered = [r.id for r in reqs if r.covered_elsewhere]
    assert covered == ["REQ-SRC-3"]
