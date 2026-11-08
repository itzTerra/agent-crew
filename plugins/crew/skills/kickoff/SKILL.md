---
name: kickoff
description: "Run the one-time project kickoff with the owner: condense existing documents into the requirements baseline and file the first owner decisions. Run by the lead, once per project."
---

# Kickoff

Run by the lead, with the owner, once per project. Keep it short: features are **not** specified
in detail at kickoff. Living specs grow as features are shaped.

## 1. Gather

Read what already exists: the practices file, product notes, business documents, existing
requirements (`paths.requirements`), ADRs (`paths.adr`) and any prototype results. Ask the owner
which of them are still current.

## 2. Write the baseline

Write `docs/requirements/baseline.md` with:

- **Goals:** what the product is for and how success is judged;
- **Main user flows:** prose, a few sentences each;
- **Epics:** a list of large feature areas, one line each (not detailed features);
- **MVP cut:** which epics form the first release.

Flows and epics are prose and lists. Only hard constraints go in as requirement rows, in the
table format with stable IDs:

```
| ID | Pri | Requirement | Why |
|---|---|---|---|
| REQ-ARCH-1 | Must | <one EARS statement> | <source> |
```

Pri is `Must`, `Should` or `Later`. Requirements no living spec will cite (because a setting or a
process covers them) get a `[covered: <how>]` marker.

Commit it on a branch, open a PR labeled `crew:owner-accept` and `crew:owner-facing`, and run
`crew check-docs` until it reports no errors. `XREF-UNCITED` warnings are expected while there
are no living specs yet.

## 3. File the first decisions

File the first owner decisions as issues labeled `crew:owner-decision`, each for the architect to
prepare as a decision document:

- the architecture and stack ADRs (languages, frameworks, storage, hosting);
- the operations and checks setup (CI, Docker, test and lint tools);
- design-system alternatives (for the designer).

Add dependencies between them where one decision needs another first.
