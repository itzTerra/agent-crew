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

Work in the unit's worktree, in this order:

1. Bring the branch up to date first: `git fetch origin && git rebase origin/main`. Never build
   the final history from a tree based on an older `main`. Resolve conflicts inside the unit's
   Owns; if a conflict needs a change outside them, stop and report it.
2. Read `merge_rules` in `.crew/config.yaml` (free text, or a path to a file that holds the
   rules) and follow it. Unless it says otherwise, squash fixup, review-fix and docs commits
   into the feature commits they belong to, so each commit is one meaningful change, and keep
   ADRs as separate commits. Check that the tree and the tests are unchanged by the squash.
3. Check the owned paths: `crew check-owns P --range origin/main...HEAD`. If it lists any
   outside path, stop: comment the paths on the PR with its full URL and run
   `crew labels set-state P changes-requested`.
4. Push with `git push --force-with-lease` (your own unit branch only), then run
   `crew check-owns P` again to check GitHub's view of the diff.

## 3. Merge

Wait for CI to be green again (`gh pr checks P --watch`). Then merge **from the main checkout,
not from the unit's worktree**: `--delete-branch` makes gh switch the local checkout to `main`,
which fails inside a worktree while `main` is checked out elsewhere.

- `gh pr merge P --rebase --delete-branch`, or
- `gh pr merge P --squash --delete-branch` when the history is a single commit anyway.

Then check what landed. Take the merge commit from `gh pr view P --json mergeCommit` and run
`crew check-owns P --range <merge-sha>^..<merge-sha>` (for a rebase merge of several commits,
use the range from the first new commit's parent). If it lists outside paths, `main` already
has them and only the owner may fix `main`: run `crew labels set-state N owner-stuck` on the
issue and comment the paths, with the PR's full URL.

## 4. Clean up

Remove the worktree (`git worktree remove <path>` or the herdr equivalent) and the local branch.
Check that the linked issue `#N` closed, then clear its workflow labels and the PR's:
`crew labels set-state N done`.
