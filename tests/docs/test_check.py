import shutil
from pathlib import Path

import pytest

from crew.cli import main
from crew.config import load_config
from crew.docs.check import check_docs

PROJECT = Path(__file__).resolve().parent.parent / "fixtures" / "project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    return root


def check(root: Path, strict: bool = False):
    return [(f.code, f.severity) for f in check_docs(root, load_config(root), strict=strict)]


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_fixture_project_clean(project):
    assert check(project) == []


def test_unknown_satisfies_id(project):
    spec = project / "docs/specs/imports/spec.md"
    edit(spec, "Satisfies: REQ-SRC-1", "Satisfies: REQ-SRC-9")
    findings = check_docs(project, load_config(project))
    assert [(f.code, f.path, f.line) for f in findings if f.code == "XREF-REQ"] == [
        ("XREF-REQ", spec, 20)
    ]


def test_duplicate_req_across_files(project):
    other = project / "docs/requirements/extra.md"
    other.write_text(
        "| ID | Pri | Requirement | Why |\n|---|---|---|---|\n| REQ-ARCH-1 | Must | Again. |\n",
        encoding="utf-8",
    )
    findings = check_docs(project, load_config(project))
    assert [(f.code, f.path.name, f.line) for f in findings] == [("REQ-DUP", "extra.md", 3)]


def test_uncited_is_warning_then_error_in_strict(project):
    spec = project / "docs/specs/imports/spec.md"
    edit(spec, "Satisfies: REQ-SRC-1\n", "")
    assert check(project) == [("XREF-UNCITED", "warning")]
    assert check(project, strict=True) == [("XREF-UNCITED", "error")]


def test_superseding_adr_must_exist(project):
    adr = project / "docs/adr/0001-use-sqlite-for-storage.md"
    edit(adr, "- **Status:** Accepted", "- **Status:** Superseded by ADR-0004")
    assert check(project) == [("ADR-REF", "error")]


def test_spec_and_pitch_findings_included(project):
    edit(project / "docs/pitches/0001-shopping-list.md", "## No-gos", "## Later")
    edit(project / "docs/specs/imports/spec.md", "## Purpose", "## Why")
    assert sorted(check(project)) == [("PITCH-SECTION", "error"), ("SPEC-PURPOSE", "error")]


def test_missing_dirs_ok(tmp_path):
    (tmp_path / ".crew").mkdir()
    shutil.copy(PROJECT / ".crew/config.yaml", tmp_path / ".crew/config.yaml")
    assert check(tmp_path) == []


def test_cli_exit_codes(project, tmp_path, capsys):
    assert main(["check-docs", "--root", str(project)]) == 0

    spec = project / "docs/specs/imports/spec.md"
    edit(spec, "Satisfies: REQ-SRC-1\n", "")
    capsys.readouterr()
    assert main(["check-docs", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert "docs/requirements/core.md:6: warning: XREF-UNCITED" in out
    assert main(["check-docs", "--root", str(project), "--strict"]) == 1

    edit(spec, "## Purpose", "## Why")
    assert main(["check-docs", "--root", str(project)]) == 1
    assert "docs/specs/imports/spec.md:1: SPEC-PURPOSE" in capsys.readouterr().out

    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["check-docs", "--root", str(empty)]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("crew: error: ")
