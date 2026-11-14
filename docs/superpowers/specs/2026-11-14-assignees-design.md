# Assignees for whose turn it is

## Why

The owner finds what needs them by reading the lead's messages, and those often name items only
as `#79` or "Q2, Q3 and the extensions plan", with no link. Two fixes:

- GitHub's own **"Assigned to me"** filter (per repo, and across repos at github.com/issues) should
  list exactly what waits on the owner, so the owner can work from GitHub without parsing agent
  output.
- The lead's messages should link every item they name.

## Goals

- An open issue or PR is assigned to `owner_login` exactly when it carries a `crew:owner-*` label.
- It is assigned to `agent_login` exactly when the agents hold it: `crew:in-progress`,
  `crew:in-review` or `crew:changes-requested`, and no `crew:owner-*` label.
- Assignment changes in the same `crew` call that changes the label, from one place in code.
- Drift (someone edits labels by hand, a call fails halfway) is found by `crew labels check` and
  repaired by `--fix` and by the run supervisor.
- Every message from the lead links each issue or PR it names at least once, recaps included.

## Non-goals and anti-goals

- The labels stay as they are: no renames, no removals. Assignees add a filter; they don't
  replace the `crew:owner-*` labels, which still say what is asked (accept, decision, stuck,
  proposal). (Considered with the owner and rejected: dropping the labels for assignees, or
  shortening their names.)
- `crew inbox` keeps reading labels, not assignees.
- Anti-goal: "Assigned to me" shows something that isn't waiting on the owner, or misses
  something that is. Both the owner and the bot assigned at once counts as this failure.
- Anti-goal: `crew` removes an assignee it doesn't manage.

## Decided with the owner

1. **Approach: `crew` sets assignees itself, with a check as the safety net.**
   - `crew labels set-state` sets the assignees for every item it moves.
   - New commands replace the raw `gh` label edits for the asks that stack on a flow label:
     `crew labels ask N decision|proposal` adds `crew:owner-<ask>` and assigns; `crew labels
     clear N decision|proposal` removes it and re-derives the assignees.
   - `crew labels check` reports assignee drift; `--fix` and the run supervisor's existing
     label repair fix it.
   - Rejected: repair only (agents keep raw `gh`, assignees lag until something runs the
     repair) and a GitHub Action on label events (a workflow and an assign-capable token in every
     project).
2. **Who is assigned**, derived from the item's labels alone:

   | Labels on the open item | Assignees `crew` wants |
   |---|---|
   | any `crew:owner-*` | `owner_login` only |
   | else `crew:in-progress`, `crew:in-review` or `crew:changes-requested` | `agent_login` only |
   | anything else with a crew label (rough, ready, idea) | neither |
   | no crew label at all | left alone |
   | closed issue, merged or closed PR | neither |

   An owner ask on an issue applies to that issue; its PR follows its own labels. (`set-state`
   already keeps an issue and its PRs on the same flow label.)
3. **Only two logins are managed.** `crew` adds and removes `owner_login` and `agent_login` and
   never touches any other assignee.
4. **Strict for the owner.** On an item with any crew label, `crew` alone decides whether
   `owner_login` is assigned: a hand-made self-assignment on, say, a ready unit is drift and gets
   removed. Items with no crew label are never touched. (Rejected: add-only, which would let
   "Assigned to me" show items that aren't asks.)
5. **Links.** The lead's rule (`plugins/crew/agents/lead.md`, "Whenever you open or mention a PR
   or issue…") is extended: in every message, each item named gets its full URL at least once,
   including repeated lists and summaries ("the same seven items…"), and a grouped item ("Q2, Q3
   for #47 and #48") links each number. The run skill's report rule says the same.

## Builder's notes

- `crew.labels` gains one pure function from labels (plus open/closed state) to the wanted set
  of managed assignees, used by `set_state`, the new commands, and the check. `set_state` needs
  the two logins, so it takes them (from `Config`) as arguments.
- `crew.github.GitHub` gains assignee reads and writes (REST
  `repos/{repo}/issues/{n}/assignees`, POST to add, DELETE to remove); `assignees` joins
  `ISSUE_FIELDS` and `PR_FIELDS`, and `labels_of` (or a sibling) also returns assignees.
- Assignee drift is reported separately from `LabelProblem`, because the planner holds back
  every unit with a label problem (`supervisor/planner.py`) and drift must never stall a run
  (for example when GitHub refuses to assign `agent_login`). The supervisor's `_repair_labels`
  fixes drift, honoring `dry_run`, and logs a refused assignment once per run, not every tick.
  `crew labels check` lists drift but exits non-zero only for label problems. (My call.)
- Every instruction that adds or removes `crew:owner-decision` or `crew:owner-proposal` by hand
  switches to `crew labels ask` / `clear`: the five agent prompts, the implement, refine, inbox
  and kickoff skills, and the lead's retrospective rule. Grep for the label names. Items that
  were created with an ask label on them (the designer's and architect's PRs, filed
  `crew:owner-proposal` issues, the retrospective) are now created without it, followed by
  `crew labels ask`, so assignment still comes from one place. (My call.)
- The asks are exactly `crew:owner-accept`, `-decision`, `-stuck` and `-proposal`
  (`graph.OWNER_ASKS`); `crew:owner-facing` is a kind, not an ask.
- Update `docs/workflow.md` (Labels section: one paragraph on assignees) and the README's setup:
  `agent_login` must be a collaborator on the repo so it can be assigned. If GitHub refuses to
  assign a login, `crew` reports it once per command and doesn't fail the label change.
- Tests: the derivation table, `set_state` assigning across an issue and its PRs, the new
  commands, the drift check and its fix, and that a third person's assignment is left alone.
