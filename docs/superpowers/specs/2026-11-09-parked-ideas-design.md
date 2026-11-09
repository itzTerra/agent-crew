# Parked ideas

## Why

The owner often has ideas they want recorded but not worked on yet: several at once when talking
to the lead, or in passing while reviewing a PR ("the mockup has no light/dark switch and no
language selector; I want two themes and more languages, but not now"). Today the only place for
them is `crew:owner-proposal`, which means "waiting for the owner's pitch challenge" and shows in
`crew inbox` as waiting on the owner. Twenty parked ideas there would bury the real decisions.
Agents have the same problem: the "Discovered work" rule sends every scope-adding find to
`crew:owner-proposal`, however speculative.

Separately, kickoff writes the epics and the MVP cut but nothing turns them into pitches, so the
owner would have to pitch each epic by hand.

## Goals

- Record one or many ideas without the pitch challenge, cheaply, in a place they can be found
  again.
- Let the owner park ideas from a PR comment; the agent handling the feedback files them.
- Keep the inbox for what actually waits on the owner.
- Promote a parked idea to a pitch later, through the normal `crew:pitch` challenge.
- Have kickoff leave the MVP epics behind as parked ideas.

## Non-goals and anti-goals

- No automatic promotion, reminders or prioritization of ideas.
- No pitch files or PRs for parked ideas; the pitch PR appears only on promotion. (Considered and
  rejected by the owner: a draft pitch PR per idea clutters the PR list and makes builders open PRs.)
- Failure even if it works: an idea is ever picked up as a unit (refined, implemented), or ideas
  show up as items waiting on the owner.

## Decided with the owner

1. **An idea is a GitHub issue labeled `crew:idea`.** Not a bet, not work, not waiting on the
   owner. It carries no flow label.
2. **Ways in:**
   - **Lead, new skill `crew:ideas`** (`plugins/crew/skills/ideas/SKILL.md`): the owner gives one
     idea or a list. The lead files one short issue per idea with no challenge and no
     brainstorming: a title, the owner's words (quoted as theirs), and where it came from.
     Before filing, it checks open issues; if one already covers the idea, it comments there
     instead. Then it reports what it filed, with full URLs.
   - **PR feedback:** when the owner's PR comment asks for something "for later" or otherwise
     outside the unit, the agent handling the feedback (implementer or designer, in the
     `crew:implement` changes-requested step) files each such item as a `crew:idea` issue that
     links to the PR, and replies on the PR with the issue URLs. If nothing else in the comment
     needs changing, it says so and moves the PR on through the normal round. A round with
     nothing to fix is acceptable to the owner; no change to `crew run`'s feedback handling.
   - **Kickoff:** after the baseline, the lead files one `crew:idea` issue per MVP epic, linking
     the baseline.
   - **Agents' discovered work:** see 4.
3. **Way out:** when the owner says "let's go through the ideas", the lead lists open
   `crew:idea` issues; the owner picks one; the lead runs `crew:pitch` on it. If the owner
   drops it, the lead closes the issue with the owner's reason quoted. If it survives, see
   "Promotion" below.
4. **Discovered work rule** (in every agent brief, and `docs/workflow.md`): bugs and debt that
   only fix or tidy existing behavior stay `crew:rough`. A find that changes agreed behavior,
   or a gap that blocks the current bet or puts it at risk, is `crew:owner-proposal`. Any other
   scope-adding or "might be nice" find is filed as `crew:idea`. Agents may file ideas on their
   own.
5. The weekly retrospective stays a `crew:owner-proposal`.

## The builder's own calls (made in design, can be revisited)

- **Inbox:** `crew inbox` prints one line after "Merged without you", e.g. `Parked ideas: 12`
  (omitted when there are none), with no list. The inbox skill mentions it and offers
  `crew:ideas` to go through them.
- **Guard:** `crew labels check` reports an open issue that carries `crew:idea` together with a
  flow label or `crew:owner-proposal` (not auto-fixable). The planner and `crew next` already
  pick only `crew:rough`/`crew:ready`, so no planner change is needed; add a test proving an
  idea-only issue is never picked or refined.
- **Promotion:** the pitch PR body says `From idea #N` (not `Closes #N`: a closing reference
  would make `set_state` and `crew run` treat the idea issue as the PR's unit and route feedback
  to the implementer). Once the pitch PR is open, the lead closes the idea issue with a comment
  linking the PR. The pitch PR is from then on the only record. If the owner later declines the
  bet as "not now", the lead reopens the idea issue with `crew:idea`; a plain "no" leaves it
  closed. Pitch PRs stay as they are otherwise; no planner change.
- **Kickoff ideas:** filed in the kickoff session right after the baseline PR is opened, one
  per MVP epic, each linking the baseline PR and naming its epic. If the MVP cut changes in the
  baseline review, the lead adjusts the ideas while relaying that feedback.
- **Lead-owned PRs:** the same "for later → `crew:idea`" rule goes into the lead brief and
  `crew:relay`, so comments on pitch or baseline PRs are handled the same way.
- The label goes in `LABELS` under a new "Parked" group; pick a muted color.
- `crew:ideas` both files ideas and walks through them (one skill, two modes); `crew:pitch`'s
  description mentions it can start from a `crew:idea` issue.

## What changes

- `src/crew/labels.py`: the label; the guard in `label_problems`.
- `src/crew/inbox.py` and `src/crew/cli.py`: the parked-ideas count.
- `plugins/crew/skills/ideas/SKILL.md`: new.
- `plugins/crew/skills/pitch`, `inbox`, `kickoff`, `implement`: as above.
- `plugins/crew/agents/*.md`: the discovered-work rule; `lead.md` also names `crew:ideas`.
- `docs/workflow.md`: label table, discovered work, pitches section (ideas as the parked stage),
  kickoff step.
- `README.md`: skills list, day-to-day use ("park ideas").
- Tests: `test_labels.py`, `test_inbox.py`, `test_plugin_files.py` (skill list), `test_cli.py`
  for the count line, `test_graph.py`/planner for "never picked".
