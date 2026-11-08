"""Edge cases across the CLI: labels, cycles, busy units, fences, unreadable input."""

import shutil
from pathlib import Path

from crew.cli import main
from crew.config import load_config
from crew.docs.specs import parse_delta, parse_spec
from crew.graph import build_units, next_ready, owns_overlap
from crew.units import check_unit, parse_unit_body
from tests.test_graph import issue
from tests.test_inbox import FakeGitHub

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"


def test_owner_facing_kind_label_is_not_parked():
    units = build_units([issue(1, labels=["crew:ready", "crew:owner-facing"])])
    assert next_ready(units, running=[], max_agents=2) == [1]


def test_next_cli_reports_cycles(monkeypatch, capsys):
    fake = FakeGitHub(
        [issue(3, deps=[4], labels=["crew:ready"]), issue(4, deps=[3], labels=["crew:ready"])],
        [],
        [],
    )
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["next", "--root", str(PROJECT)]) == 0
    assert "#3 → #4 → #3" in capsys.readouterr().out


def test_inbox_peek_keeps_marker(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeGitHub([], [], []))
    assert main(["inbox", "--peek", "--root", str(root)]) == 0
    assert not (root / ".crew/state.json").exists()


def test_units_in_review_block_paths_but_not_slots():
    units = build_units(
        [
            issue(1, labels=["crew:in-review"], owns=["src/a/**"]),
            issue(2, labels=["crew:ready"], owns=["src/a/x.py"]),
            issue(3, labels=["crew:ready"], owns=["src/b/**"]),
            issue(4, labels=["crew:ready"], owns=["src/c/**"]),
        ]
    )
    assert next_ready(units, running=[], max_agents=2, busy=[1]) == [3, 4]


def test_next_cli_counts_only_in_progress(monkeypatch, capsys):
    fake = FakeGitHub(
        [
            issue(1, labels=["crew:in-review"], owns=["a/"]),
            issue(2, labels=["crew:owner-accept"], owns=["b/"]),
            issue(3, labels=["crew:ready"], owns=["c/"]),
            issue(4, labels=["crew:ready"], owns=["a/x"]),
        ],
        [],
        [],
    )
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["next", "--root", str(PROJECT)]) == 0
    assert capsys.readouterr().out.strip().splitlines() == ["#3 Unit 3"]


def test_owns_paths_are_normalized():
    body = "## Owns\n\n- `src/api/**`\n- ./src/ui/x.py\n"
    owns = parse_unit_body(body).owns
    assert owns == ["src/api/**", "src/ui/x.py"]
    assert owns_overlap(owns, ["src/api/auth.py"])


SPEC_WITH_FENCE = """\
# Imports

## Purpose

Cooks bring their own recipes.

## Requirements

### Requirement: Size limit

When a cook imports a file, the system shall enforce the configured size limit:

```sh
# set the import size
## not a heading either
```

#### Scenario: Too large

- WHEN the cook imports a 50 MB file
- THEN an error names the limit

### Requirement: Reject locked files

The system rejects locked files.

#### Scenario: Locked file

- WHEN the cook imports a locked file
- THEN an error explains why
"""


def test_headings_inside_code_fences_are_text(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(SPEC_WITH_FENCE, encoding="utf-8")
    spec, findings = parse_spec(path)
    assert [r.name for r in spec.requirements] == ["Size limit", "Reject locked files"]
    assert [(f.code, f.line) for f in findings] == [("SPEC-SHALL", 25)]
    delta = "Target: x\n\n## ADDED Requirements\n\n" + SPEC_WITH_FENCE.split("## Requirements\n")[1]
    parsed, _ = parse_delta(delta, path, None)
    assert [r.name for r in parsed.added] == ["Size limit", "Reject locked files"]


def test_unit_sections_ignore_fenced_headings():
    body = "## Goal\n\nx\n\n```\n## Kind\n```\n"
    assert parse_unit_body(body).kind is None
    assert "Kind" in " ".join(f.message for f in check_unit(body, PROJECT, load_config(PROJECT)))


def one_error_line(capsys) -> str:
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1, err
    assert err[0].startswith("crew: error: ")
    return err[0]


def test_unreadable_documents_are_clean_errors(tmp_path, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    (root / "docs/requirements/bad.md").write_bytes(b"\xff\xfe\x00bad")
    assert main(["check-docs", "--root", str(root)]) == 2
    assert "bad.md" in one_error_line(capsys)
    issue_file = tmp_path / "issue.md"
    issue_file.write_bytes(b"\xff\xfe")
    assert main(["check-issue", "--file", str(issue_file), "--root", str(root)]) == 2
    one_error_line(capsys)


def test_paths_must_be_a_mapping(tmp_path, capsys):
    (tmp_path / ".crew").mkdir()
    (tmp_path / ".crew/config.yaml").write_text(
        "repo: a/b\nowner_login: o\nagent_login: a\npaths: 5\n", encoding="utf-8"
    )
    assert main(["check-docs", "--root", str(tmp_path)]) == 2
    assert "paths" in one_error_line(capsys)


def test_init_on_unwritable_root_is_clean_error(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    argv = ["init", "--repo", "a/b", "--owner", "o", "--agent", "a", "--root", str(blocker)]
    assert main(argv) == 2
    one_error_line(capsys)


def test_state_write_failure_is_clean_error(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    (root / ".crew/state.json").mkdir()
    monkeypatch.setattr("crew.cli.make_github", lambda repo: FakeGitHub([], [], []))
    assert main(["inbox", "--root", str(root)]) == 2
    one_error_line(capsys)


def test_bad_arguments_give_one_error_line(capsys):
    assert main(["check-issue"]) == 2
    one_error_line(capsys)
    assert main(["no-such-command"]) == 2
    one_error_line(capsys)


def test_labels_needs_an_action(capsys):
    assert main(["labels"]) == 2
    one_error_line(capsys)
