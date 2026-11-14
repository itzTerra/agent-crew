# Assignees Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assign `owner_login` to every crew item waiting on the owner and `agent_login` to every
item the agents hold, from the same `crew` calls that move labels, with a drift check as the
safety net. The lead also links every item it names.

**Architecture:** One pure derivation in `crew.labels` (labels → wanted managed assignees) feeds
`sync_assignees`, which `set_state`, the new `ask`/`clear` commands and the drift fix all call.
Drift is a separate `AssigneeDrift` list, never a `LabelProblem`, so it can't block the planner.
Prompts switch from raw `gh` label edits to `crew labels ask/clear`.

**Tech Stack:** Python 3, `gh` CLI via `crew.github.GitHub`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-assignees-design.md`

## Global Constraints

- Managed logins are exactly `config.owner_login` and `config.agent_login`; never add or remove any other assignee.
- Asks are exactly `graph.OWNER_ASKS` (`accept`, `decision`, `stuck`, `proposal`) with prefix `crew:owner-`; `crew:owner-facing` is not an ask.
- Agent-held flow labels: `crew:in-progress`, `crew:in-review`, `crew:changes-requested`.
- An item with no `crew:` label at all is left alone.
- Labels are not renamed or removed; `crew inbox` keeps reading labels.
- A refused assignment never fails a label change and never blocks a run.
- Work on a feature branch (e.g. `feat/assignees`), not `main`. Commit this plan first; check each box in the commit of its task.

## Review Focus

- `agent_login` not a collaborator: GitHub's add-assignees call returns 201 but silently drops the login. Expect the label change to land, a one-line warning, exit 0 (test in Task 2).
- A PR closing two issues where only one has `crew:owner-decision`: after `set-state … in-review`, that issue stays owner-only, its sibling and the PR get the agent (test in Task 2).
- The owner self-assigned on a `crew:ready` issue, plus a third person assigned: drift removes only the owner (test in Task 4).
- Owner assigned on an issue with no crew labels: no drift reported (test in Task 4).
- `crew run --dry-run` with drift: logs "would assign", writes nothing (test in Task 4).

---

### Task 1: GitHub client reads and writes assignees

**Files:**
- Modify: `src/crew/github.py` (`ISSUE_FIELDS`, `PR_FIELDS`, `PR_DETAIL_FIELDS`, `labels_of`, new methods)
- Test: `tests/test_github.py`

**Interfaces:**
- Produces:
  - `assignees` appended to `ISSUE_FIELDS`, `PR_FIELDS`, `PR_DETAIL_FIELDS` (gh gives `[{"login": …}]`).
  - `GitHub.item_state(number: int) -> tuple[set[str], set[str]]`: (label names, assignee logins) from one `api repos/{repo}/issues/{n}` call; `labels_of` returns its first element.
  - `GitHub.set_assignees(number: int, add: list[str], remove: list[str]) -> set[str]`: POST `repos/{repo}/issues/{n}/assignees` with `-f assignees[]=<login>` per add; DELETE the same path with `-f assignees[]=<login>` per remove (one call each, skipped when empty). Returns the logins from `add` missing from the POST response's `assignees` (GitHub drops non-assignable users silently).

- [x] **Step 1: Write failing tests** — `test_item_state_reads_labels_and_assignees` (answer `{"labels":[{"name":"crew:ready"}],"assignees":[{"login":"ann"}]}` → `({"crew:ready"}, {"ann"})`); `test_set_assignees_argv` (asserts the POST and DELETE argv); `test_set_assignees_reports_dropped_login` (POST answer `{"assignees":[{"login":"ann"}]}` for add `["ann","bot"]` → `{"bot"}`); update `test_list_issues_argv_and_parse` to the new field string `number,title,body,labels,state,createdAt,closedAt,url,assignees`.
- [x] **Step 2: Run** `uv run pytest tests/test_github.py -q` — expect the new tests to FAIL.
- [x] **Step 3: Implement** the fields and the two methods in `src/crew/github.py`.
- [x] **Step 4: Run** `uv run pytest -q` — expect PASS (fix fakes that answer `labels_of` if the field change breaks them).
- [x] **Step 5: Commit** `feat: read and write assignees through the GitHub client`

### Task 2: Derive and sync assignees; `set_state` assigns

**Files:**
- Modify: `src/crew/labels.py`, `src/crew/cli.py` (`_cmd_labels_set_state`, the `fix_state` branch of `_cmd_labels_check`), `src/crew/supervisor/loop.py` (`_set_state`)
- Test: `tests/test_labels.py`, `tests/supervisor/fakes.py`, `tests/supervisor/test_loop.py`

**Interfaces:**
- Consumes: `GitHub.item_state`, `GitHub.set_assignees` (Task 1).
- Produces (in `crew.labels`):
  - `@dataclass(frozen=True) class Logins: owner: str; agent: str`, with `Logins.of(config: Config) -> Logins`.
  - `AGENT_HELD = ("crew:in-progress", "crew:in-review", "crew:changes-requested")`.
  - `wanted_assignees(labels: set[str], logins: Logins, closed: bool = False) -> set[str] | None`: `None` when no label starts with `crew:`; `set()` when closed; `{owner}` when any `crew:owner-<ask>`; `{agent}` when any `AGENT_HELD`; else `set()`.
  - `assignee_change(labels, assignees, logins, closed=False) -> tuple[list[str], list[str]]`: (add, remove), sorted, limited to the two managed logins; `([], [])` when `wanted_assignees` is `None`.
  - `sync_assignees(github, number, labels, assignees, logins) -> str | None`: applies `assignee_change`; returns a warning `"#N: GitHub did not assign <logins>; is it a collaborator?"` when `set_assignees` reports dropped logins, else `None`.
  - `set_state(github, number, state, logins: Logins) -> StateResult` where `@dataclass class StateResult: numbers: list[int]; warnings: list[str]`. Each target's final labels are computed from its fetched labels plus the label edit (no second fetch), then synced. Callers updated: the CLI prints `#N: <state>` per number as now and each warning to stderr; the supervisor logs warnings.

