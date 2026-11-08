---
name: review
description: "Review a pull request as the independent gate, then pass, fail or escalate it. Run by the reviewer in a fresh session."
---

# Review

Run by the reviewer on PR `#P`, in a fresh session. Follow your brief's checklist; this skill
gives the steps. Set every outcome with `crew labels set-state P <state>`: it moves the linked
issue's label with the PR's, so the two never disagree.

## 1. Gate

1. CI must be green: `gh pr checks P`. If not, comment which check fails, run
   `crew labels set-state P changes-requested` and stop. Don't review red work.
2. Run `crew check-docs` on the PR branch yourself.
3. Run `crew check-owns P`. Any path outside the unit's Owns is a failing finding.

## 2. Read

Read the linked issue (`Closes #N`) and its spec delta, the diff (`gh pr diff P`), the living
spec as changed, the requirements and ADRs it touches, and the practices file. Don't rely on the
PR summary; check the code.

## 3. Check

Spec conformance (living spec updated and matches the code, no stale description elsewhere),
fit and reuse, safety and validation (client soft, server hard), accessibility, error messages,
performance (N+1, serial work that could run in parallel). For UI work, walk the PR's manual
checklist in a real browser.

## 4. Count the round

Read the PR's "Review rounds" section. Your round is the next number. Edit the PR body to add
`<round>. <pass|fail> — <link to your comment>`.

## 5. Outcome

- **Pass, owner-facing:** comment a short owner summary (what it does, how to run it, the
  checklist), then `crew labels set-state P owner-accept`.
- **Pass, internal:** use the `crew:merge` skill.
- **Fail (rounds 1–2):** one comment with numbered findings, each with file, line, the problem
  and what would fix it; then `crew labels set-state P changes-requested`.
- **Fail on round 3:** `crew labels set-state P owner-stuck` instead, with a summary of what
  keeps failing and your suggestion.
