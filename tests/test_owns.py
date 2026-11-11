import subprocess
from pathlib import Path

from crew import owns
from crew.cli import main
from crew.owns import expand_braces, outside_owns, owns_match
from crew.units import delta_target

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"


def body(owned, target=None):
    delta = f"Target: `{target}`\n\n## ADDED Requirements\n" if target else "none — no spec change"
    own_lines = "\n".join(f"- `{o}`" for o in owned)
    return f"## Goal\n\nG.\n\n## Spec delta\n\n{delta}\n\n## Owns\n\n{own_lines}\n"


def test_owns_match_rules():
    assert owns_match("src/api/a/b.py", "src/api/**")
    assert owns_match("src/a.py", "src/*.py")
    assert not owns_match("src/a/b.py", "src/*.py")
    assert owns_match("src/a.py", "src/?.py") and not owns_match("src/ab.py", "src/?.py")
    assert owns_match("docs/x.md", "docs/x.md")
    assert not owns_match("docs/x.md.bak", "docs/x.md")
    assert owns_match("docs/a.md", "docs/") and owns_match("docs/a.md", "docs")
    assert not owns_match("docs2/a.md", "docs")
    assert owns_match("a/b/c/d.py", "a/**/d.py") and owns_match("a/d.py", "a/**/d.py")


def test_expand_braces():
    assert expand_braces("src/{a,b}/index.ts") == ["src/a/index.ts", "src/b/index.ts"]
    assert expand_braces("{x,y/{1,2}}.md") == ["x.md", "y/1.md", "y/2.md"]
    assert expand_braces("src/{a,}x") == ["src/ax", "src/x"]
    assert expand_braces("plain/**") == ["plain/**"]
    assert expand_braces("src/{a}.ts") == ["src/{a}.ts"]
    assert expand_braces("src/{a,b.ts") == ["src/{a,b.ts"]


def test_check_owns_cli_brace_pattern(monkeypatch, capsys):
    files = ["src/a/index.ts", "src/b/index.ts", "src/c/index.ts"]
    fake = FakeGitHub([5], {5: body(["src/{a,b}/index.ts"])}, files)
    assert run_check(monkeypatch, fake) == 1
    assert capsys.readouterr().out.splitlines() == [
        "src/c/index.ts:1: OWNS-OUTSIDE not in the Owns of #5"
    ]


def test_outside_owns_allows_delta_target():
    paths = ["src/api/x.py", "docs/specs/api/spec.md", "README.md"]
    assert outside_owns(paths, ["src/api/**"], ["docs/specs/api/spec.md"]) == ["README.md"]


def test_delta_target():
    assert delta_target("Target: `docs/specs/a/spec.md`\n\n## ADDED") == "docs/specs/a/spec.md"
    assert delta_target(None) is None and delta_target("no target here") is None


class FakeGitHub:
    def __init__(self, linked, bodies, files=()):
        self.linked, self.bodies, self.files = linked, bodies, list(files)

    def pr_linked_issues(self, number):
        return self.linked

    def issue_body(self, number):
        return self.bodies[number]

    def pr_files(self, number):
        return self.files


def run_check(monkeypatch, fake, *extra):
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    return main(["check-owns", "9", "--root", str(PROJECT), *extra])


def test_check_owns_cli_outside_path_exit_1(monkeypatch, capsys):
    fake = FakeGitHub([5], {5: body(["src/api/**"])}, ["src/api/a.py", "README.md"])
    assert run_check(monkeypatch, fake) == 1
    assert capsys.readouterr().out.splitlines() == [
        "README.md:1: OWNS-OUTSIDE not in the Owns of #5"
    ]


def test_check_owns_cli_clean(monkeypatch, capsys):
    target = "docs/specs/api/spec.md"
    fake = FakeGitHub([5], {5: body(["src/api/**"], target)}, ["src/api/a.py", target])
    assert run_check(monkeypatch, fake) == 0
    assert capsys.readouterr().out.strip() == "all 2 changed paths are inside the Owns of #5"


def test_check_owns_pr_without_issue_ok(monkeypatch, capsys):
    assert run_check(monkeypatch, FakeGitHub([], {})) == 0
    assert capsys.readouterr().out.strip() == "PR #9 closes no issue; nothing to check"


def test_check_owns_issue_without_owns(monkeypatch, capsys):
    fake = FakeGitHub([5], {5: "## Goal\n\nG.\n"}, ["a.py"])
    assert run_check(monkeypatch, fake) == 1
    assert "<issue>:1: OWNS-NONE #5 lists no owned paths" in capsys.readouterr().out


def test_check_owns_range_uses_git_diff(monkeypatch, capsys):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, 0, "src/api/a.py\nother.txt\n", "")

    monkeypatch.setattr(owns, "RUN", fake_run)
    fake = FakeGitHub([5], {5: body(["src/api/**"])}, ["ignored-on-github.txt"])
    assert run_check(monkeypatch, fake, "--range", "origin/main...HEAD") == 1
    assert calls == [(["git", "diff", "--name-only", "origin/main...HEAD"], PROJECT)]
    assert capsys.readouterr().out.splitlines() == [
        "other.txt:1: OWNS-OUTSIDE not in the Owns of #5"
    ]
