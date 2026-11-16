# Refine What Blocks Ready Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `crew run` never stalls on a rough unit that blocks ready work, and it ends with a reason that names what is actually stuck.

**Architecture:** `graph.py` marks which left-out ready units can still start (`Skipped.startable`), finds rough *blockers* of ready units, and sorts them first in `rough_order`. `planner.py` counts only startable ready units toward `refine_ahead`, refines a blocker even when that count is met, and builds the end reason (`idle_reason`), which `loop.py` returns instead of its fixed string.

**Tech Stack:** Python 3, pytest, ruff (`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`).

**Spec:** `docs/superpowers/specs/2026-11-16-refine-stall-design.md`

## Global Constraints

- Dependencies stay in the `## Depends on` body section; nothing reads or writes GitHub relationships.
- `refine_ahead` keeps its meaning and default (2); at most one refine agent at a time.
- The owner message stays exactly `nothing to do: everything waits on the owner`, used only when `owner_inbox` is non-empty.
- `planner.py` stays pure: no I/O.

## Review Focus

- A blocker that is occupied (an agent is on it) while enough ready units can start: no non-blocker refine starts in its place. Test in Task 2.
- A ready unit whose dependency has an open PR (`crew:in-review`): it doesn't count as startable, so refinement continues. Test in Task 2.
- A blocker that waits on the owner: never refined, and the run ends with the owner message (inbox non-empty). Test in Task 3.
- A ready unit depending on an open issue with no crew flow label: the end reason tags it `(not a crew unit)`. Test in Task 3.
- Ready units in a dependency cycle: the end reason says so instead of blaming the owner. Test in Task 3.

---

### Task 1: Startable skips and blockers in the graph

**Files:**
- Modify: `src/crew/graph.py` (`Skipped`, `ready_report`, new `blockers`, `rough_order`)
- Test: `tests/test_graph.py`, `tests/test_minors.py` (unchanged expectation must still pass)

**Interfaces:**
- Produces: `Skipped(number: int, reason: str, startable: bool = False)`; `startable` is `True` only for the "owns overlap with #N" and "WIP limit reached (…)" skips.
- Produces: `blockers(units: dict[int, Unit]) -> set[int]`: the `crew:rough` units that some `crew:ready` unit without `crew:idea` depends on, directly or indirectly (via `_all_dependents`).
- Produces: `rough_order(units)` lists blockers first, then the rest; each group in today's `priority_key` order; same exclusions as today.

- [x] **Step 1: Write the failing tests**

In `tests/test_graph.py`, update `test_ready_report_reasons` so the two capacity skips carry the flag:

```python
        Skipped(7, "owns overlap with #1", startable=True),
        Skipped(9, "WIP limit reached (2 of 2 agents)", startable=True),
```

Add:

```python
def test_blockers_direct_and_indirect():
    units = units_of(
        issue(140, labels=["crew:rough"], owns=["a/"]),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132], labels=["crew:ready"], owns=["c/"]),
        issue(58, labels=["crew:rough"], owns=["d/"]),
        issue(60, deps=[61], labels=["crew:rough"], owns=["e/"]),
        issue(61, labels=["crew:rough"], owns=["f/"]),
        issue(70, labels=["crew:rough"], owns=["g/"]),
        issue(71, deps=[70], labels=["crew:idea", "crew:ready"], owns=["h/"]),
    )
    assert blockers(units) == {140}


def test_rough_order_puts_blockers_first():
    units = units_of(
        issue(140, labels=["crew:rough"], owns=["a/"], created="2026-03-01T00:00:00Z"),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132], labels=["crew:ready"], owns=["c/"]),
        issue(58, labels=["crew:rough", "crew:must"], owns=["d/"]),
        issue(59, labels=["crew:rough", "crew:must"], owns=["e/"]),
        issue(90, labels=["crew:rough", "crew:owner-decision"], owns=["f/"]),
        issue(91, deps=[90], labels=["crew:ready"], owns=["g/"]),
    )
    assert rough_order(units) == [140, 58, 59]
```

(Import `blockers` from `crew.graph` at the top of the file.)

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL: `ImportError` for `blockers` (and the `startable` keyword).

- [x] **Step 3: Implement in `src/crew/graph.py`**

