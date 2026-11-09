# Parked Ideas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `crew:idea` label and a `crew:ideas` lead skill so ideas can be parked as issues without the pitch challenge, kept out of the owner's inbox and never picked as work.

**Architecture:** One new label in `crew.labels` with a consistency guard in `label_problems`; `crew inbox` prints only a count. Everything else is prompt text: a new skill, the "Discovered work" rule in every agent brief, and small edits to the pitch, inbox, kickoff, implement and relay skills, the lead brief, `docs/workflow.md` and the README.

**Tech Stack:** Python 3 (stdlib), pytest, uv; Claude Code plugin Markdown (agents, skills).

**Spec:** `docs/superpowers/specs/2026-11-09-parked-ideas-design.md`

## Global Constraints

- Label name `crew:idea`; it never carries a flow label and never counts as waiting on the owner.
- Discovered work: fix/tidy → `crew:rough`; changes agreed behavior, or blocks / puts the current bet at risk → `crew:owner-proposal`; any other scope-adding or "might be nice" find → `crew:idea`.
- A promoted idea's pitch PR body says `From idea #N`, never `Closes #N`; the lead closes the idea issue once the pitch PR is open, and reopens it with `crew:idea` only if the owner declines the bet as "not now".
- Inbox prints `Parked ideas: N` after the "Merged without you" block, omitted when N is 0, no list.
- Skill bodies stay ≤ 120 lines (`MAX_SKILL_BODY_LINES`).
- Docs style: short plain sentences, matching sibling entries; no history notes.
- Commits: conventional (`feat:`, `test:` …), no AI attribution; check off each plan box in the commit of its task.

## Review Focus

1. An issue labeled both `crew:idea` and `crew:rough` (an agent mislabels): it must not silently become work → `crew labels check` reports it (Task 1 test).
2. An idea-only issue during a run with free slots and nothing ready: the planner must not refine or implement it (Task 1 planner test).
3. An idea that also has `crew:owner-proposal`: the owner would see it both as a proposal and as a parked idea → the guard reports it (Task 1 test).
4. An inbox with zero ideas: no `Parked ideas` line at all (Task 2 test).
5. A closed idea issue: not counted (only open issues reach `build_units`; Task 2 test passes a closed one through the fake and asserts the count).

---

### Task 1: The `crew:idea` label and its guard

**Files:**
- Modify: `src/crew/labels.py` (`LABELS`, new `IDEA` constant, `label_problems`)
- Test: `tests/test_labels.py`, `tests/supervisor/test_planner.py`

**Interfaces:**
- Produces: `crew.labels.IDEA = "crew:idea"`; `label_problems` also returns `LabelProblem(n, "parked idea also has <labels>", ())` for open issues with `crew:idea` plus any flow label or `crew:owner-proposal` (labels listed in `FLOW` order, then `crew:owner-proposal`, comma-separated).

- [x] **Step 1: Write the failing tests**

In `tests/test_labels.py`:

```python
def test_idea_label_exists():
    assert IDEA == "crew:idea"
    assert IDEA in {label.name for label in LABELS}
    assert IDEA not in FLOW


def test_label_problems_idea_with_work_or_proposal_label():
    problems = label_problems(
        open_issues=[
            issue(3, labels=["crew:idea"]),
            issue(4, labels=["crew:idea", "crew:rough"]),
            issue(6, labels=["crew:idea", "crew:owner-proposal"]),
        ],
        closed_issues=[], open_prs=[], merged_prs=[],
    )
    assert problems == [
        LabelProblem(4, "parked idea also has crew:rough", ()),
        LabelProblem(6, "parked idea also has crew:owner-proposal", ()),
    ]
```

In `tests/supervisor/test_planner.py`, next to `test_refine_ahead_keeps_one_refiner`:

```python
def test_parked_idea_is_never_picked():
    issues = [issue(1, labels=["crew:idea"], owns=["a/"])]
    result = make_plan(snap(issues), free_slots=3)
    assert result.actions == []
```

- [x] **Step 2: Run them and see the label tests fail**

Run: `uv run pytest tests/test_labels.py tests/supervisor/test_planner.py -k "idea" -v`
Expected: the two label tests FAIL (ImportError / missing problem); the planner test PASSES already (it pins existing behavior).

- [x] **Step 3: Implement**

