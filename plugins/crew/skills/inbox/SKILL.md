---
name: inbox
description: "Show the owner what is waiting on them, most blocking first, and act on it. Use at the start of every owner session, run by the lead."
---

# Inbox

Run by the lead, with the owner.

1. Run `crew inbox` (without `--peek`: this is the owner's session, so it marks the inbox as
   seen) in the project root and show its output **unchanged**. Don't summarize,
   reorder or drop items: the order (priority, then how much work each item blocks) is the point.
   - If it fails with `crew: error: …`, show the error and what to do (for example `gh auth
     login`, or `crew init` when the config is missing).
2. For each item, the ask says what the owner is asked to do:
   - **accept:** open the PR; the owner runs it with the PR's "How to run" command and walks
     the manual checklist, then approves or comments on GitHub;
   - **decision:** show the question comment and its options; record the owner's choice;
   - **stuck:** show the reviewer's summary; the owner decides how to unstick it;
   - **proposal:** run the pitch challenge with the `crew:pitch` skill.
   When presenting an item, give its URL as `crew inbox` printed it, not only `#N`.
3. Offer to act on each item, one at a time:
   - open the PR or issue (`gh pr view N --web`, `gh issue view N --web`);
   - relay the owner's feedback with the `crew:relay` skill;
   - record a decision: post the owner's words quoted as theirs, run
     `crew labels clear N decision` and set the state the unit needs next (usually
     `crew labels set-state N rough` for refinement).
4. Show the "Merged without you" list and ask whether any of them should be returned as a new
   unit. If so, file it as `crew:rough` with a link to the merged PR and the merged unit's
   priority label (`crew:must`, `crew:should` or `crew:later`).
   If `crew inbox` printed `Parked ideas: N`, mention it and offer to go through them with the
   `crew:ideas` skill.
5. If `crew inbox` listed "Bets to split into units", the owner already bet on those pitches
   by merging them; the merge is their go-ahead. Say so, and offer to split each one now with the
   `crew:architect` subagent (prompt: the pitch PR's URL and "split it into units per your
   brief"), or to leave them to the next `crew run`, which splits them on its own.
6. If cycles are listed, propose which dependency to drop, and fix the issue bodies once the
   owner agrees.

Never act on an item without the owner's say-so in this session. Everything decided is recorded
on GitHub before the session ends.
