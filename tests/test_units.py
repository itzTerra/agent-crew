from pathlib import Path

import pytest

from crew.cli import main
from crew.config import load_config
from crew.init import read_template
from crew.units import check_unit, parse_unit_body

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"

READY = """\
## Goal

Cooks can import PDF files.

## Bet

docs/pitches/0001-shopping-list.md

## Spec delta

Target: docs/specs/imports/spec.md

## ADDED Requirements

### Requirement: Accept PDF

When a cook imports a PDF file, the system shall import its text as a recipe.

Satisfies: REQ-ARCH-1

#### Scenario: Import a PDF

- WHEN the cook imports `soup.pdf`
- THEN the cookbook lists one recipe

## Owns

- src/import/**
- tests/import/

## Depends on

- #12
- #15

## Kind

owner-facing
"""


@pytest.fixture
def config():
    return load_config(PROJECT)


def codes(findings):
    return [(f.code, f.line) for f in findings]


def test_ready_unit_passes(config):
    assert check_unit(READY, PROJECT, config) == []
    unit = parse_unit_body(READY)
    assert unit.goal == "Cooks can import PDF files."
    assert unit.owns == ["src/import/**", "tests/import/"]
    assert unit.kind == "owner-facing"
    assert unit.delta_text.startswith("Target: docs/specs/imports/spec.md")


def test_each_missing_section_reported(config):
    findings = check_unit("Just some text.\n", PROJECT, config)
    assert [f.code for f in findings] == ["DOR-SECTION"] * 6
    for name in ("Goal", "Bet", "Spec delta", "Owns", "Depends on", "Kind"):
        assert any(name in f.message for f in findings)
    assert all(str(f.path) == "<issue>" for f in findings)


def test_delta_none_with_reason_ok(config):
    body = READY.split("## Spec delta")[0] + "## Spec delta\n\nnone — refactor only\n\n## Owns"
    body += READY.split("## Owns")[1]
    assert check_unit(body, PROJECT, config) == []
    assert parse_unit_body(body).delta_text is None


def test_empty_delta_reported(config):
    body = READY.split("## Spec delta")[0] + "## Spec delta\n\n## Owns" + READY.split("## Owns")[1]
    assert codes(check_unit(body, PROJECT, config)) == [("DOR-DELTA", 9)]


def test_bad_kind(config):
    body = READY.replace("owner-facing\n", "external\n")
    assert codes(check_unit(body, PROJECT, config)) == [("DOR-KIND", 38)]


def test_bad_bet_owns_and_deps(config):
    body = READY.replace("docs/pitches/0001-shopping-list.md", "the PDF bet")
    body = body.replace("- src/import/**\n- tests/import/\n", "nothing yet\n")
    body = body.replace("- #12\n", "- the API unit\n")
    assert [f.code for f in check_unit(body, PROJECT, config)] == [
        "DOR-BET",
        "DOR-OWNS",
        "DOR-DEPS",
    ]


def test_owns_bullet_with_several_paths():
    body = READY.replace(
        "- src/import/**\n", "- `src/import/**`, `docs/import.md` and `package.json`\n"
    )
    assert parse_unit_body(body).owns == [
        "src/import/**",
        "docs/import.md",
        "package.json",
        "tests/import/",
    ]


def test_owns_brace_pattern_expands():
    body = READY.replace(
        "- src/import/**\n", "- `packages/p/src/{passages,select}/index.ts`\n- {a,b/{c,d}}.ts\n"
    )
    assert parse_unit_body(body).owns == [
        "packages/p/src/passages/index.ts",
        "packages/p/src/select/index.ts",
        "a.ts",
        "b/c.ts",
        "b/d.ts",
        "tests/import/",
    ]


def test_depends_parsed():
    assert parse_unit_body(READY).depends_on == [12, 15]
    none = READY.replace("- #12\n- #15\n", "none\n")
    assert parse_unit_body(none).depends_on == []


def test_delta_against_real_spec_fixture(config):
    body = READY.replace("## ADDED Requirements", "## MODIFIED Requirements")
    findings = check_unit(body, PROJECT, config)
    assert codes(findings) == [("DOR-DELTA", 15)]
    assert "DELTA-UNKNOWN" in findings[0].message

    new_area = READY.replace("docs/specs/imports/spec.md", "docs/specs/export/spec.md")
    assert check_unit(new_area, PROJECT, config) == []

    missing = body.replace("docs/specs/imports/spec.md", "docs/specs/export/spec.md")
    findings = check_unit(missing, PROJECT, config)
    assert codes(findings) == [("DOR-DELTA", 11)]
    assert "DELTA-TARGET" in findings[0].message


def test_malformed_body_never_raises():
    unit = parse_unit_body("## Depends on\n\nsoon, maybe #x\n## Kind\n")
    assert unit.depends_on == []
    assert unit.kind is None


def test_template_has_every_section(config):
    findings = check_unit(read_template("github/ISSUE_TEMPLATE/unit.md"), PROJECT, config)
    assert "DOR-SECTION" not in [f.code for f in findings]


def test_check_issue_cli_file(tmp_path, capsys):
    issue = tmp_path / "issue.md"
    issue.write_text(READY.replace("owner-facing\n", "external\n"), encoding="utf-8")
    assert main(["check-issue", "--file", str(issue), "--root", str(PROJECT)]) == 1
    assert "<issue>:38: DOR-KIND" in capsys.readouterr().out
    issue.write_text(READY, encoding="utf-8")
    assert main(["check-issue", "--file", str(issue), "--root", str(PROJECT)]) == 0
