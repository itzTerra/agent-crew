---
name: refine
description: "Bring rough units up to the definition of ready, in pick order. Run by the architect or the lead in refinement mode."
---

# Refine

Run by the architect (or the lead) in refinement mode.

## Pick

List the rough units (`gh issue list --label crew:rough`). Refine them in the order the
workers will need them: do-first units first, then the ones that block the most other work
(`crew inbox --peek` and `crew next` show the same ordering). Refine a few ahead, not the whole backlog.

## Per unit

1. Read the issue, its bet (the pitch or parent issue) and the living spec it will change.
2. Write or complete the sections, in the unit template's order:
   - **Goal:** one or two sentences;
   - **Bet:** a `docs/pitches/NNNN-slug.md` path or `#N`;
   - **Spec delta:** `Target: docs/specs/<area>/spec.md`, then `## ADDED Requirements`,
     `## MODIFIED Requirements`, `## REMOVED Requirements` or `## RENAMED Requirements`
     sections. Each requirement has one EARS statement with "shall", optional
     `Satisfies: REQ-…`, and scenarios with WHEN and THEN. A unit with no behavior change says
     exactly `none — <reason>`. A new area's spec is created by the first unit that targets it.
   - **Owns:** bullet items with the paths (globs allowed) the unit may change;
   - **Depends on:** bullet items `- #N`, or exactly `none`;
   - **Kind:** `owner-facing` (user-visible, design, decisions, anything in an owner decision
     area) or `internal`. When unsure, `owner-facing`.
3. Run `crew check-issue --number N` and fix the body until it reports nothing.
4. Set `crew:ready` and remove `crew:rough`:
   `gh issue edit N --add-label crew:ready --remove-label crew:rough`.

Scale the effort to the unit: a few lines for a small one, a short brainstorm for a larger one.

## Questions only the owner can answer

Don't guess. Post one comment with the question, the options and your recommendation, add
`crew:owner-decision`, and move on to the next unit. The unit stays rough until it is answered.
