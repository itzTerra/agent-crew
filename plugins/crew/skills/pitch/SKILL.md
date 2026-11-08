---
name: pitch
description: "Challenge a pitch with the owner and write it up as a shaped pitch for the owner to bet on. Use when the owner proposes a feature or change, or for a crew:owner-proposal item. Run by the lead."
---

# Pitch

Run by the lead, with the owner.

## 1. Challenge

Have a real back-and-forth. Ask one question at a time; the owner can push back, and you can be
persuaded. Check, in order:

1. **Fit:** with the practices file, accepted ADRs and binding `REQ-…` requirements. Name any
   conflict with its ID.
2. **Worth:** value for users against cost, both build effort and running cost.
3. **Alternatives:** simpler variants, existing features that nearly do it, and "don't build it".
4. **Impact:** what it would break, delay or make harder, including units already in flight
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
## Solution      <- rough: the main elements, not a design
## Rabbit holes
## No-gos
```

Run `crew check-docs`; it must report no errors for the pitch.

## 3. Propose the bet

Commit the pitch on a branch `pitch/NNNN`, push it and open a PR labeled `crew:owner-accept`
and `crew:owner-facing`. **Merging that PR is the bet.** If the owner declines, close the PR
with their reason quoted.

## 4. After the bet

Start the architect to split the pitch into units: one issue per unit from the unit template,
labeled `crew:rough`, with owned paths and dependencies. Shared foundations come first.
