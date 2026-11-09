---
name: pitch
description: "Challenge a pitch with the owner and write it up as a shaped pitch for the owner to bet on. Use when the owner proposes a feature or change, or for a crew:owner-proposal or crew:idea issue. Run by the lead."
---

# Pitch

Run by the lead, with the owner.

## 1. Understand and challenge

**REQUIRED SUB-SKILL:** Use `superpowers:brainstorming` for the conversation, with these limits:

- Go only as far as agreeing on the problem and picking an approach. Write no design spec,
  don't commit one, and don't run `superpowers:writing-plans`. The pitch file below is the only
  output.
- Keep the approaches at pitch level: the main pieces, not a design.
- "Don't build it" is always one of the approaches, next to simpler variants and existing
  features that nearly do it.

The owner can push back, and you can be persuaded. While you discuss, check each approach for:

1. **Fit:** with the practices file, accepted ADRs and binding `REQ-…` requirements. Name any
   conflict with its ID.
2. **Worth:** value for users against cost, both build effort and running cost.
3. **Impact:** what it would break, delay or make harder, including units already in flight
   (`crew next`, `crew inbox --peek`).

A change to something already built becomes a new unit that modifies the existing living spec.
It never reopens the original issue or creates a second description of the feature.

## 2. Shape

Write what survives as `docs/pitches/NNNN-slug.md` from `docs/pitches/TEMPLATE.md`, with the next
free number:

```
# Pitch NNNN: <title>
## Problem
## Appetite      <- a share of the weekly limit, for example "15 %"
## Priority      <- Must, Should or Later
## Solution      <- rough: the main elements, not a design
## Rabbit holes
## No-gos
```

For `## Priority`, take the idea's priority when the pitch started from a `crew:idea` issue;
otherwise the highest priority of the requirements it serves; otherwise suggest one with a
one-line reason and let the owner confirm.

Run `crew check-docs`; it must report no errors for the pitch.

## 3. Propose the bet

Commit the pitch on a branch `pitch/NNNN`, push it and open a PR labeled `crew:owner-accept`,
`crew:owner-facing` and the pitch's priority (`crew:must`, `crew:should` or `crew:later`). **Merging that PR is the bet.** If the owner declines, close the PR
with their reason quoted.

When the pitch started from a `crew:idea` issue, the PR body says `From idea #N`, never a
closing reference to it. Once the PR is open, close the idea issue with a comment linking the
PR. If the owner declines the bet as "not now", reopen the idea; see the `crew:ideas` skill.

## 4. After the bet

Start the architect to split the pitch into units: one issue per unit from the unit template,
labeled `crew:rough` and the pitch's priority (or higher if a unit's requirements say so), with
owned paths and dependencies. Shared foundations come first.
