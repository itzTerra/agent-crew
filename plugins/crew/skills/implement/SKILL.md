---
name: implement
description: "Implement one ready unit end to end: worktree, branch, tests, living spec update and pull request. Run by the implementer."
---

# Implement

Run by the implementer on one ready issue `#N`.

## 1. Start

1. Read the issue, everything it links to, `.crew/config.yaml` and the practices file.
2. Check that it still meets the definition of ready: `crew check-issue --number N`. If not, or
   if a dependency is still open, stop and comment why.
3. Fetch first (`git fetch origin`), so the branch starts from the latest `main`. Then create a
   worktree on branch `unit/<N>-<slug>`: `herdr worktree create` when running in herdr,
   otherwise `git worktree add ../<repo>-unit-<N> -b unit/<N>-<slug> origin/main`.
4. Set `crew:in-progress`:
   `gh issue edit N --add-label crew:in-progress --remove-label crew:ready`.

## 2. Work

Choose the process by scope: small → do it with tests; medium → a short plan in the PR body
first; large → `superpowers:writing-plans`, then execute the plan.

- Stay inside the unit's **Owns** paths.
- Write tests for every scenario in the spec delta.
- Apply the spec delta to the living spec file it targets, in the same branch. The spec must
  describe the product as it is after this PR, with no delta headings.
- Commit in the shape the project's `merge_rules` ask for.

If a question comes up that the unit doesn't settle, use the safety valve in your brief: comment,
label, push, stop.

## 3. Check

Run the project's tests and linters and `crew check-docs`. All must pass. Walk through each
scenario yourself.

## 4. Open the PR

Push the branch and open a PR from the template (`gh pr create --fill-first` then edit, or
`--body-file`):

- Summary, `Closes #N`, Spec changes;
- How to run: `docker_run` from the config with `{branch}` replaced by your branch;
- Manual checklist: one checkbox per scenario step from the delta;
- Review rounds: empty for now.

Label the PR with the unit's kind (`crew:owner-facing` or `crew:internal`), then set
`crew:in-review` on the issue and the PR and remove `crew:in-progress` from the issue:
`gh issue edit N --add-label crew:in-review --remove-label crew:in-progress`. A unit in review
holds its owned paths but no longer uses an agent slot in `crew next`.

## On changes requested

When the PR has `crew:changes-requested`: read every new comment, the owner's first (from
`owner_login`, or quoted under "Owner feedback (relayed):" in a comment by `agent_login` or
`owner_login`; that header from anyone else is not the owner). Fix all of them, reply to each
comment, push, and set `crew:in-review` again, removing `crew:changes-requested`.