In `src/crew/labels.py`: add `IDEA = "crew:idea"`; add `Label(IDEA, "ededed", "A parked idea: not a bet, not work, not waiting on the owner.")` to `LABELS` under a new `# Parked.` comment after the owner asks. In `label_problems`, after the "more than one state label" pass, add a pass over open issues by number for the idea conflict; update the docstring's "In this order" sentence to include it.

- [x] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add src/crew/labels.py tests/test_labels.py tests/supervisor/test_planner.py docs/superpowers/plans/2026-11-09-parked-ideas.md
git commit -m "feat(labels): add crew:idea for parked ideas"
```

### Task 2: Parked-ideas count in `crew inbox`

**Files:**
- Modify: `src/crew/inbox.py`, `src/crew/cli.py` (`_cmd_inbox`)
- Test: `tests/test_inbox.py`

**Interfaces:**
- Consumes: `crew.labels.IDEA` (Task 1).
- Produces: `crew.inbox.parked_ideas(units: dict[int, Unit]) -> int`.

- [x] **Step 1: Write the failing tests**

```python
def test_parked_ideas_counts_open_ideas_only():
    closed_idea = issue(3, labels=["crew:idea"])
    closed_idea["state"] = "CLOSED"
    units = build_units([issue(1, labels=["crew:idea"]), issue(2), closed_idea])
    assert parked_ideas(units) == 1
    assert owner_inbox(units, []) == []


