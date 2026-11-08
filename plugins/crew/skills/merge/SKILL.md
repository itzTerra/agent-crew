---
name: merge
description: "Merge a pull request once it is accepted (owner-facing) or has passed review (internal), following the project's merge rules. Run by the implementer or the reviewer."
---

# Merge

Run by the implementer or the reviewer on PR `#P`.

## 1. Preconditions

- **Owner-facing unit:** an approving review from `owner_login` on the PR
  (`gh pr view P --json reviews`). A comment, or approval from anyone else, is not enough.
- **Internal unit:** the latest review round in the PR body is a pass.
- No `crew:changes-requested`, `crew:owner-decision` or `crew:owner-stuck` label is on it.

If any precondition fails, stop and say which.

## 2. Shape the history

Read `merge_rules` in `.crew/config.yaml` (free text, or a path to a file that holds the rules)
and follow it. Unless it says otherwise:

- squash fixup, review-fix and docs commits into the feature commits they belong to, so each
  commit is one meaningful change;
- keep ADRs as separate commits;
- rebase onto the latest `main`: `git fetch origin && git rebase origin/main`.

Check that the tree and the tests are unchanged by the squash, then push with
`git push --force-with-lease` (your own unit branch only).

## 3. Merge

Wait for CI to be green again (`gh pr checks P --watch`). Then merge:

- `gh pr merge P --rebase --delete-branch`, or
- `gh pr merge P --squash --delete-branch` when the history is a single commit anyway.

## 4. Clean up

Remove the worktree (`git worktree remove <path>` or the herdr equivalent) and the local branch.
Check that the linked issue closed. Remove `crew:in-review` and `crew:owner-accept` labels from
the PR if they remain.
