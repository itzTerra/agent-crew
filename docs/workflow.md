# The crew workflow

How a project is built by a small crew of Claude Code agents while one person acts as the
**product owner**: they accept or return finished work, choose between options for decisions that
are costly to reverse, and pitch ideas. The agents do the rest: planning, architecture proposals,
design, implementation, review and merging.

The goal: in about 20 minutes a day, the owner sees what needs them, deals with it, and comes
back later to work that already passed review.

## Principles

- **State lives in durable places.** No agent session lasts the whole project. Everything that
  matters is in the repo or on GitHub, and each agent starts fresh from a short brief.
- **One agent to talk to.** The owner talks only to the lead, never manages workers directly.
- **Feedback goes into the pull request**, written there by the owner or relayed by the lead.
- **One source of truth per fact**, in standard formats a CI check can validate.
- **A light process.** Shaping and betting upstream, Kanban flow downstream. No sprints, no
  estimates, no heavy specification phase up front.

## Roles

| Role | Model | Does |
|---|---|---|
| **Lead** | Opus | Shows the inbox, runs the kickoff and the pitch challenge, writes shaped pitches, parks ideas, relays owner feedback, marks do-first units, proposes retrospectives |
| **Architect** | Opus | Writes decision documents and ADRs, splits bets into units, refines rough units to ready |
| **Designer** | Sonnet | The design system and flow and screen alternatives, as clickable mockups |
| **Implementer** | Sonnet | One unit end to end: branch, tests, living spec update, pull request |
| **Reviewer** | Opus or Sonnet | The independent review gate; Opus for owner-facing or risky units |

Refinement is not a separate role: the architect or the lead does it in refinement mode.

## The owner's session

1. The owner starts a session with the lead.
2. The lead rebuilds its picture from GitHub and shows the **inbox** (`crew inbox`):
   - only items waiting on the owner, each with what is asked (accept, decide, unstick, consider
     a proposal) and a link;
   - ordered by do-first, then by how many open units each item blocks, directly or indirectly;
   - followed by the internal work merged without the owner since their last session, so they
     can return any of it as a new unit.
3. The owner acts on each item on GitHub (comment, approve) or tells the lead, who posts the
   owner's words on the PR as a quote.
4. Optionally, the owner pitches or parks ideas.

## Upstream: kickoff, pitches and bets

**Kickoff** (once per project): the lead and the owner condense existing material into a
requirements baseline: goals, main user flows, an epic list and the MVP cut. Then the first
owner decisions follow: architecture and stack, operations and checks, design-system
alternatives. Features are not specified in detail at kickoff. Each MVP epic is filed as a
parked idea, to be pitched later.

**Pitches**: every idea, the owner's or an agent's proposal, goes through a real back-and-forth
challenge by the lead: fit with decisions and requirements, worth, better alternatives
(including not building it), and what it would delay or break. What survives becomes a **shaped
pitch** with five sections: Problem, Appetite (a share of the weekly usage limit), Solution
(rough), Rabbit holes, No-gos.

**Parked ideas**: an idea the owner wants recorded but not challenged yet is filed as an issue
labeled `crew:idea`, from a session with the lead, an owner comment on a PR asking for
something for later, or an agent's discovered work. A parked idea is not a bet, not work and
not waiting on the owner; `crew inbox` shows only how many there are. When the owner goes
through them, the lead pitches the one they pick. A pitch PR from an idea says `From idea #N`
and the idea issue is closed once it is open; if the bet is declined as "not now", the idea is
reopened.

**Bets**: the pitch is proposed as a pull request; merging it is the owner's bet. Only a bet
becomes work. Work that runs past its appetite comes back to the owner as a decision; it never
silently grows.

## Downstream: units on a Kanban flow

A bet is split into **units**. One unit = one GitHub issue = one branch = one worktree = one pull
request. A unit moves: rough → ready → in progress → in review → (owner) → done.

**Definition of ready** (`crew check-issue`):

- a goal and a link to its bet;
- the delta to the living spec it changes, with WHEN/THEN scenarios, or `none — <reason>`;
- the paths it owns;
- its dependencies (`- #N` items or `none`);
- its kind: owner-facing or internal;
- every owner decision it touches already settled.

**Definition of done**:

- CI green, including `crew check-docs`;
- review passed;
- the living spec updated in the same PR;
- owner acceptance, for owner-facing units;
- merged under the project's merge rules, and the issue closed.

