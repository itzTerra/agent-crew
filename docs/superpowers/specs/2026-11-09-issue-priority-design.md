# Issue and PR priority

## Why

The lead should suggest the most important work first, but nothing on an issue says how
important it is. In a real project the twelve MVP epics from the kickoff and
two small side ideas ("suggest-a-feature button", "translated interface") all carry only
`crew:idea`, so they look equally important. The requirements already rank themselves
(`Must`, `Should`, `Later` in the requirement tables; one real baseline has 196 `Must`
and 5 `Should` rows), but the issues and PRs built from them lose that ranking.

The only ordering signal today is `crew:do-first`, which the owner does not use.

## Goals

- Every issue and PR carries a priority on the same scale as the requirements.
- Priority comes primarily from the requirements an issue serves; otherwise the lead suggests one
  and the owner confirms it, or (with no owner around) a fixed rule sets it.
- Priority drives every order the crew uses: the inbox, the refine order, the pick order, and
  which parked idea the lead suggests first.
- `crew:do-first` is removed; priority replaces it.

## Non-goals and anti-goals

- No one-time backfill pass in the framework. Existing projects label their open issues by asking
  their lead (instructions are given to the owner separately, not shipped).
- No priority prompts during an unattended `crew run`: agents never wait for the owner to set a
  priority.
- No finer scale (no numbers, no P0–P3).
- Failure even if it works: a `Later` item that blocks `Must` work starves; the owner gets asked
  to confirm priorities for things agents file on their own; the inbox fills with priority
  questions.

This reverses one non-goal of the parked-ideas design ("no automatic prioritization of ideas"):
ideas now carry a priority, but promotion stays manual.

## Decided with the owner

1. **Priority drives what the lead suggests first** and replaces `crew:do-first` everywhere.
2. **Derived from requirements first.** An issue whose body links requirement IDs (`REQ-…`) takes
   the highest priority among them. Kickoff epics are the exception, because the baseline's epics
   are prose and do not cite requirement IDs: the MVP cut is the requirements' priority call, so
   every epic in the MVP cut is `Must`, and every epic outside it is `Later` (see the kickoff
   spot below). The baseline format does not change.
3. **Otherwise suggested and confirmed** when the owner is present: the lead (in `crew:ideas`,
   `crew:pitch`, `crew:relay`, `crew:inbox`, `crew:kickoff`) suggests a priority with a one-line
   reason and the owner confirms or changes it before the issue is filed.
4. **Agents filing without the owner** (discovered work, during a run or any session):
   - a work issue (`crew:rough`, `crew:owner-proposal`, `crew:owner-decision`) gets the same
     priority as the issue the agent was working on;
   - a parked idea (`crew:idea`) gets `Later`.
   No confirmation is asked; the owner can relabel whenever they see it.
5. **No backfill command or pass** in the framework.

## Design

### The scale and labels

Three labels, one per requirement priority, defined in `src/crew/labels.py` and created by
`crew labels sync`:

| Label | Meaning |
|---|---|
| `crew:must` | Needed for the current cut (MVP or the bet it serves) |
| `crew:should` | Wanted, but the cut works without it |
| `crew:later` | A nice-to-have or a later idea |

They replace the `crew:do-first` entry in the "Priority and kind" group. An issue or PR carries at
most one of them. Colors are the builder's choice (one hue, strongest for `must`).

*My call:* label names `crew:must` / `crew:should` / `crew:later`, matching `PRIORITIES` in
`src/crew/docs/requirements.py` (reuse that tuple or keep the two in step).

`crew labels sync` does not delete labels today and keeps not doing so; the stale `crew:do-first`
label in existing repos is harmless and the owner can delete it by hand.

### Effective priority and ordering (code)

`priority_key` in `src/crew/graph.py` changes from `(not do_first, -blocks, created_at, number)`
to `(rank, -blocks, created_at, number)`, where `rank` is 0 for `must`, 1 for `should`, 2 for
`later`, from the item's **effective priority**:

- the item's own priority label; an item with none counts as `should`;
- raised to the highest effective priority of any open issue that depends on it, directly or
  indirectly (the same dependency graph `dependents_count` uses). So a `later` unit blocking a
  `must` unit sorts as `must`, and an owner decision that blocks `must` work sorts as `must`;
- for a PR, raised to its linked issue's effective priority (as `do_first` is today in
  `src/crew/inbox.py`).

The effective priority is computed, never written back to labels.