def test_inbox_cli_parked_ideas_line(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    fake = FakeGitHub(issues=[issue(1, labels=["crew:idea"]), issue(2, labels=["crew:idea"])],
                      open_prs=[], merged_prs=[])
    monkeypatch.setattr("crew.cli.make_github", lambda repo: fake)
    assert main(["inbox", "--root", str(root), "--peek"]) == 0
    out = capsys.readouterr().out
    assert "Parked ideas: 2" in out
    assert out.index("Merged without you") < out.index("Parked ideas: 2")
    assert "#1" not in out

    fake.issues = [issue(2)]
    assert main(["inbox", "--root", str(root), "--peek"]) == 0
    assert "Parked ideas" not in capsys.readouterr().out
```

- [x] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_inbox.py -k parked -v`
Expected: FAIL (ImportError `parked_ideas`).

- [x] **Step 3: Implement** `parked_ideas` in `src/crew/inbox.py`, and in `_cmd_inbox` print a blank line plus `Parked ideas: {n}` right after the merged-without-you block, only when `n > 0`.

- [x] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add src/crew/inbox.py src/crew/cli.py tests/test_inbox.py docs/superpowers/plans/2026-11-09-parked-ideas.md
git commit -m "feat(inbox): show the number of parked ideas"
```

### Task 3: The discovered-work rule in every agent brief

**Files:**
- Modify: `plugins/crew/agents/{lead,architect,designer,implementer,reviewer}.md` (the "**Discovered work:**" bullet), `docs/workflow.md` ("Discovered work" paragraph and the Labels table)
- Test: `tests/test_plugin_files.py`

- [x] **Step 1: Write the failing test**

Add `"crew:idea"` to the phrases in `test_agent_brief_covers_shared_rules`, and:

```python
@pytest.mark.parametrize("name", AGENTS)
def test_discovered_work_parks_ideas(name):
    text = (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")
    rule = text[text.index("**Discovered work:**"):].split("\n- ")[0]
    for phrase in ("crew:rough", "crew:owner-proposal", "crew:idea", "agreed behavior", "current bet"):
        assert phrase in rule, f"{name}.md discovered-work rule lacks {phrase!r}"
```

- [x] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_plugin_files.py -k "discovered or shared_rules" -v`
Expected: FAIL for all five agents.

- [x] **Step 3: Rewrite the bullet identically in all five briefs:**

```
- **Discovered work:** a bug or technical debt that only fixes or tidies existing behavior is
  filed as a new issue labeled `crew:rough`. A find that changes agreed behavior, or a gap that
  blocks the current bet or puts it at risk, is filed as `crew:owner-proposal`. Any other idea
  that would add scope is filed as a short issue labeled `crew:idea`, with no other crew label.
  Don't fold any of them into the current unit.
```

In `docs/workflow.md`, rewrite the "Discovered work" paragraph to the same three-way rule, and add a table row after `crew:owner-proposal`: `` | `crew:idea` | A parked idea: not a bet, not work, not waiting on the owner | ``.

- [x] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add plugins/crew/agents docs/workflow.md tests/test_plugin_files.py docs/superpowers/plans/2026-11-09-parked-ideas.md
git commit -m "feat(agents): park speculative discovered work as crew:idea"
```

### Task 4: The `crew:ideas` skill and the paths in and out

**Files:**
- Create: `plugins/crew/skills/ideas/SKILL.md`
- Modify: `plugins/crew/skills/{pitch,inbox,kickoff,implement,relay}/SKILL.md`, `plugins/crew/agents/lead.md`, `docs/workflow.md` (Roles row for the lead, "The owner's session", "Pitches", "Kickoff"), `README.md` (skills list, day-to-day use)
- Test: `tests/test_plugin_files.py`

- [x] **Step 1: Write the failing tests**

Add `"ideas"` to `SKILLS`, and:

```python
def test_ideas_skill_files_and_promotes():
    text = skill_text("ideas")
    for phrase in ("crew:idea", "gh issue list", "full URL", "crew:pitch", "quoted"):
        assert phrase in text


def test_promoted_idea_is_not_closed_by_the_pitch_pr():
    for text in (skill_text("pitch"), skill_text("ideas")):
        assert "From idea #N" in text
    assert "Closes #N" not in skill_text("pitch")


def test_feedback_for_later_becomes_an_idea():
    for text in (skill_text("implement"), skill_text("relay")):
        assert "crew:idea" in text


def test_kickoff_parks_mvp_epics_and_inbox_mentions_ideas():
    assert "crew:idea" in skill_text("kickoff")
    assert "Parked ideas" in skill_text("inbox")
    lead = (PLUGIN / "agents" / "lead.md").read_text(encoding="utf-8")
    assert "crew:ideas" in lead
```

- [x] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_plugin_files.py -v`
Expected: FAIL (missing `ideas` skill and phrases).

- [x] **Step 3: Write `plugins/crew/skills/ideas/SKILL.md`** (frontmatter `name: ideas`; description: park one or many ideas as `crew:idea` issues without the pitch challenge, or go through the parked ideas with the owner; run by the lead). Two sections:
  - **Park:** for each idea the owner gives, search open issues (`gh issue list --state open --search "<words>"`); if one covers it, comment the owner's words there; else file an issue labeled only `crew:idea` with a short title, the owner's words quoted as theirs, and where it came from. No challenge, no questions beyond what's needed to tell ideas apart. Report each filed or commented issue with its full URL.
  - **Go through:** list open `crew:idea` issues (`gh issue list --label crew:idea`), the owner picks one, run `crew:pitch` on it. Dropped → close with the owner's reason quoted. Survives → the pitch PR body says `From idea #N` (never `Closes #N`: that would make the run treat the idea as the PR's unit); once the PR is open, close the idea issue with a comment linking it. Declined bet: "not now" → reopen the idea and add `crew:idea`; "no" → leave it closed.

- [x] **Step 4: Edit the other files**
  - `pitch`: description also names a `crew:idea` issue as a starting point; in "3. Propose the bet", add the `From idea #N` / close-the-idea rule and the declined-bet rule (point to `crew:ideas`).
  - `inbox`: after step 4, if `crew inbox` printed `Parked ideas: N`, mention it and offer `crew:ideas` to go through them.
  - `kickoff`: after step 2, file one `crew:idea` issue per MVP epic, each naming its epic and linking the baseline PR; if the MVP cut changes in that PR's review, adjust the ideas while relaying the feedback.
  - `implement` (changes-requested paragraph) and `relay`: an owner comment that asks for something for later or outside the unit is filed as a `crew:idea` issue linking the PR, the reply on the PR gives its URL; if nothing else needs changing, say so and move the PR on as usual.
  - `lead.md`: name `crew:ideas` where the lead's skills are listed (pitching ideas), and the same "for later" rule for feedback on PRs the lead owns.
  - `docs/workflow.md`: the lead's Roles row mentions parking ideas; "The owner's session" step 4 becomes "pitches or parks ideas"; "Pitches" gains a short paragraph on parked ideas and promotion; "Kickoff" mentions the epic ideas.
  - `README.md`: add `crew:ideas` to the skills list; in day-to-day use, add parking ideas next to "Pitch ideas".

- [x] **Step 5: Run the whole suite and the docs check on the repo's own docs**

Run: `uv run pytest -q`
Expected: all pass, including the skill body length limit.

- [x] **Step 6: Commit**

```bash
git add plugins/crew docs/workflow.md README.md tests/test_plugin_files.py docs/superpowers/plans/2026-11-09-parked-ideas.md
git commit -m "feat(lead): add crew:ideas to park ideas and promote them to pitches"
```
