"""GitHub access through the ``gh`` CLI."""

import json
import os
import subprocess
from urllib.parse import quote

from crew.agent import CLEARED_VARS
from crew.labels import Label

ISSUE_FIELDS = "number,title,body,labels,state,createdAt,closedAt,url"
PR_FIELDS = "number,title,labels,headRefName,closingIssuesReferences,mergedAt,author,url"
PR_DETAIL_FIELDS = (
    "number,title,url,state,labels,headRefName,closingIssuesReferences,"
    "reviews,comments,commits,statusCheckRollup"
)
LIST_LIMIT = "1000"


class GitHubError(Exception):
    """A ``gh`` call failed: gh missing, not authenticated, offline, or an API error."""


class GitHub:
    """Thin wrapper over ``gh`` for one repo. ``run`` is injectable for tests."""

    def __init__(self, repo: str, run=subprocess.run, token: str | None = None):
        self.repo = repo
        self._run = run
        # Set by `crew run`: its comments and label moves then come from the agents' account.
        self.token = token

    def list_issues(self, state: str = "open") -> list[dict]:
        """Issues in ``state`` (open, closed or all), with body and labels."""
        return self._json(
            "issue", "list", "--repo", self.repo, "--state", state,
            "--json", ISSUE_FIELDS, "--limit", LIST_LIMIT,
        )  # fmt: skip

    def list_prs(self, state: str = "open") -> list[dict]:
        """Pull requests in ``state`` (open, closed, merged or all)."""
        return self._json(
            "pr", "list", "--repo", self.repo, "--state", state,
            "--json", PR_FIELDS, "--limit", LIST_LIMIT,
        )  # fmt: skip

    def issue_body(self, number: int) -> str:
        """The body of issue ``number``."""
        data = self._json("issue", "view", str(number), "--repo", self.repo, "--json", "body")
        return data.get("body") or ""

    def pr_detail(self, number: int) -> dict:
        """PR ``number`` with its reviews, comments, commits and checks."""
        return self._json(
            "pr", "view", str(number), "--repo", self.repo, "--json", PR_DETAIL_FIELDS
        )

    def issue_comments(self, number: int) -> list[dict]:
        """The comments on issue ``number``."""
        data = self._json("issue", "view", str(number), "--repo", self.repo, "--json", "comments")
        return data.get("comments") or []

    def pr_files(self, number: int) -> list[str]:
        """Paths PR ``number`` changes, from ``gh pr diff --name-only``."""
        out = self._gh("pr", "diff", str(number), "--repo", self.repo, "--name-only")
        return [line for line in out.splitlines() if line.strip()]

    def pr_linked_issues(self, number: int) -> list[int]:
        """The issues PR ``number`` closes."""
        data = self._json(
            "pr", "view", str(number), "--repo", self.repo, "--json", "closingIssuesReferences"
        )
        return [ref["number"] for ref in data.get("closingIssuesReferences") or []]

    def labels_of(self, number: int) -> set[str]:
        """Label names on issue or PR ``number``."""
        data = self._json("api", f"repos/{self.repo}/issues/{number}")
        return {label["name"] for label in (data.get("labels") or [])}

    def ensure_labels(self, labels: list[Label]) -> list[str]:
        """Create missing labels and update changed ones; return the names written."""
        existing = {
            item["name"]: item
            for item in self._json(
                "label",
                "list",
                "--repo",
                self.repo,
                "--json",
                "name,color,description",
                "--limit",
                LIST_LIMIT,
            )  # fmt: skip
        }
        written = []
        for label in labels:
            current = existing.get(label.name)
            if (
                current
                and current.get("color", "").lower() == label.color.lower()
                and (current.get("description") or "") == label.description
            ):
                continue
            self._gh(
                "label", "create", label.name, "--repo", self.repo,
                "--color", label.color, "--description", label.description, "--force",
            )  # fmt: skip
            written.append(label.name)
        return written

    def set_labels(self, number: int, add: list[str], remove: list[str]) -> None:
        """Add and remove labels on an issue or pull request."""
        base = f"repos/{self.repo}/issues/{number}/labels"
        if add:
            fields = [arg for name in add for arg in ("-f", f"labels[]={name}")]
            self._gh("api", "--method", "POST", base, *fields)
        for name in remove:
            try:
                self._gh("api", "--method", "DELETE", f"{base}/{quote(name, safe='')}")
            except GitHubError as exc:
                if "HTTP 404" not in str(exc):  # the label wasn't on it: already removed
                    raise

    def comment(self, number: int, body: str) -> None:
        """Post a comment on an issue or pull request."""
        self._gh(
            "api", "--method", "POST", f"repos/{self.repo}/issues/{number}/comments",
            "-f", f"body={body}",
        )  # fmt: skip

    def _json(self, *args: str):
        out = self._gh(*args)
        try:
            return json.loads(out) if out.strip() else []
        except json.JSONDecodeError as exc:
            raise GitHubError(f"gh {args[0]} {args[1]} returned invalid JSON: {exc}") from None

    def _gh(self, *args: str) -> str:
        argv = ["gh", *args]
        try:
            if self.token is None:
                result = self._run(argv, capture_output=True, text=True, check=False)
            else:
                env = {k: v for k, v in os.environ.items() if k not in CLEARED_VARS}
                env["GH_TOKEN"] = self.token
                result = self._run(argv, capture_output=True, text=True, check=False, env=env)
        except FileNotFoundError:
            raise GitHubError("gh is not installed or not on PATH") from None
        if result.returncode != 0:
            detail = " ".join((result.stderr or result.stdout or "").split())
            raise GitHubError(f"gh {args[0]} {args[1]} failed: {detail or 'no output'}")
        return result.stdout
