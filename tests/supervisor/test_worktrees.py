import subprocess
from pathlib import Path

from crew.supervisor.worktrees import worktree_for

ROOT = Path("/src/app")
WT = ROOT / ".crew" / "worktrees"


class FakeGit:
    def __init__(self, worktrees="", remote=(), local=()):
        self.calls = []
        self.worktrees, self.remote, self.local = worktrees, set(remote), set(local)

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        out, code = "", 0
        if argv[1:4] == ["-C", str(ROOT), "worktree"] and argv[4] == "list":
            out = self.worktrees
        elif "rev-parse" in argv:
            ref = argv[-1]
            known = {f"refs/remotes/origin/{b}" for b in self.remote}
            known |= {f"refs/heads/{b}" for b in self.local}
            code = 0 if ref in known else 1
        return subprocess.CompletedProcess(argv, code, out, "")


def git(*args):
    return ["git", "-C", str(ROOT), *args]


def changes(fake):
    """The calls that change something (no reads)."""
    return [c for c in fake.calls if "rev-parse" not in c and "list" not in c]


def test_worktree_new_unit_branch(tmp_path):
    fake = FakeGit()
    path = worktree_for(ROOT, "unit/12-add-csv", run=fake, ignore_dir=False)
    assert path == WT / "unit-12"
    assert changes(fake) == [
        git("fetch", "origin"),
        git("worktree", "add", "-b", "unit/12-add-csv", str(WT / "unit-12"), "origin/main"),
    ]


def test_worktree_reuses_existing():
    listing = (
        f"worktree {ROOT}\nHEAD abc\nbranch refs/heads/main\n\n"
        f"worktree /elsewhere/app-unit-12\nHEAD def\nbranch refs/heads/unit/12-add-csv\n\n"
    )
    fake = FakeGit(worktrees=listing, remote={"unit/12-add-csv"}, local={"unit/12-add-csv"})
    path = worktree_for(ROOT, "unit/12-add-csv", run=fake, ignore_dir=False)
    assert path == Path("/elsewhere/app-unit-12")
    assert changes(fake) == [
        git("fetch", "origin"),
        ["git", "-C", str(path), "merge", "--ff-only", "origin/unit/12-add-csv"],
    ]


def test_worktree_tracks_remote_branch():
    fake = FakeGit(remote={"unit/12-add-csv"})
    path = worktree_for(ROOT, "unit/12-add-csv", run=fake, ignore_dir=False)
    assert changes(fake)[-1] == git(
        "worktree", "add", "--track", "-b", "unit/12-add-csv", str(path),
        "origin/unit/12-add-csv",
    )  # fmt: skip
    local = FakeGit(remote={"unit/12-add-csv"}, local={"unit/12-add-csv"})
    worktree_for(ROOT, "unit/12-add-csv", run=local, ignore_dir=False)
    assert changes(local)[-2] == git("worktree", "add", str(path), "unit/12-add-csv")
    other = FakeGit(remote={"docs/adr-7"})
    assert worktree_for(ROOT, "docs/adr-7", run=other, ignore_dir=False) == WT / "docs-adr-7"


def test_worktree_detached_review_refreshes():
    fake = FakeGit(remote={"unit/12-add-csv"})
    path = worktree_for(ROOT, "unit/12-add-csv", detach=True, run=fake, ignore_dir=False)
    assert path == WT / "review-unit-12-add-csv"
    assert changes(fake)[-1] == git(
        "worktree", "add", "--detach", str(path), "origin/unit/12-add-csv"
    )
    listing = f"worktree {path}\nHEAD abc\ndetached\n\n"
    again = FakeGit(worktrees=listing, remote={"unit/12-add-csv"})
    assert worktree_for(ROOT, "unit/12-add-csv", detach=True, run=again, ignore_dir=False) == path
    assert changes(again) == [
        git("fetch", "origin"),
        ["git", "-C", str(path), "checkout", "--detach", "origin/unit/12-add-csv"],
    ]


def test_worktree_dir_ignores_itself(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    fake = FakeGit()
    fake_root = root
    worktree_for(fake_root, "unit/3-x", run=fake)
    assert (root / ".crew" / "worktrees" / ".gitignore").read_text() == "*\n"


def test_reused_branch_fast_forwards_to_remote():
    # M6: a stale local branch would let --force-with-lease overwrite pushed commits.
    listing = f"worktree {WT / 'unit-12'}\nHEAD def\nbranch refs/heads/unit/12-add-csv\n\n"
    fake = FakeGit(worktrees=listing, remote={"unit/12-add-csv"}, local={"unit/12-add-csv"})
    worktree_for(ROOT, "unit/12-add-csv", run=fake, ignore_dir=False)
    assert changes(fake)[-1] == [
        "git", "-C", str(WT / "unit-12"), "merge", "--ff-only", "origin/unit/12-add-csv"
    ]  # fmt: skip
    local = FakeGit(remote={"unit/12-add-csv"}, local={"unit/12-add-csv"})
    worktree_for(ROOT, "unit/12-add-csv", run=local, ignore_dir=False)
    assert changes(local)[-1][-3:] == ["merge", "--ff-only", "origin/unit/12-add-csv"]