**Just-in-time refinement**: rough units are refined as they near the top of the order, scaled to
their size. Questions only the owner can answer go to the inbox before a worker would hit them.

**Safety valve**: an implementer who finds an unsettled question mid-unit sends it back instead
of guessing.

**Pick order** (`crew next`): do-first units, then the units that block the most others, then the
oldest. A unit is eligible only when every dependency is closed, it is not in a dependency cycle,
and it waits on nothing from the owner. Two units run at once only if their owned paths don't
overlap. The number of agents at once is the work-in-progress limit.

**Discovered work**: bugs and debt that only fix or tidy existing behavior are filed as rough
units. A find that changes agreed behavior, or a gap that blocks the current bet or puts it at
risk, is filed as a proposal and goes through the pitch challenge. Any other idea that would add
scope is filed as a parked idea.

## Labels

| Label | Meaning |
|---|---|
| `crew:rough` | Not yet refined to ready |
| `crew:ready` | Meets the definition of ready |
| `crew:in-progress` | A worker is on it |
| `crew:in-review` | Waiting for the review gate |
| `crew:changes-requested` | Review or owner feedback to address |
| `crew:owner-accept` | Waiting for the owner to accept |
| `crew:owner-decision` | Waiting for the owner to decide |
| `crew:owner-stuck` | Failed review three times; needs the owner |
| `crew:owner-proposal` | A proposal for the owner's pitch challenge |
| `crew:idea` | A parked idea: not a bet, not work, not waiting on the owner |
| `crew:do-first` | The owner wants it before anything else |
| `crew:owner-facing` | Needs owner acceptance before merging |
| `crew:internal` | Merges after review and CI without the owner |
| `crew:design` | Design work: the designer builds it, not the implementer |

A unit is done when its issue is closed by a merged PR with `Closes #N`.

## Review gate

1. **Automated checks first.** CI must be green before any agent review.
2. **Agent review** by a fresh reviewer who has never seen the implementer's session. It reads the
   issue, the diff, the living specs, requirements and ADRs involved, and the practices file, and
   checks:
   - **spec:** the living spec is updated and matches the code; nothing else still describes the
     old behavior;
   - **fit:** practices and ADRs followed, existing code reused, no duplicated logic;
   - **safety:** no security holes; validation on the client (soft) and server (hard);
   - **users:** accessibility, and error messages that say what happened and what to do;
   - **performance:** no N+1 queries or serial work that could run in parallel;
   - **checklist:** for UI work, the manual checklist walked in a real browser.
3. **Outcome:**
   - pass, owner-facing → waits for the owner's acceptance;
   - pass, internal → merged by an agent, listed under "merged without you";
   - fail → findings on the PR, the implementer fixes them;
   - third failed round → to the inbox as stuck, with a summary.

## Who accepts what

**Owner-facing**: features and other user-visible changes, design work, decision documents and
ADRs, flow changes, and anything touching an owner decision area. When unsure, a unit is
owner-facing.

**Internal**: work inside already accepted decisions, such as contracts an ADR already covers,
refactors, internal modules, and plumbing within the agreed CI setup.

To accept a feature, the owner gets a summary, the manual checklist taken from the spec
scenarios, and one command that runs the branch locally. They approve the PR on GitHub; an agent
then prepares the merge (squash, rebase, CI green) and merges. The owner never handles git.

## Decision rights

**The owner decides**; an agent prepares options, trade-offs and a recommendation:

- anything costly to reverse: architecture, languages, frameworks, storage, anything ADR-worthy;
- anything that costs money or affects income: paid services, provider or model choices that
  change cost, pricing;
- larger UX flows (which steps, in which order) and visual design;
- operations and checks: Docker, CI/CD, test framework, linters, formatters, type checking;
- the development workflow itself;
- whatever the project adds in `owner_decisions_extra`.

**Agents decide** inside those fences, visibly in the PR: code structure within a module, naming,
use of libraries already chosen, element placement, test cases, refactors that don't cross module
boundaries.

**When in doubt, it's the owner's.** A worker who hits an owner decision raises it as a decision
item, parks the unit, and moves on.

## Sources of truth and their formats

Each fact lives in exactly one place:

