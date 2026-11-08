from crew.cli import main
from crew.config import load_config
from crew.init import init_project

EXPECTED = {
    ".crew/config.yaml",
    ".gitignore",
    ".github/ISSUE_TEMPLATE/unit.md",
    ".github/pull_request_template.md",
    ".github/workflows/crew-docs.yml",
    "docs/specs/README.md",
    "docs/specs/TEMPLATE.md",
    "docs/pitches/README.md",
    "docs/pitches/TEMPLATE.md",
    "docs/adr/TEMPLATE.md",
}


def test_init_writes_files_and_is_idempotent(tmp_path):
    written = init_project(tmp_path, "example/app", "owner-a", "agent-b")
    assert {p.relative_to(tmp_path).as_posix() for p in written} == EXPECTED
    assert ".crew/state.json" in (tmp_path / ".gitignore").read_text().splitlines()
    config = load_config(tmp_path)
    assert (config.repo, config.owner_login, config.agent_login) == (
        "example/app",
        "owner-a",
        "agent-b",
    )
    assert init_project(tmp_path, "example/app", "owner-a", "agent-b") == []


def test_init_never_overwrites(tmp_path):
    template = tmp_path / ".github" / "pull_request_template.md"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"own template\r\n")
    written = init_project(tmp_path, "example/app", "owner-a", "agent-b")
    assert template not in written
    assert template.read_bytes() == b"own template\r\n"


def test_init_appends_to_existing_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/", encoding="utf-8")
    init_project(tmp_path, "example/app", "owner-a", "agent-b")
    assert (tmp_path / ".gitignore").read_text().splitlines() == [
        "node_modules/",
        ".crew/state.json",
    ]


def test_init_cli(tmp_path, capsys):
    argv = ["init", "--repo", "example/app", "--owner", "o", "--agent", "a"]
    assert main([*argv, "--root", str(tmp_path)]) == 0
    assert "wrote .crew/config.yaml" in capsys.readouterr().out


def test_docs_workflow_pins_crew_version_and_needs_no_token(tmp_path):
    from crew import __version__

    init_project(tmp_path, "example/app", "owner-a", "agent-b")
    workflow = (tmp_path / ".github/workflows/crew-docs.yml").read_text(encoding="utf-8")
    assert f"git+https://github.com/itzTerra/agent-crew@v{__version__}" in workflow
    assert "secrets." not in workflow