Add `startable: bool = False` to `Skipped` (keep it `frozen`), pass `startable=True` at the two capacity skips in `ready_report`, add `blockers`, and prefix `rough_order`'s sort key with `u.number not in found` (where `found = blockers(units)`, computed once). Update the `rough_order` docstring: blockers of ready units come first.

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_graph.py tests/test_minors.py -v`
Expected: PASS (`test_rough_order` in `test_minors.py` still gives `[3, 1, 2, 4]`).

- [x] **Step 5: Commit**

```bash
git add src/crew/graph.py tests/test_graph.py docs/superpowers/plans/2026-11-16-refine-stall.md
git commit -m "feat(graph): mark startable skips and order rough blockers first"
```

---

### Task 2: Refine trigger in the planner

**Files:**
- Modify: `src/crew/supervisor/planner.py:241-249`
- Test: `tests/supervisor/test_planner.py`

**Interfaces:**
- Consumes: `Skipped.startable`, `blockers(units)`, `rough_order(units)` from Task 1.
- Produces: no new names. Behavior: `startable = sum(1 for s in skipped if s.startable)`. With no live refine agent: if `startable < config.refine_ahead`, refine the first unit of `rough_order` that is neither occupied nor has a label problem; otherwise do the same over the blockers only (rough_order filtered to `blockers(...)`), and refine nothing if none qualifies.

- [x] **Step 1: Write the failing tests**

In `tests/supervisor/test_planner.py`:

```python
def test_stall_refines_the_blocker():
    issues = [
        issue(140, labels=["crew:rough"], owns=["a/"]),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132], labels=["crew:ready"], owns=["c/"]),
        issue(58, labels=["crew:rough", "crew:must"], owns=["d/"]),
        issue(59, labels=["crew:rough", "crew:must"], owns=["e/"]),
    ]
    result = make_plan(snap(issues), free_slots=3)
    assert kinds(result) == [("refine", 140)]
    assert result.idle is False


def test_blocker_refined_even_with_enough_ready():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:ready"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(7, labels=["crew:ready"], owns=["g/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["d/"]),
        issue(5, labels=["crew:rough"], owns=["e/"]),
        issue(6, labels=["crew:rough", "crew:must"], owns=["f/"]),
    ]
    # Two picks fill the slots; #3 and #7 can still start, so the count alone plans no refine.
    result = make_plan(snap(issues), free_slots=2)
    assert kinds(result) == [("implement", 1), ("implement", 2)]
    assert "no free agent slot for refine #5" in result.waiting


def test_blocked_ready_units_dont_count():
    issues = [
        issue(1, labels=["crew:in-review"], owns=["a/"]),
        issue(2, deps=[1], labels=["crew:ready"], owns=["b/"]),
        issue(3, deps=[1], labels=["crew:ready"], owns=["c/"]),
        issue(4, labels=["crew:rough"], owns=["d/"]),
    ]
    prs = [pr(9, 1, ["crew:in-review"], checks="pending")]
    result = make_plan(snap(issues, prs), free_slots=2)
    assert kinds(result) == [("refine", 4)]