- [x] **Step 1: Write failing tests** in `tests/test_labels.py`:
  - `test_wanted_assignees` table: `{"crew:owner-decision","crew:in-progress"}` → `{"owner"}`; `{"crew:in-review"}` → `{"bot"}`; `{"crew:ready"}` → `set()`; `{"crew:owner-facing","crew:ready"}` → `set()`; `{"bug"}` → `None`; `{"crew:in-review"}` closed → `set()`.
  - `test_assignee_change_leaves_others`: labels `{"crew:ready"}`, assignees `{"owner","carol"}` → `([], ["owner"])`.
  - `test_set_state_assigns_agent_and_owner`: PR 9 closes 5 and 6; 5 has `crew:owner-decision`; `set_state(github, 9, "in-review", LOGINS)` → assignee POSTs `(5, owner)`, `(6, bot)`, `(9, bot)`.
  - `test_set_state_warns_when_login_dropped`: POST answer without `bot` → `StateResult.warnings == ["#9: GitHub did not assign bot; is it a collaborator?"]`, labels still written.
  - Update existing `set_state` tests to pass `LOGINS = Logins("owner", "bot")` and read `.numbers`; make `label_calls` ignore `/assignees` paths.
- [x] **Step 2: Run** `uv run pytest tests/test_labels.py -q` — expect FAIL.
- [x] **Step 3: Implement** the above in `src/crew/labels.py`; update the three callers; add `assignees` and `set_assignees`/`item_state` to `tests/supervisor/fakes.FakeGitHub` (items carry `"assignees": [{"login": …}]`, default empty).
- [x] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [x] **Step 5: Commit** `feat: assign the owner or the agents when a unit changes state`

### Task 3: `crew labels ask` and `crew labels clear`

**Files:**
- Modify: `src/crew/labels.py`, `src/crew/cli.py`
- Test: `tests/test_labels.py`

**Interfaces:**
- Consumes: `sync_assignees`, `Logins`, `GitHub.item_state` (Task 2).
- Produces:
  - `STACKED_ASKS = ("decision", "proposal")`.
  - `set_ask(github, number, ask: str, on: bool, logins: Logins) -> str | None`: adds (`on=True`) or removes `crew:owner-<ask>` on that one item, then syncs its assignees; returns the warning. Raises `ValueError` for an ask outside `STACKED_ASKS`.
  - CLI: `crew labels ask N decision|proposal` prints `#N: crew:owner-<ask>`; `crew labels clear N decision|proposal` prints `#N: removed crew:owner-<ask>`; warnings to stderr; exit 0.

