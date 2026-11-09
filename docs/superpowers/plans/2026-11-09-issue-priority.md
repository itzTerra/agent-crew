# Issue and PR Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every issue and PR a `crew:must` / `crew:should` / `crew:later` priority that drives the inbox, refine and pick orders, replacing `crew:do-first`.

**Architecture:** Three new labels in `src/crew/labels.py`. `src/crew/graph.py` computes an *effective rank* per open unit (own label, raised by any open dependent's), and `priority_key` sorts on it instead of do-first. Plugin texts (agents, skills, `docs/workflow.md`) tell every filer which priority to set. Pitches gain a `## Priority` section, checked as a warning when missing.

**Tech Stack:** Python 3.12, pytest, uv; Claude Code plugin Markdown.

**Spec:** `docs/superpowers/specs/2026-11-09-issue-priority-design.md`

## Global Constraints

- Label names exactly `crew:must`, `crew:should`, `crew:later`; rank 0, 1, 2 in that order.
- An item with no priority label counts as `should`.
- Effective priority is computed, never written back to GitHub labels.
- `crew:do-first` and `DO_FIRST` are removed everywhere (code, tests, plugin, docs). `crew labels sync` still deletes nothing.
- Pitch: missing `## Priority` is a `warning` (`PITCH-PRIORITY`); a value other than `Must`, `Should`, `Later` is an error (`PITCH-PRIORITY`).
- Agent bodies stay ≤ 150 lines, skill bodies ≤ 120 lines (`tests/test_plugin_files.py`).
- Run tests with `uv run pytest`; lint with `uv run ruff check . && uv run ruff format --check .`.

## Review Focus

- A dependency cycle among units must not hang or crash the effective-rank computation (it shares the traversal with `dependents_count`). Test in Task 1.
- An item carrying two priority labels sorts by the higher one and is reported by `crew labels check`. Tests in Tasks 1 and 2.
- A PR labeled lower than its issue (or unlabeled) sorts at the issue's effective priority. Test in Task 1.
- A dependency on a closed or unknown issue number is ignored (no KeyError). Test in Task 1.
- A pitch section `## Priority` holding `**Must**` or `Must.` should be accepted (strip `*_` and a trailing period, like requirements' `strip("`*_ ")`). Test in Task 3.

---

### Task 1: Priority labels and ordering

**Files:**
- Modify: `src/crew/labels.py` (the `LABELS` list, "Priority and kind" group; new constants)
- Modify: `src/crew/graph.py` (remove `DO_FIRST`; `priority_key`, `rough_order`, `ready_report`; new functions)
- Modify: `src/crew/inbox.py` (`InboxItem`, `owner_inbox`)
- Modify: `src/crew/cli.py:335` (inbox line)
- Test: `tests/test_graph.py`, `tests/test_minors.py`, `tests/test_inbox.py`, `tests/test_github.py`

**Interfaces:**
- Produces in `crew.labels`:
  - `PRIORITY_LABELS: tuple[str, ...] = ("crew:must", "crew:should", "crew:later")`
  - `DEFAULT_PRIORITY = "crew:should"`
- Produces in `crew.graph`:
  - `own_rank(labels: set[str]) -> int`: lowest index in `PRIORITY_LABELS` among `labels`; `1` when none.
  - `effective_ranks(units: dict[int, Unit]) -> dict[int, int]`: per open unit, `min` of its `own_rank` and the `own_rank` of every open unit depending on it directly or indirectly.
  - `rank_name(rank: int) -> str`: `"must"`, `"should"`, `"later"`.
  - `priority_key(rank: int, blocks: int, created_at: str, number: int) -> tuple` returning `(rank, -blocks, created_at or "~", number)`.
- Produces in `crew.inbox`: `InboxItem` field `do_first: bool` replaced by `priority: str` (a `rank_name`), same position (last).

- [x] **Step 1: Write the failing tests**

In `tests/test_github.py::test_label_set` replace `"crew:do-first"` with `"crew:must", "crew:should", "crew:later"` (same position).

In `tests/test_graph.py`:

```python
def test_own_rank():
    assert own_rank({"crew:later"}) == 2
    assert own_rank(set()) == 1
    assert own_rank({"crew:later", "crew:must"}) == 0


def test_effective_ranks_raise_blockers():
    units = units_of(
        issue(1, labels=["crew:later"]),
        issue(2, labels=["crew:later"], deps=[1]),
        issue(3, labels=["crew:must"], deps=[2]),
        issue(4, labels=["crew:later"], deps=[99]),
        issue(5, labels=["crew:later"], deps=[6]),
        issue(6, labels=["crew:should"], deps=[5]),
    )
    assert effective_ranks(units) == {1: 0, 2: 0, 3: 0, 4: 2, 5: 1, 6: 1}
```

Rewrite `test_next_ready_order_and_cycles`: issue 3 labels `["crew:ready", "crew:must"]`, issue 1 and 2 unlabeled; still expects `[3, 1, 2]`. Add issue 7 `labels=["crew:ready", "crew:later"], owns=["g/"], created="2025-01-01T00:00:00Z"` and expect `[3, 1, 2, 7]` (oldest but `later`).

In `tests/test_minors.py::test_rough_order`: issue 3 gets `"crew:must"` instead of `"crew:do-first"`; still `[3, 1, 2, 4]`.

In `tests/test_inbox.py`: rename `test_inbox_order_do_first_then_blocks` → `test_inbox_order_priority_then_blocks`; issue 3 gets `"crew:must"`; issue 2 gets `"crew:later"`; expected tuples use `i.priority`:

```python
    assert [(i.number, i.ask, i.blocks, i.priority) for i in items] == [
        (3, "proposal", 0, "must"),
        (1, "decision", 2, "should"),
        (6, "accept", 0, "should"),
        (2, "stuck", 0, "later"),
    ]
```

`test_pr_maps_to_linked_issue` expects `InboxItem(..., "accept", 1, "should")`. New test:

```python
def test_pr_takes_its_issues_effective_priority():
    units = build_units([issue(1, labels=["crew:later"]), issue(2, labels=["crew:must"], deps=[1])])
    items = owner_inbox(units, [pr(10, labels=["crew:owner-accept", "crew:later"], closes=[1])])
    assert [i.priority for i in items] == ["must"]
```

The CLI assertion at `tests/test_inbox.py:106` becomes
`"#1 [decision] should, blocks 1 — Unit 1 — https://github.com/example/app/issues/1"`.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph.py tests/test_minors.py tests/test_inbox.py tests/test_github.py -q`
Expected: FAIL (import errors for `own_rank`, `effective_ranks`; label set mismatch).

- [x] **Step 3: Implement**

- `labels.py`: replace the `crew:do-first` `Label` with three labels (descriptions from the spec's table, each ending with `.`; colors builder's choice, one hue, strongest for must); add the two constants.
- `graph.py`: remove `DO_FIRST`; add the functions above. `effective_ranks` reuses `_dependents` and the same seen-set traversal as `dependents_count` (cycle-safe). `rough_order` and `ready_report` sort with `priority_key(ranks[u.number], counts[u.number], ...)`.
- `inbox.py`: compute `ranks = effective_ranks(units)`. A unit's item uses `ranks[unit.number]`. A PR's item uses `min(own_rank(labels), ranks[number])` when its linked number is a unit, else `own_rank(labels)`. Sort with the rank; store `rank_name(rank)` in `InboxItem.priority`. Update the `owner_inbox` docstring order line.
- `cli.py:335`: `print(f"  #{item.number} [{item.ask}] {item.priority}, blocks {item.blocks} — {item.title} — {item.url}")`.

- [x] **Step 4: Run the whole suite and lint**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass; `grep -rn "do_first\|DO_FIRST\|do-first" src tests` prints nothing.

- [x] **Step 5: Commit** (with this plan's checkbox updates)

```bash
git add src/crew tests docs/superpowers/plans/2026-11-09-issue-priority.md
git commit -m "feat: order work by must/should/later priority instead of do-first"
```

### Task 2: Two priority labels are a label problem

**Files:**
- Modify: `src/crew/labels.py` (`label_problems` and its docstring)
- Test: `tests/test_labels.py`

**Interfaces:**
- Consumes: `PRIORITY_LABELS` (Task 1).

- [x] **Step 1: Write the failing test**

```python
def test_label_problems_two_priorities():
    problems = label_problems(
        open_issues=[issue(3, labels=["crew:must"]), issue(4, labels=["crew:must", "crew:later"])],
        closed_issues=[],
        open_prs=[pr(9, labels=["crew:should", "crew:later"])],
        merged_prs=[],
    )
    assert problems == [
        LabelProblem(4, "has more than one priority label: crew:must, crew:later", ()),
        LabelProblem(9, "has more than one priority label: crew:should, crew:later", ()),
    ]
```

(Use the `issue`/`pr` helpers already used in `tests/test_labels.py`.) Also extend `test_label_problems_idea_with_work_or_proposal_label` with `issue(5, labels=["crew:idea", "crew:later"])` producing no problem.

- [x] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_labels.py -q` — Expected: FAIL on the new test.

- [x] **Step 3: Implement**

In `label_problems`, right after the "more than one state label" loop (same open issues + PRs, by number), emit the message above with names in `PRIORITY_LABELS` order, `fix_remove=()`.

- [x] **Step 4: Run and lint** — `uv run pytest -q && uv run ruff check .` — Expected: pass.

- [x] **Step 5: Commit**

```bash
git add src/crew/labels.py tests/test_labels.py docs/superpowers/plans/2026-11-09-issue-priority.md
git commit -m "feat(labels): report items with more than one priority label"
```

### Task 3: Pitch `## Priority` section

**Files:**
- Modify: `src/crew/docs/pitches.py`
- Modify: `src/crew/templates/docs/pitches/TEMPLATE.md`, `tests/fixtures/project/docs/pitches/TEMPLATE.md` (kept identical), `tests/fixtures/pitches/0001-shopping-list.md`, `tests/fixtures/project/docs/pitches/0001-shopping-list.md`
- Modify: `plugins/crew/skills/pitch/SKILL.md` (the section list in step 2)
- Test: `tests/docs/test_pitches.py`

**Interfaces:**
- Consumes: `PRIORITIES` from `crew.docs.requirements`.

- [x] **Step 1: Write the failing tests**

Fixtures: add after `## Appetite`'s paragraph:

```markdown
## Priority

Must
```

Template: the same heading with `<Must, Should or Later: the highest priority of the requirements it serves.>`.

```python
def test_pitch_missing_priority_is_a_warning(tmp_path):
    path = variant(tmp_path, "## Priority\n\nMust\n\n", "")
    findings = parse_pitch(path)
    assert [(f.code, f.severity) for f in findings] == [("PITCH-PRIORITY", "warning")]


def test_pitch_bad_priority(tmp_path):
    path = variant(tmp_path, "\nMust\n", "\nUrgent\n")
    findings = parse_pitch(path)
    assert [(f.code, f.severity) for f in findings] == [("PITCH-PRIORITY", "error")]


def test_pitch_priority_tolerates_emphasis(tmp_path):
    assert parse_pitch(variant(tmp_path, "\nMust\n", "\n**Should.**\n")) == []
```

Line numbers in existing tests (`test_pitch_appetite_without_percent` expects line 7) stay valid only if the section is placed after Appetite's paragraph; keep it there.

- [x] **Step 2: Run to verify they fail** — `uv run pytest tests/docs/test_pitches.py -q` — Expected: FAIL.

- [x] **Step 3: Implement**

`Priority` is *not* added to `SECTIONS`. After the section loop: if `"priority"` is missing → `Finding(path, 1, "PITCH-PRIORITY", "missing `## Priority` section (Must, Should or Later)", severity="warning")`. If present, take the first non-blank line, `strip("`*_ .")`; if not in `PRIORITIES` → error at the heading line: ``priority `<value>` is not one of Must, Should, Later``. Update the module docstring. Add `## Priority` to the pitch skill's section list.

- [x] **Step 4: Run the whole suite** — `uv run pytest -q` (the `check-docs` CLI tests over `tests/fixtures/project` must stay clean) — Expected: pass.

- [x] **Step 5: Commit**

```bash
git add src/crew/docs/pitches.py src/crew/templates tests plugins/crew/skills/pitch/SKILL.md docs/superpowers/plans/2026-11-09-issue-priority.md
git commit -m "feat(pitches): record the pitch's priority"
```

### Task 4: Plugin texts and workflow docs

**Files:**
- Modify: `plugins/crew/agents/{lead,architect,designer,implementer,reviewer}.md`
- Modify: `plugins/crew/skills/{kickoff,ideas,pitch,relay,implement,inbox,refine}/SKILL.md`
- Modify: `docs/workflow.md`; `README.md` only if it mentions do-first or the order (currently it does not)
- Test: `tests/test_plugin_files.py`

- [x] **Step 1: Write the failing tests**

```python
PRIORITY_RULE_PHRASES = ("crew:must", "crew:should", "crew:later", "the issue you are working on")


@pytest.mark.parametrize("name", AGENTS)
def test_agent_brief_sets_priority(name):
    text = (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")
    rule = text[text.index("**Priority:**") :].split("\n- ")[0]
    for phrase in PRIORITY_RULE_PHRASES:
        assert phrase in rule, f"{name}.md priority rule lacks {phrase!r}"


def test_no_do_first_left():
    for path in [*PLUGIN.rglob("*.md"), PLUGIN.parent.parent / "docs" / "workflow.md"]:
        assert "do-first" not in path.read_text(encoding="utf-8"), path


@pytest.mark.parametrize("name", ["kickoff", "ideas", "pitch", "relay", "implement", "inbox"])
def test_filing_skills_name_a_priority(name):
    assert "crew:must" in skill_text(name) or "crew:later" in skill_text(name)
```

- [x] **Step 2: Run to verify they fail** — `uv run pytest tests/test_plugin_files.py -q` — Expected: FAIL.

- [x] **Step 3: Edit the texts**

- Every agent brief, in `## Rules` right after **Discovered work**, a bullet starting `**Priority:**` with the spec's shared rule (the quoted block under "Where issues and PRs are filed"). In **Discovered work**, "with no other crew label" → "with `crew:later` and no other crew label".
- `lead.md`: line 42 → "When the owner changes how important something is, relabel it (`crew:must`, `crew:should`, `crew:later`). When the owner asks what to do next, suggest the highest-priority work first." Retrospective proposal (line 61) gets `crew:should`.
- `architect.md`: units from a pitch take the pitch's `## Priority`, or higher if a requirement in the spec delta says so; decision PRs take the priority of the issue they answer. `designer.md`: decision PRs likewise.
- `kickoff`: file one `crew:idea` per epic — `crew:must` in the MVP cut, `crew:later` outside it; relabel when the cut changes; first decision issues and the baseline PR `crew:must`.
- `ideas`: park = "`crew:idea` and one priority label, no other crew label"; derive from linked requirements, else suggest with a one-line reason and let the owner confirm. Go through = list by priority (`crew:must` first, then oldest) and suggest the top one; the owner picks.
- `pitch`: the pitch PR and the `## Priority` section take the idea's priority, else suggest and confirm.
- `relay`, `implement` (later-feedback idea): `crew:later` unless the owner said otherwise. `implement`: the PR copies the unit's priority label.
- `inbox`: order wording "priority, then how much work each item blocks"; a follow-up `crew:rough` takes the merged unit's priority.
- `refine`: order wording "priority, then the ones that block the most other work, then …".
- `docs/workflow.md`: lead role line (line 25: "marks do-first units" → "sets priorities"), inbox order (line 39), pick order (line 100), label table (line 124: drop do-first, add the three labels), the parked-ideas wording, and a short "Priority" paragraph with the shared rule and the effective-priority rule.

- [x] **Step 4: Run the suite** — `uv run pytest -q` — Expected: pass (including body-length limits).

- [x] **Step 5: Commit**

```bash
git add plugins docs/workflow.md tests/test_plugin_files.py docs/superpowers/plans/2026-11-09-issue-priority.md
git commit -m "feat(plugin): set a priority on every issue and PR the crew files"
```