Users of `priority_key`: `owner_inbox` (`src/crew/inbox.py`), `rough_order` and `ready_report`
(`src/crew/graph.py`). `InboxItem.do_first` becomes the effective priority; wherever the CLI shows
the do-first marker (`crew inbox`, `crew next`, the supervisor's views), it shows the priority
instead. `DO_FIRST` is removed.

*My call:* `label_problems` (`src/crew/labels.py`) reports an open issue or PR carrying more than
one priority label, not auto-fixable. A missing label is not a problem (it counts as `should`).

Tests: the existing do-first tests (`tests/test_inbox.py`, `tests/test_graph.py`,
`tests/test_minors.py`, `tests/test_github.py`) are rewritten for priority, plus tests for the
dependency raise, the unlabeled default, PRs taking their issue's priority, and the
two-priority-labels problem.

### Where issues and PRs are filed (plugin texts)

Each spot below says which priority label to add. One shared rule goes into every agent brief
next to the "Discovered work" rule, and into `docs/workflow.md`:

> Every issue and PR you file carries one priority label (`crew:must`, `crew:should`,
> `crew:later`). Take it from the requirements it serves (the highest one). Otherwise: with the
> owner present, suggest one with a one-line reason and let them confirm; without the owner, a
> work issue takes the priority of the issue you are working on and a parked idea gets
> `crew:later`. A PR takes the priority of the issue it closes or comes from.

Spots:

- **`crew:kickoff`**: one `crew:idea` issue per epic, not only the MVP ones: an epic in the MVP
  cut gets `crew:must`, an epic outside it gets `crew:later`. If the MVP cut changes later, the
  lead relabels the affected epic ideas. The first owner-decision issues get the priority of the work they block (normally
  `crew:must`). The baseline PR gets `crew:must`.
- **`crew:ideas` (park)**: the lead derives or suggests and confirms, per idea. A parked idea is
  now "labeled `crew:idea` and a priority label, no other crew label" (update the skill text, the
  parked-ideas wording in `docs/workflow.md`, and the "with no other crew label" phrase in every
  agent brief).
- **`crew:ideas` (go through)**: list ideas by priority (`must` first, then oldest) and suggest
  the top one; the owner still picks.
- **`crew:pitch`**: the pitch PR takes the idea's priority when it came from one; otherwise the
  lead suggests and confirms. The pitch document records it (below).
- **Architect, refining a pitch into units**: each unit takes the pitch's priority, or higher if
  the requirements in its spec delta say so.
- **`crew:relay` and `crew:implement`** (owner feedback asking for something for later): the new
  `crew:idea` issue gets `crew:later` unless the owner said otherwise in the feedback.
- **`crew:implement`**: the PR copies the unit's priority label.
- **`crew:inbox`**: a follow-up `crew:rough` unit filed after a merge takes the merged unit's
  priority; ordering text says "priority, then how much work each item blocks".
- **Architect and designer decision PRs**: take the priority of the issue they answer.
- **Lead's retrospective proposal**: `crew:should`.
- **Discovered work** (all five agent briefs): the shared rule above.
- **`lead.md`**: "When the owner says a unit comes first, add `crew:do-first`" becomes "When the
  owner changes how important something is, relabel it". The lead suggests the highest-priority
  work first when the owner asks what to do next.
- **`crew:refine`**: the refine order text says priority instead of do-first.
- **`docs/workflow.md`**: the inbox order, the pick order, the label table (`crew:do-first` out,
  the three priority labels in), the lead's role line ("marks do-first units").
- **README**: only if it mentions do-first or the ordering.

### The pitch document

*My call:* the pitch template (`src/crew/templates/docs/pitches/TEMPLATE.md`) gets a
`## Priority` section holding one of `Must`, `Should`, `Later`, and `crew check-docs`
(`src/crew/docs/pitches.py`) checks it. The architect reads it when refining, after the pitch PR
(and its label) is merged.

*My call:* a missing `## Priority` section is a **warning** (`Finding(severity="warning")`), so
upgrading crew does not break CI in existing projects or send agents in a run after pitches they
don't own. A section that is present but holds anything other than `Must`, `Should` or `Later` is
an error.

### Issue and PR templates

No new section in the unit or PR templates: the label is the single source. The unit template's
default label list stays `crew:rough` (the filer adds the priority).

## Left to the builder

- Label colors and descriptions.
- How the priority shows in CLI output (a word, a short tag).
- Exact wording of the skill and brief edits, as long as the rules above hold.
- Whether effective priority is computed in `graph.py` or a small helper next to
  `dependents_count`.