| Kind | Default location | Format |
|---|---|---|
| **Requirements**: cross-cutting hard constraints | `docs/requirements/` | Markdown tables with stable `REQ-<AREA>-<n>` IDs, a `Pri` of Must, Should or Later, and a source; statements in EARS wording that meet the ISO/IEC/IEEE 29148 quality rules |
| **Living specs**: how the product works now, one per area | `docs/specs/<area>/spec.md` | OpenSpec structure: Purpose, then `### Requirement:` blocks with one EARS "shall" statement, optional `Satisfies: REQ-…`, and `#### Scenario:` blocks with GIVEN/WHEN/THEN |
| **Decisions** | `docs/adr/` | MADR 4.0: context and problem, decision drivers, considered options, decision outcome, consequences, confirmation; status Proposed, Accepted, Rejected, Deprecated or Superseded by ADR-NNNN |

Everything else describes a change, not the product:

- **shaped pitches** (`docs/pitches/NNNN-slug.md`);
- **units**, which state only the delta to one living spec, in OpenSpec's ADDED / MODIFIED /
  REMOVED / RENAMED form;
- **plans and design notes**, which are working documents and history, never specs.

Rules:

- A PR changes the living spec, the code and the tests together. A change to an existing feature
  edits the same living spec file.
- If anything contradicts a living spec, a requirement or an accepted ADR, the latter wins.
- Accepted ADRs are never edited except their status; a new ADR supersedes an old one.
- The scenarios in living specs are the source of the owner's manual checklist and of the
  end-to-end tests.

`crew check-docs` validates the formats in CI: required sections, unique IDs, resolving
references, at least one scenario per spec requirement, no delta headings in living specs, and
every requirement cited by a spec or marked `[covered: <how>]`. The reviewer judges content
quality.

## Parallel work without collisions

- Each unit works in its own branch and worktree.
- Each unit names the paths it owns; units with overlapping paths don't run at the same time.
- Shared foundations (an ADR, a contract, the design system) are their own units and merge
  first; units that build on them depend on them.
- A dependency counts as done only when it is merged. Nobody builds on unmerged work.
- Before merging, a branch is rebased onto `main` and CI must be green again.

## Runs

Nothing runs unless the owner starts a run. A run has an end time, such as "until 07:00", or
"until Monday 07:00" when started on a Friday. The lead agrees it with the owner, shows the budget
and a dry run of the first step, and starts the run only with the owner's go-ahead. While it
runs, the lead reports each new item that waits on the owner as it appears, and summarizes the
end; it acts on an item only with the owner's go-ahead.

During a run a small local supervisor (`crew run`) keeps up to N agents busy, N = 1–3 from the
project settings (`max_agents`). Every couple of minutes it reads GitHub and:

- turns the owner's comments on a PR into "changes requested", and the owner's approval of an
  owner-facing PR into a merge. When the owner both comments and approves, the later action wins;
  feedback written before the run started counts like any other;
- returns a PR whose CI failed to its implementer, naming the failed checks;
- starts agents, finishing work before starting new work: merges, fixes, reviews (Opus for
  owner-facing units, Sonnet for internal ones), follow-ups on owner answers, units an earlier run
  paused, then new ready units in pick order (units labeled `crew:design` go to the designer,
  the rest to the implementer) (*do first* units ahead of the rest, then highest
  blocker first). It keeps a few units refined ahead of the workers (just-in-time refinement);
- runs each agent in its own terminal tab and worktree, under the agents' GitHub login, in Claude
  Code's auto mode;
- nudges an agent that stops before its unit moves on, once; an agent that stops again is
  reported on the issue and its unit marked stuck for the owner.

The run stops at the end time or the budget cap, whichever comes first:

- it doesn't start a unit it can't plausibly finish before the stop;
- work in progress at the stop is committed and pushed, so nothing is lost, and the next run
  resumes it;
- if nothing is ready (everything waits on the owner), the run ends early;
- it waits out session-limit resets and continues, so one evening start can span two overnight
  windows.

**Budget cap.** The default is 75% of the weekly limit. The owner can raise it for the current
week ("this week, up to 95%"); it falls back to the default when the weekly limit resets. The cap
counts the whole account's weekly usage, including the owner's own sessions. The supervisor reads
usage from the agents' own sessions; while it has no recent reading, it starts at most one agent.
A restarted supervisor adopts the agents still running, and a second run is refused while one is
active.
