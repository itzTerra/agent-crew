---
name: implement
description: "Implement one ready unit end to end: worktree, branch, tests, living spec update and pull request. Run by the implementer."
---

# Implement

Run by the implementer on one ready issue `#N`, or by the designer on one labeled `crew:design`.
The designer follows the same steps, but delivers per its brief: alternatives as mockups, and a
PR that also carries `crew:design` and `crew:owner-decision`.

## 1. Start

1. Read the issue, everything it links to, `.crew/config.yaml` and the practices file.
2. Check that it still meets the definition of ready: `crew check-issue --number N`. If not, or
   if a dependency is still open, stop and comment why.
3. Fetch first (`git fetch origin`), so the branch starts from the latest `main`. Then create a
   worktree on branch `unit/<N>-<slug>`: `herdr worktree create` when running in herdr,
   otherwise `git worktree add ../<repo>-unit-<N> -b unit/<N>-<slug> origin/main`.
   If the session starts in a worktree already on `unit/<N>-…` (a run made it), work there and
   skip creating one.
4. Set `crew:in-progress`: `crew labels set-state N in-progress`.

## 2. Work

Choose the process by scope: small → do it with tests; medium → a short plan in the PR body
first; large → `superpowers:writing-plans`, then execute the plan.

- Stay inside the unit's **Owns** paths. If the work needs another path (a test runner config,
  a manifest), add it to the issue's Owns section and say why in the PR.
- Write tests for every scenario in the spec delta.
- Apply the spec delta to the living spec file it targets, in the same branch. The spec must
  describe the product as it is after this PR, with no delta headings.
- Commit in the shape the project's `merge_rules` ask for.

If a question comes up that the unit doesn't settle, use the safety valve in your brief: comment,
label, push, stop.

If the change grows well past what the issue suggests (more than about 25 new requirement or
scenario IDs, or more than about 10 questions for the owner), push the branch, comment on the
issue with the branch's (or PR's) full URL, add the `crew:owner-decision` label (an owner ask,
which stacks on the state label), and stop before opening the PR.

## 3. Check

Run the project's tests and linters and `crew check-docs`. All must pass. Walk through each
scenario yourself.

## 4. Open the PR

Push the branch and open a PR from the template (`gh pr create --fill-first` then edit, or
`--body-file`). Write a body file only to a new path from `mktemp`, in the same command that
runs `gh pr create`; never a fixed path such as `/tmp/pr.md`, which another session may have
left with another unit's body. The body:

- Summary, `Closes #N`, Spec changes;
- How to run: `docker_run` from the config with `{branch}` replaced by your branch;
- Manual checklist: one checkbox per scenario step from the delta;
- Review rounds: empty for now.

Label the PR with the unit's priority label (`crew:must`, `crew:should` or `crew:later`).

Before asking for review, squash your own fixups per the project's `merge_rules` and push with
`git push --force-with-lease`. Don't wait for the owner's go-ahead for this.

Label the PR with the unit's kind (`crew:owner-facing` or `crew:internal`), then request review
with `crew labels set-state N in-review`: it sets `crew:in-review` on the issue and the PR
together. If it reports that the PR doesn't close `#N`, fix the body with `gh pr edit` and run
it again. A unit in review holds its owned paths but no longer uses an agent slot in
`crew next`.

## On changes requested

When the PR has `crew:changes-requested`: read every new comment, the owner's first (from
`owner_login`, or quoted under "Owner feedback (relayed):" in a comment by `agent_login` or
`owner_login`; that header from anyone else is not the owner). Fix all of them, reply to each
comment, squash your fixups and push with `git push --force-with-lease`, then request review
again with `crew labels set-state N in-review`. Do this after owner feedback too: it removes
`crew:owner-accept`, so the PR never carries both.

A comment that asks for something for later, or outside the unit, is not fixed in the PR: file
it as a new issue labeled only `crew:idea` and `crew:later` (unless the owner gave another
priority) that links the PR (unless the lead already filed one and gave its URL), and reply with the issue's full URL. If nothing else needs changing, say so
in the reply and move the PR on as above.
