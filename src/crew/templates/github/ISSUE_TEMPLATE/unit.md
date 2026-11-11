---
name: Unit
about: One unit of work = one branch = one pull request
labels: ["crew:rough"]
---

## Goal

<!-- One or two sentences: what this unit achieves. -->

## Bet

<!-- The bet this unit belongs to: a docs/pitches/NNNN-slug.md path or an issue #N. -->

## Spec delta

<!--
The change to one living spec, in delta form. Or exactly: none — <reason>

Target: docs/specs/<area>/spec.md

## ADDED Requirements
### Requirement: <name>
The system shall <...>.
Satisfies: REQ-AREA-1
#### Scenario: <name>
- GIVEN <...>
- WHEN <...>
- THEN <...>
-->

## Owns

<!--
Every path this unit may change, as bullet items in backticks: source, tests, and any config,
manifest or fixture file it touches. `src/api/` owns the whole directory; `*` and `?` match
within one segment, `**` across segments; `src/{a,b}/index.ts` expands to both paths.
-->
- 

## Depends on

<!-- Bullet items #N for issues that must be merged first, or exactly: none -->
none

## Kind

<!-- owner-facing (needs owner acceptance) or internal (merges after review and CI). -->
owner-facing
