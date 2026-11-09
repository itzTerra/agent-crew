from pathlib import Path

from crew.docs.pitches import parse_pitch

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "pitches" / "0001-shopping-list.md"


def variant(tmp_path: Path, old: str, new: str, name: str = "0001-shopping-list.md") -> Path:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / name
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def codes(findings):
    return [(f.code, f.line) for f in findings]


def test_pitch_valid():
    assert parse_pitch(EXAMPLE) == []


def test_pitch_missing_no_gos(tmp_path):
    path = variant(tmp_path, "## No-gos", "## Out of scope")
    findings = parse_pitch(path)
    assert codes(findings) == [("PITCH-SECTION", 1)]
    assert "No-gos" in findings[0].message


def test_pitch_appetite_without_percent(tmp_path):
    path = variant(tmp_path, "10 % of the weekly limit.", "About two evenings.")
    assert codes(parse_pitch(path)) == [("PITCH-APPETITE", 7)]


def test_pitch_bad_name_and_title(tmp_path):
    path = variant(tmp_path, "# Pitch 0001:", "# Remember:", name="shopping.md")
    assert codes(parse_pitch(path)) == [("PITCH-NAME", 1), ("PITCH-TITLE", 1)]


def test_pitch_missing_priority_is_a_warning(tmp_path):
    path = variant(tmp_path, "## Priority\n\nMust\n\n", "")
    findings = parse_pitch(path)
    assert [(f.code, f.severity) for f in findings] == [("PITCH-PRIORITY", "warning")]


def test_pitch_bad_priority(tmp_path):
    path = variant(tmp_path, "\nMust\n", "\nUrgent\n")
    findings = parse_pitch(path)
    assert [(f.code, f.severity) for f in findings] == [("PITCH-PRIORITY", "error")]


def test_pitch_priority_tolerates_emphasis(tmp_path):
    assert parse_pitch(variant(tmp_path, "\nMust\n", "\n**Should.**\n")) == []
