---
name: refine
description: "Bring rough units up to the definition of ready, in pick order. Run by the architect or the lead in refinement mode."
---

# Refine

Run by the architect (or the lead) in refinement mode.

## Pick

Given one unit (`#N`), refine only that unit, and stop when it is done.

Only when asked to refine the backlog, run `crew next --rough`: it lists the rough units in the
order the workers will need them (priority, then the ones that block the most other work, then
the oldest), leaving out units that wait on the owner. Take them from the top. Refine a few
ahead, not the whole backlog.

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
   - **Owns:** bullet items with every path the unit may change: the source and tests, and
     also the config, manifest and fixture files the change touches (a test runner config such
     as `vitest.config.ts`, `package.json`, a lockfile). `crew check-owns` fails a PR on any
     other path. Write each path in backticks; several may share a bullet. Patterns:
     - `src/api/` (or `src/api`) owns everything under that directory;
     - `*` and `?` match within one path segment, `**` across segments (`src/**/*.test.ts`);
     - `{a,b}` expands to one path per alternative:
       `packages/p/src/{passages,select}/index.ts`.

     Prefer a directory or a glob over a long file list, but keep it as narrow as the work, so
     units that should run in parallel don't overlap;
   - **Depends on:** bullet items `- #N`, or exactly `none`;
   - **Kind:** `owner-facing` (user-visible, design, decisions, anything in an owner decision
     area) or `internal`. When unsure, `owner-facing`.
3. If the unit's deliverable is design (a design system, or flow and screen alternatives as
   mockups), add the `crew:design` label, so a run gives it to the designer instead of the
   implementer.
4. Run `crew check-issue --number N` and fix the body until it reports nothing.
5. Set `crew:ready`: `crew labels set-state N ready`.

Scale the effort to the unit: a few lines for a small one, a short brainstorm for a larger one.

If refining shows the unit will grow well past the issue (more than about 25 new requirement or
scenario IDs, or more than about 10 questions for the owner), don't set it ready: say so on the
issue, with its full URL, and propose a split into smaller units.

## Questions only the owner can answer

Don't guess. Post one comment with the question, the options and your recommendation, run
`crew labels ask N decision`, and move on to the next unit. The unit stays rough until it is
answered.
