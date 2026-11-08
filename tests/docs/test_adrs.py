from pathlib import Path

from crew.docs.adrs import parse_adr

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "adr" / "0001-example-decision.md"


def variant(tmp_path: Path, name: str, old: str, new: str) -> Path:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / name
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def codes(findings):
    return [(f.code, f.line) for f in findings]


def test_bullet_style_adr_passes():
    adr, findings = parse_adr(EXAMPLE)
    assert findings == []
    assert (adr.number, adr.status, adr.superseded_by) == (1, "Accepted", None)


def test_adr_missing_decision_outcome(tmp_path):
    path = variant(tmp_path, "0001-x.md", "## Decision outcome", "## What we chose")
    assert codes(parse_adr(path)[1]) == [("ADR-SECTION", 1)]


def test_adr_number_mismatch(tmp_path):
    path = tmp_path / "0002-x.md"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert codes(parse_adr(path)[1]) == [("ADR-TITLE", 1)]


def test_adr_superseded_parsed(tmp_path):
    path = variant(
        tmp_path, "0001-x.md", "- **Status:** Accepted", "- **Status:** Superseded by ADR-0003"
    )
    adr, findings = parse_adr(path)
    assert findings == []
    assert adr.superseded_by == 3


def test_adr_bad_status(tmp_path):
    path = variant(tmp_path, "0001-x.md", "- **Status:** Accepted", "- **Status:** Maybe")
    assert codes(parse_adr(path)[1]) == [("ADR-STATUS", 3)]


def test_adr_heading_case_insensitive(tmp_path):
    path = variant(tmp_path, "0001-x.md", "## Decision outcome", "## Decision Outcome")
    text = path.read_text(encoding="utf-8")
    text = text.replace("## Considered options", "## CONSIDERED OPTIONS  ")
    text = text.replace("- **Status:** Accepted", "- **status:** accepted").replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    adr, findings = parse_adr(path)
    assert findings == []
    assert adr.status == "Accepted"


def test_adr_bad_filename(tmp_path):
    path = tmp_path / "1-Store.md"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert ("ADR-NAME", 1) in codes(parse_adr(path)[1])


def test_template_and_readme_skipped(tmp_path):
    for name in ("TEMPLATE.md", "README.md"):
        path = tmp_path / name
        path.write_text("anything", encoding="utf-8")
        assert parse_adr(path) == (None, [])
