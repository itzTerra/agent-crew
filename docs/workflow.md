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
| **Lead** | Opus | Shows the inbox, runs the kickoff and the pitch challenge, writes shaped pitches, relays owner feedback, marks do-first units, proposes retrospectives |
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
4. Optionally, the owner pitches ideas.

## Upstream: kickoff, pitches and bets

**Kickoff** (once per project): the lead and the owner condense existing material into a
requirements baseline: goals, main user flows, an epic list and the MVP cut. Then the first
owner decisions follow: architecture and stack, operations and checks, design-system
alternatives. Features are not specified in detail at kickoff.

**Pitches**: every idea, the owner's or an agent's proposal, goes through a real back-and-forth
challenge by the lead: fit with decisions and requirements, worth, better alternatives
(including not building it), and what it would delay or break. What survives becomes a **shaped
pitch** with five sections: Problem, Appetite (a share of the weekly usage limit), Solution
(rough), Rabbit holes, No-gos.

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
units. Anything that adds scope or changes agreed behavior is filed as a proposal and goes
through the pitch challenge.

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
| `crew:do-first` | The owner wants it before anything else |
| `crew:owner-facing` | Needs owner acceptance before merging |
| `crew:internal` | Merges after review and CI without the owner |

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