- [x] **Step 1: Write failing tests**: `test_ask_adds_label_and_assigns_owner_removing_agent` (item in `crew:in-progress` assigned `bot` → POST label, POST `owner`, DELETE `bot`); `test_clear_hands_back_to_agent` (reverse); `test_ask_rejects_accept` (`ValueError`, nothing written); `test_labels_ask_cli` (output line, exit 0).
- [x] **Step 2: Run** `uv run pytest tests/test_labels.py -q` — expect FAIL.
- [x] **Step 3: Implement** `set_ask` and the two subcommands (argument `ask` with `choices=STACKED_ASKS`).
- [x] **Step 4: Run** `uv run pytest -q` — expect PASS (including `tests/test_plugin_files.py`'s registered-commands check).
- [x] **Step 5: Commit** `feat: add crew labels ask and clear`

### Task 4: Drift check, `--fix`, and the run supervisor's repair

**Files:**
- Modify: `src/crew/labels.py`, `src/crew/cli.py` (`_cmd_labels_check`, `_fetch_label_problems` callers), `src/crew/supervisor/snapshot.py`, `src/crew/supervisor/loop.py` (`_repair_labels`)
- Test: `tests/test_labels.py`, `tests/supervisor/test_snapshot.py`, `tests/supervisor/test_loop.py`

**Interfaces:**
- Consumes: `assignee_change`, `Logins` (Task 2); `GitHub.set_assignees` (Task 1).
- Produces:
  - `@dataclass(frozen=True) class AssigneeDrift: number: int; add: tuple[str, ...]; remove: tuple[str, ...]`, with `message` property `"assign owner, unassign bot"` style (only the non-empty halves).
  - `assignee_drift(open_issues, closed_issues, open_prs, merged_prs, logins) -> list[AssigneeDrift]`, sorted by number; closed issues and merged PRs count as closed.
  - `Snapshot.drift: list[AssigneeDrift]` (default empty), filled in `take_snapshot` from the lists it already fetches. The planner does not read it.
  - `crew labels check`: after the label problems, prints `#N: assignees: <message>` per drift; with `--fix` applies `set_assignees` and prints `fixed #N` (or the warning). Drift never changes the exit code; "no label problems" prints only when there are neither problems nor drift.
  - Supervisor: `_repair_labels` also applies drift (dry run: logs `#N: would <message> (assignee drift)`); a dropped login is logged once per run per (number, login) via a `self.refused_assignees: set[tuple[int, str]]`.

- [x] **Step 1: Write failing tests**:
  - `test_assignee_drift_strict_owner`: open `crew:ready` issue assigned `owner` and `carol` → one drift `(n, (), ("owner",))`.
  - `test_assignee_drift_ignores_non_crew_items`: issue labeled `bug`, assigned `owner` → `[]`.
  - `test_assignee_drift_closed_and_merged`: merged PR assigned `bot` → remove `bot`.
  - `test_labels_check_reports_drift_without_failing`: exit 0, line `#4: assignees: assign owner`; with `--fix`, `set_assignees` called and `fixed #4` printed.
  - Supervisor: `test_repair_applies_assignee_drift`, `test_dry_run_only_logs_assignee_drift`, `test_refused_assignment_logged_once` (two ticks, one log line, units still planned).
- [x] **Step 2: Run** `uv run pytest tests/test_labels.py tests/supervisor -q` — expect FAIL.
- [x] **Step 3: Implement** as above.
- [x] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [x] **Step 5: Commit** `feat: find and repair assignee drift`

### Task 5: Prompts and skills use `crew labels ask/clear`; links in every message

**Files:**
- Modify: `plugins/crew/agents/{lead,architect,designer,implementer,reviewer}.md`; `plugins/crew/skills/{implement,refine,inbox,kickoff,run}/SKILL.md`, and any other file `grep -rn "owner-decision\|owner-proposal" plugins` shows adding or removing those labels.
- Test: `tests/test_plugin_files.py`

**Interfaces:**
- Consumes: the CLI from Task 3.

- [x] **Step 1: Write failing tests** in `tests/test_plugin_files.py`:
  - `test_owner_asks_go_through_crew` (parametrized over every agent and skill file): text contains no `add the \`crew:owner-decision\` label`, no `--add-label`/`--remove-label` naming `crew:owner-`; each file that mentions `crew:owner-decision` or `crew:owner-proposal` as something to set also contains `crew labels ask`.
  - `test_lead_links_every_item_in_every_message`: `lead.md` contains `at least once in every message` and `repeated lists`; `run/SKILL.md` contains `at least once in every message`.
- [x] **Step 2: Run** `uv run pytest tests/test_plugin_files.py -q` — expect FAIL.
- [x] **Step 3: Edit the prompts:**
  - "add the `crew:owner-decision` label" → "run `crew labels ask N decision`"; removing it (inbox "record a decision") → `crew labels clear N decision`.
  - Items filed already waiting on the owner (designer's and architect's PRs, `crew:owner-proposal` issues in "Discovered work", the lead's retrospective): create without the ask label, then `crew labels ask N decision|proposal`.
  - `lead.md` link rule becomes: "Whenever you open or mention a PR or issue to the owner, in the session or on GitHub, give its full URL (`https://github.com/<repo>/pull/N`) at least once in every message, including repeated lists and summaries; when one line names several items, link each."
  - `run/SKILL.md` "waiting on you" step: same "at least once in every message" wording for repeated reports.
- [x] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [x] **Step 5: Commit** `feat(agents): raise owner asks with crew labels ask and link every item`

### Task 6: Document assignees

**Files:**
- Modify: `docs/workflow.md` (Labels section), `README.md` (agent account setup near `agent_login`)

- [x] **Step 1:** In `docs/workflow.md` under Labels, add one paragraph: the owner is assigned exactly while a `crew:owner-*` ask is on an item, the agents' account while it is in progress, in review or has changes requested, nobody otherwise; only these two logins are managed; "Assigned to me" is the owner's queue; `crew labels check` reports drift.
- [x] **Step 2:** In `README.md`, state that `agent_login` must be a collaborator on the repo so it can be assigned, and that `crew` warns when GitHub drops an assignment.
- [x] **Step 3: Run** `uv run pytest -q` — expect PASS (`test_no_private_references` included).
- [x] **Step 4: Commit** as `git commit --fixup=<Task 2's commit>` (the docs belong to the feature; squashed before finishing).
