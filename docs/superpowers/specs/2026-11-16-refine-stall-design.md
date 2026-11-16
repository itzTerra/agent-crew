# Refine what blocks ready work

## Why

`crew run` stalled in a downstream project with nothing waiting on the owner. #132 and #48 were
`crew:ready`, but #48 depends on #132 and #132 on #140, which is `crew:rough`. The planner plans a
refine only while fewer than `refine_ahead` (default 2) ready units are left, and it counted every
`crew:ready` unit, including the two that can't start. So #140 was never refined, and the run ended
with "nothing to do: everything waits on the owner" while `crew inbox` was empty. Ready units
behind an open PR stalled refinement the same way earlier.

## Goals

- Ready units that can't start don't hold back refinement.
- A rough unit that blocks ready work is refined first, even when enough ready work exists.
- The run's end reason names what is actually stuck, and blames the owner only when the owner
  inbox has something in it.

## Non-goals

- Dependencies stay in the `## Depends on` body section. Moving them to GitHub's blocked-by
  relationships was considered and dropped.
- `refine_ahead` keeps its meaning and default, and a run still has at most one refiner at a
  time.

## Approaches

- **A. Count only startable ready units toward `refine_ahead`.** This fixes the stall above,
  but a rough blocker still waits whenever two other ready units can start.
- **B. A, and refine blockers first (chosen).** A blocker never holds ready work back for long.

## Design

1. **Startable count.** `ready_left` in `planner.py` counts the ready units that weren't picked
   this tick but can start: the ones `ready_report` left out only for the WIP limit or an owns
   overlap. Ready units left out because they depend on an open unit, sit in a dependency cycle,
   wait on the owner, are parked ideas, already run or have an open PR don't count.
2. **Blockers first.** A *blocker* is a rough unit that some `crew:ready` unit depends on,
   directly or through other units (from `_all_dependents`). `rough_order` lists the blockers
   first and then the other rough units. Each group keeps today's `priority_key` order, and the
   exclusions stay: parked ideas and units waiting on the owner are never listed.
3. **Refine trigger.** The planner plans one refine when no refine agent is live and either a
   blocker exists or the startable count is below `refine_ahead`. It refines the first unit of
   `rough_order` that is neither occupied nor has a label problem, as it does today.
4. **End reason.** When the plan is idle and no agents are live, the run ends with:
   - `nothing to do: everything waits on the owner`, only when the owner inbox is non-empty;
   - otherwise `nothing can start: ` followed by the left-out ready units and their reasons, for
     example `#48 depends on open #132; #132 depends on open #140`. Each open dependency gets a
     short tag when it explains the stall: `(parked idea)`, `(waits on the owner)`, `(not a crew
     unit)` for an open issue with no crew state label, or `(in a cycle)`;
   - `nothing to do` when there are no ready or rough units at all.
   The exact wording is the builder's call, but it must name units.

## Tests

- **Planner, stall scenario:** #140 rough; #132 ready, depends on #140; #48 ready, depends on
  #132; other rough units (#58, #59) with a higher priority than #140, and free slots. Expected:
  one refine, of #140.
- **Planner, blocker beats the count:** two startable ready units plus a rough blocker of a third
  ready unit. Expected: the implements and a refine of the blocker.
- **Planner, blocked units don't count:** two ready units that both depend on an open unit, plus
  one rough unit that blocks neither. Expected: the rough unit is refined.
- **Planner:** no second refine while a refine agent is live, blockers or not (extend
  `test_refine_ahead_keeps_one_refiner`).
- **Graph:** `rough_order` puts blockers, direct and indirect, ahead of higher-priority rough
  units, and still leaves out parked ideas and units waiting on the owner.
- **Loop:** the end reason is the owner message when the inbox has an item, and the
  `nothing can start` message naming #48, #132 and #140 when it doesn't (next to
  `test_ends_when_idle_and_no_agents`).

## Left to the builder

- How the planner learns which skip reasons count as startable: a reason kind on `Skipped`, say,
  rather than matching strings.
- Where the end reason is built. The loop has the snapshot, so it can call `owner_inbox` there.