def test_occupied_blocker_leaves_no_other_refine():
    issues = [
        issue(1, labels=["crew:ready"], owns=["a/"]),
        issue(2, labels=["crew:ready"], owns=["b/"]),
        issue(3, labels=["crew:ready"], owns=["c/"]),
        issue(7, labels=["crew:ready"], owns=["g/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["d/"]),
        issue(5, labels=["crew:rough"], owns=["e/"]),
        issue(6, labels=["crew:rough"], owns=["f/"]),
    ]
    # One live agent plus one slot: #1 and #2 are picked, #3 and #7 can still start.
    result = make_plan(snap(issues), live=[Live("followup", 5, None)], free_slots=1)
    assert [a for a in result.actions if a.kind == "refine"] == []
    assert not any("refine" in line for line in result.waiting)
```

Extend `test_refine_ahead_keeps_one_refiner`: add `issue(4, deps=[2], labels=["crew:ready"], owns=["d/"])` to its issues (so #2 becomes a blocker), keep the existing assertions, but the first plan now refines #2 (the blocker comes first): `assert kinds(result) == [("implement", 3), ("refine", 2)]` and the prompt names `#2`. The `busy` plan with a live refine agent still gives `[("implement", 3)]`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/supervisor/test_planner.py -v`
Expected: FAIL: `test_stall_refines_the_blocker` plans no refine; `test_blocker_refined_even_with_enough_ready` misses `refine #5`.

- [x] **Step 3: Implement the trigger in `plan()`**

Replace the `ready_left` block (`planner.py:241-249`) with the behavior in this task's Interfaces block. Drop the `READY` import if it becomes unused. Update `plan()`'s docstring with one sentence: a refine starts while fewer than `refine_ahead` ready units can start, or for a rough unit that blocks ready work.

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/supervisor -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/crew/supervisor/planner.py tests/supervisor/test_planner.py docs/superpowers/plans/2026-11-16-refine-stall.md
git commit -m "fix(run): refine what blocks ready work and count only startable units"
```

---

### Task 3: Honest end reason

**Files:**
- Modify: `src/crew/supervisor/planner.py` (new `OWNER_IDLE`, `idle_reason`)
- Modify: `src/crew/supervisor/loop.py:47,282-283` (drop `IDLE_END`, return `idle_reason(snapshot)`)
- Test: `tests/supervisor/test_planner.py`, `tests/supervisor/test_loop.py`

**Interfaces:**
- Consumes: `owner_inbox(units, open_prs)` from `crew.inbox`; `find_cycles`, `FLOW`, `IDEA`, `WAITING_ON_OWNER`, `READY`.
- Produces: `OWNER_IDLE = "nothing to do: everything waits on the owner"` and `idle_reason(snapshot: Snapshot) -> str` in `planner.py`:
  1. `owner_inbox(snapshot.units, list(snapshot.prs.values()))` non-empty → `OWNER_IDLE`.
  2. Else, for each `crew:ready` unit without `crew:idea` or an owner-ask label, by number: in a cycle → `#N is in a dependency cycle`; with open dependencies → `#N depends on open #D[ tag], #E[ tag]`. Tag of a dependency, first that applies: ` (in a cycle)`, ` (parked idea)`, ` (waits on the owner)`, ` (not a crew unit)` (no `FLOW` label). If any parts → `"nothing can start: " + "; ".join(parts)`.
  3. Else → `"nothing to do"`.

- [ ] **Step 1: Write the failing tests**

In `tests/supervisor/test_planner.py` (import `idle_reason`, `OWNER_IDLE`):

```python
def test_idle_reason_names_the_stall():
    issues = [
        issue(140, labels=["crew:idea"], owns=["a/"]),
        issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        issue(48, deps=[132, 77], labels=["crew:ready"], owns=["c/"]),
        issue(77, owns=["d/"]),
        issue(4, deps=[5], labels=["crew:ready"], owns=["e/"]),
        issue(5, deps=[4], labels=["crew:rough"], owns=["f/"]),
    ]
    assert idle_reason(snap(issues)) == (
        "nothing can start: #4 is in a dependency cycle; "
        "#48 depends on open #132, #77 (not a crew unit); "
        "#132 depends on open #140 (parked idea)"
    )


def test_idle_reason_blames_owner_only_with_inbox():
    waiting = [
        issue(5, labels=["crew:rough", "crew:owner-decision"], owns=["a/"]),
        issue(6, deps=[5], labels=["crew:ready"], owns=["b/"]),
    ]
    assert idle_reason(snap(waiting)) == OWNER_IDLE
    assert idle_reason(snap([])) == "nothing to do"
```

In `tests/supervisor/test_loop.py`, next to `test_ends_when_idle_and_no_agents`:

```python
def test_ends_naming_the_stall_when_nothing_waits_on_owner(root, tmp_path):
    github = FakeGitHub(
        [
            issue(140, labels=["crew:idea"], owns=["a/"]),
            issue(132, deps=[140], labels=["crew:ready"], owns=["b/"]),
        ]
    )
    supervisor = make(root, tmp_path, github)
    assert supervisor.tick() == "nothing can start: #132 depends on open #140 (parked idea)"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/supervisor/test_planner.py tests/supervisor/test_loop.py -v`
Expected: FAIL: `ImportError` for `idle_reason`; the loop test gets the owner message.

- [ ] **Step 3: Implement `idle_reason` and use it in the loop**

Add `OWNER_IDLE` and `idle_reason` to `planner.py` per the Interfaces block (iterate ready units sorted by number). In `loop.py`, remove `IDLE_END` and return `idle_reason(snapshot)` where it was returned.

- [ ] **Step 4: Run the whole suite and the linters**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: all pass, no findings.

- [ ] **Step 5: Commit**

```bash
git add src/crew/supervisor/planner.py src/crew/supervisor/loop.py tests/supervisor/test_planner.py tests/supervisor/test_loop.py docs/superpowers/plans/2026-11-16-refine-stall.md
git commit -m "fix(run): end with what is stuck, not the owner, when the inbox is empty"
```
