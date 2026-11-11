import json
import subprocess
from pathlib import Path

import pytest

from crew.cli import main
from crew.github import GitHub, GitHubError
from crew.labels import LABELS, Label

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"


class FakeGh:
    """Records gh argv and answers from a list of (match, stdout, returncode)."""

    def __init__(self, answers=()):
        self.calls: list[list[str]] = []
        self.answers = list(answers)

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        for match, stdout, code in self.answers:
            if all(part in argv for part in match):
                return subprocess.CompletedProcess(
                    argv, code, stdout, "boom from gh" if code else ""
                )
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_list_issues_argv_and_parse():
    issues = [{"number": 1, "title": "A", "body": "", "labels": [{"name": "crew:ready"}]}]
    fake = FakeGh([(["issue", "list"], json.dumps(issues), 0)])
    assert GitHub("example/app", run=fake).list_issues() == issues
    assert fake.calls == [
        [
            "gh", "issue", "list", "--repo", "example/app", "--state", "open",
            "--json", "number,title,body,labels,state,createdAt,closedAt,url",
            "--limit", "1000",
        ]
    ]  # fmt: skip


def test_list_prs_argv():
    fake = FakeGh([(["pr", "list"], "[]", 0)])
    assert GitHub("example/app", run=fake).list_prs("merged") == []
    assert fake.calls[0][:7] == ["gh", "pr", "list", "--repo", "example/app", "--state", "merged"]
    assert (
        "number,title,labels,headRefName,closingIssuesReferences,mergedAt,author,url"
        in (fake.calls[0])
    )


def test_issue_body():
    fake = FakeGh([(["issue", "view", "7"], json.dumps({"body": "## Goal\n"}), 0)])
    assert GitHub("example/app", run=fake).issue_body(7) == "## Goal\n"


def test_ensure_labels_creates_missing_only():
    existing = [
        {"name": "crew:ready", "color": "0e8a16", "description": "Ready."},
        {"name": "crew:rough", "color": "cccccc", "description": "Old text."},
    ]
    fake = FakeGh([(["label", "list"], json.dumps(existing), 0)])
    wanted = [
        Label("crew:ready", "0E8A16", "Ready."),
        Label("crew:rough", "cccccc", "New text."),
        Label("crew:internal", "5319e7", "Internal."),
    ]
    assert GitHub("example/app", run=fake).ensure_labels(wanted) == ["crew:rough", "crew:internal"]
    creates = [c for c in fake.calls if c[1:3] == ["label", "create"]]
    assert creates == [
        ["gh", "label", "create", "crew:rough", "--repo", "example/app",
         "--color", "cccccc", "--description", "New text.", "--force"],
        ["gh", "label", "create", "crew:internal", "--repo", "example/app",
         "--color", "5319e7", "--description", "Internal.", "--force"],
    ]  # fmt: skip


def test_set_labels_argv():
    fake = FakeGh()
    GitHub("example/app", run=fake).set_labels(5, add=["crew:ready"], remove=["crew:rough"])
    assert fake.calls == [
        ["gh", "api", "--method", "POST", "repos/example/app/issues/5/labels",
         "-f", "labels[]=crew:ready"],
        ["gh", "api", "--method", "DELETE", "repos/example/app/issues/5/labels/crew%3Arough"],
    ]  # fmt: skip


def test_comment_argv():
    fake = FakeGh()
    GitHub("example/app", run=fake).comment(5, "Hello")
    assert fake.calls == [
        ["gh", "api", "--method", "POST", "repos/example/app/issues/5/comments", "-f", "body=Hello"]
    ]


def test_label_set():
    names = [label.name for label in LABELS]
    assert names == [
        "crew:rough", "crew:ready", "crew:in-progress", "crew:in-review",
        "crew:changes-requested", "crew:owner-accept", "crew:owner-decision",
        "crew:owner-stuck", "crew:owner-proposal", "crew:idea", "crew:must",
        "crew:should", "crew:later", "crew:owner-facing", "crew:internal", "crew:design",
    ]  # fmt: skip
    for label in LABELS:
        assert len(label.color) == 6 and label.description.endswith(".")


def test_gh_failure_is_clean_error(tmp_path, monkeypatch, capsys):
    fake = FakeGh([(["issue", "list"], "", 1)])
    with pytest.raises(GitHubError, match="boom from gh"):
        GitHub("example/app", run=fake).list_issues()

    def missing(argv, **kwargs):
        raise FileNotFoundError("gh")

    with pytest.raises(GitHubError, match="gh"):
        GitHub("example/app", run=missing).list_issues()

    monkeypatch.setenv("PATH", str(tmp_path))
    assert main(["labels", "sync", "--root", str(PROJECT)]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("crew: error: ") and "gh" in err[0]
    assert main(["check-issue", "--number", "3", "--root", str(PROJECT)]) == 2


def test_labels_sync_cli(monkeypatch, capsys):
    fake = FakeGh([(["label", "list"], "[]", 0)])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: GitHub(repo, run=fake))
    assert main(["labels", "sync", "--root", str(PROJECT)]) == 0
    out = capsys.readouterr().out
    assert "crew:owner-accept" in out
    assert all("example/app" in c for c in fake.calls)


def test_check_issue_number_cli(monkeypatch, capsys):
    body = json.dumps({"body": "## Goal\n\nx\n"})
    fake = FakeGh([(["issue", "view", "3"], body, 0)])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: GitHub(repo, run=fake))
    assert main(["check-issue", "--number", "3", "--root", str(PROJECT)]) == 1
    assert "<issue>:1: DOR-SECTION" in capsys.readouterr().out


def test_token_reaches_gh_only_through_gh_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "owner-token")
    monkeypatch.setenv("GH_HOST", "example.com")
    seen = {}

    def run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    GitHub("example/app", run=run, token="agents-token").comment(3, "hi")
    env = seen["env"]
    assert env["GH_TOKEN"] == "agents-token"
    assert "GITHUB_TOKEN" not in env and "GH_HOST" not in env


def test_no_token_keeps_the_callers_environment():
    seen = {}

    def run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    GitHub("example/app", run=run).comment(3, "hi")
    assert "env" not in seen
