---
name: inbox
description: "Show the owner what is waiting on them, most blocking first, and act on it. Use at the start of every owner session, run by the lead."
---

# Inbox

Run by the lead, with the owner.

1. Run `crew inbox` (without `--peek`: this is the owner's session, so it marks the inbox as
   seen) in the project root and show its output **unchanged**. Don't summarize,
   reorder or drop items: the order (do-first, then how much work each item blocks) is the point.
   - If it fails with `crew: error: …`, show the error and what to do (for example `gh auth
     login`, or `crew init` when the config is missing).
2. For each item, the ask says what the owner is asked to do:
   - **accept:** open the PR; the owner runs it with the PR's "How to run" command and walks
     the manual checklist, then approves or comments on GitHub;
   - **decision:** show the question comment and its options; record the owner's choice;
   - **stuck:** show the reviewer's summary; the owner decides how to unstick it;
   - **proposal:** run the pitch challenge with the `crew:pitch` skill.
3. Offer to act on each item, one at a time:
   - open the PR or issue (`gh pr view N --web`, `gh issue view N --web`);
   - relay the owner's feedback with the `crew:relay` skill;
   - record a decision: post the owner's words quoted as theirs, remove `crew:owner-decision`
     and set the label the unit needs next (usually `crew:rough` for refinement).
4. Show the "Merged without you" list and ask whether any of them should be returned as a new
   unit. If so, file it as `crew:rough` with a link to the merged PR.
5. If cycles are listed, propose which dependency to drop, and fix the issue bodies once the
   owner agrees.

Never act on an item without the owner's say-so in this session. Everything decided is recorded
on GitHub before the session ends.
