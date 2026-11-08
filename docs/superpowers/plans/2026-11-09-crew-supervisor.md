# Crew supervisor — implementation plan (2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `crew run --until <time>`, a small local supervisor that keeps up to `max_agents` crew
agents busy in herdr within an end time and a weekly budget cap. Before it, the 19 workflow changes
the owner accepted from the first trial run's retrospective (R1–R19 below).

**Architecture:**
- **Part 1 (Tasks 1–8)** applies the retrospective to the existing CLI, skills and briefs. The
  supervisor relies on several of them: label states that agree between an issue and its PR
  (`crew labels set-state`, `crew labels check`), `crew check-owns` in the merge step, the reasons
  behind `crew next`, one-unit refinement, and a hardened `crew agent` with a working `--root`.
- **Part 2 (Tasks 9–17)** builds the supervisor as a `crew.supervisor` package. A pure **planner**
  turns a GitHub snapshot and the list of live agents into actions. A thin **herdr driver** and plain
  `git worktree` calls carry them out, and a **loop** ties them together, checking end time, budget
  and the 5-hour window on every tick.
- **Weekly usage** comes from Claude Code's status-line input. `crew agent` sets the status line to
  `crew usage record`, which stores the latest `rate_limits` reading in a per-account state file. So
  workers run as interactive sessions in herdr panes, not `claude -p`.

**Tech Stack:** Python ≥ 3.12, uv, PyYAML, pytest, ruff, the `gh` CLI, the `herdr` CLI, the Claude
Code plugin format.

**Spec:** the owner's workflow design. Its project-neutral form is
[`docs/workflow.md`](../../workflow.md). The supervisor section of the design is copied into Global
Constraints below, and the retrospective changes are listed in full under *Retrospective changes*,
so this plan can be executed from this repo alone.

## Global Constraints

- **Public repo, no private references.** No file may name a project using the crew, the owner, emails or
  local home-directory paths. Examples and fixtures are synthetic. Issue numbers from the
  trial run are not quoted. `tests/test_no_private_references.py` enforces this.
- No AGPL, GPL or non-commercial dependencies. Runtime dependency stays PyYAML only.
- Every CLI failure prints one line `crew: error: <message>` to stderr and exits 2. Findings exit 1.
  Success exits 0. No tracebacks for expected failures.
- A finding prints as `<relative path>:<line>: <CODE> <message>`. Labels all start with `crew:`.
- Conventional commits; never add AI-attribution trailers.
- Plugin skill bodies ≤ 120 lines, agent brief bodies ≤ 150 lines (existing tests).
- **From the design, the supervisor:**
  - "Nothing runs unless the owner starts a run. A run has an end time, such as 'until 07:00', or
    'until Monday 07:00' when started on a Friday."
  - Keeps up to N agents busy, N = 1–3 from project settings (`max_agents`).
  - "picks ready units, *do first* units ahead of the rest, then highest blocker first" (`next_ready`).
  - "keeps a few items refined ahead of the workers (just-in-time refinement)".
  - "checks for owner comments and approvals on PRs and turns them into agent work".
  - "waits out session-limit resets and continues, so one evening start can span two overnight
    windows".
  - "The run stops at the end time or the budget cap, whichever comes first": it "doesn't start a
    unit it can't plausibly finish before the stop"; "work in progress at the stop is committed and
    pushed, so nothing is lost"; "if nothing is ready (everything waits on the owner), the run ends
    early".
  - Budget cap: "the default is 75% of the weekly limit"; "the owner can raise it for the current
    week ('this week, up to 95%'). It falls back to the default when the weekly limit resets"; "the
    cap counts the whole account's weekly usage, including the owner's own sessions".
  - "The builder must verify how to get [weekly usage]. If no reliable reading exists, the builder
    proposes an alternative to the owner before building." That is Task 9's gate.
  - Agents run in Claude Code's auto mode (`--permission-mode auto`), under the agents' own GitHub
    login (`crew agent`).
  - Review model: Opus for owner-facing units, Sonnet for internal ones.

## Retrospective changes

| # | Change | Task |
|---|---|---|
| R1 | `crew:merge`: fetch and rebase onto the current `origin/main` *before* squashing; never build the squash from a tree based on an older `main` | 7 |
| R2 | `crew:merge`: before merging, the branch diff and the final squash commit's diff list only paths under the unit's Owns; otherwise stop and report | 7 |
| R3 | `crew check-owns <PR>`: the diff-against-Owns check, for the merge skill, the reviewer and CI | 6 |
| R4 | All briefs: every PR or issue mentioned to the owner, in a session or on GitHub, is given as a full URL | 8 |
| R5 | Lead brief and `crew:kickoff`: when existing requirements live outside the file being created, propose merging them into one file and ask the owner | 8 |
| R6 | `crew:implement` / `crew:refine`: when a unit grows well past the issue (more than about 25 new IDs or about 10 owner questions), comment on the issue, with its URL, before opening the PR | 7 |
| R7 | `crew:refine`: given one unit, refine only that unit; all rough units only when asked | 7 |
| R8 | Architect and lead briefs: when a `crew` command's result is unexpected, read its stated reason instead of guessing | 8 |
| R9 | `crew next`: print why each ready unit is left out (WIP limit, unmet dependency, Owns overlap, label) | 4 |
| R10 | `crew:implement`: before asking for review, squash your own fixups and push with `--force-with-lease`, following the project's merge rules | 7 |
| R11 | `crew:implement`: when re-requesting review, remove `crew:owner-accept` before adding `crew:in-review`; a PR never carries both | 5, 7 |
| R12 | `crew:review` and `crew:merge`: move the linked issue's labels with the PR's, and clear workflow labels when the issue closes | 5, 7 |
| R13 | Label-consistency check (in `crew inbox --peek`): open PRs with more than one state label, closed issues still carrying one | 5 |
| R14 | `crew check-docs`: flag a requirements table with no Why column | 3 |
| R15 | `crew init` and README: the plugin install step; `crew agent` checks the plugin is installed and prints the install command | 2 |
| R16 | `crew agent`: isolate `GH_CONFIG_DIR` per agent session | 1 |
| R17 | `crew agent`: compare `agent_login` case-insensitively | 1 |
| R18 | `crew agent`: a non-integer `GIT_CONFIG_COUNT` is a clear error, not a traceback | 1 |
| R19 | `crew agent`: `--root` sets the session's working directory | 1 |

The retrospective also asked to clean up the labels on two closed issues in the project that ran
the trial. That happens in that project, with `crew labels check --fix` from Task 5. It is not a
task here.

## Review Focus

1. **Owner feedback written before the run starts.** The owner typically comments in the evening, then
   starts a run. That comment must still count as unanswered and become work. Test: Task 12
   `test_owner_comment_before_run_is_unanswered`.
2. **The supervisor is restarted mid-run while its agents are still live.** It must adopt them from
   `.crew/run.json`, not start a second agent on the same unit, and refuse a second concurrent `crew run`.
   Tests: Task 15 `test_restart_adopts_live_agents`, `test_second_run_refused_while_first_alive`.
3. **No usage reading, or a stale one** (no agent session has drawn a status line for a while). The run
   must not start agents unboundedly on an unknown budget. Test: Task 15
   `test_stale_usage_starts_one_probe_agent_only`.
4. **`--until 07:00` given after 07:00, or `--until Mon 07:00` given on a Monday afternoon.** It rolls to the
   next occurrence; an explicit date in the past is an error. Test: Task 16
   `test_parse_until_rolls_forward`.
5. **The owner both approves and comments on a PR**, in either order. The later action wins: approve
   after comment → merge; comment after approve → changes requested. Test: Task 12
   `test_latest_owner_action_wins`.

---

## Part 1 — retrospective changes

### Task 1: Harden `crew agent` (R16–R19)

**Files:**
- Modify: `src/crew/agent.py`, `src/crew/cli.py` (`_cmd_agent`)
- Test: `tests/test_agent.py`

**Interfaces:**
- Produces:
  ```python
  def agent_env(base: Mapping[str, str], token: str, login: str, user_id: int,
                gh_config_dir: Path) -> dict[str, str]
  def new_gh_config_dir(env: Mapping[str, str]) -> Path  # fresh 0700 dir under $XDG_RUNTIME_DIR or the temp dir
  def run_agent(role, prompt, model, agent_login, owner_login, check, root: Path) -> None
  ```

- [x] **Step 1: Write the failing tests** in `tests/test_agent.py`:
  - `test_gh_config_dir_isolated`: `env["GH_CONFIG_DIR"]` is set, differs from any `GH_CONFIG_DIR` in
    `base`, exists, is empty and has mode `0o700`. Two `new_gh_config_dir` calls give different paths.
  - `test_agent_login_case_insensitive`: config `agent_login: Agent-B`, token of `agent-b` → the agent
    starts (`FakeExec` called once).
  - `test_bad_git_config_count_is_clean_error`: `GIT_CONFIG_COUNT=abc` and `=-1` → `main([...])` returns
    2 and stderr is one line that contains `GIT_CONFIG_COUNT`.
  - `test_root_sets_session_cwd`: `FakeExec` records `os.getcwd()` when called; it equals the `--root`
    path (use `monkeypatch.chdir` so the test restores the cwd).
  - `test_check_prints_isolated_gh_config`: `--check` prints a line `gh config: isolated`.
- [x] **Step 2:** Run `uv run pytest tests/test_agent.py -v`. Expected: the five new tests FAIL.
- [x] **Step 3: Implement.** In `agent_env`, set `GH_CONFIG_DIR`. Parse `GIT_CONFIG_COUNT` with a check
  that raises `AgentError("GIT_CONFIG_COUNT is '<value>', not a whole number ≥ 0; unset or fix it")`.
  Compare `login.casefold() != agent_login.casefold()`. In `run_agent`, `os.chdir(root)` right before
  `EXEC`. The `--check` output gains `gh config: isolated` after the `gh:` line.
- [x] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [x] **Step 5:** Commit `fix: isolate gh config, accept any agent_login case and honour --root in crew agent`.

### Task 2: Plugin install step and check (R15)

**Files:**
- Modify: `src/crew/agent.py`, `src/crew/cli.py` (`_cmd_init` output), `README.md` ("Set up a project")
- Test: `tests/test_agent.py`, `tests/test_init.py`

**Interfaces:**
- Produces:
  ```python
  PLUGIN_INSTALL = ("claude plugin marketplace add https://github.com/itzTerra/agent-crew"
                    " && claude plugin install crew@agent-crew")
  def plugin_installed(env: Mapping[str, str]) -> bool | None
      # reads <$CLAUDE_CONFIG_DIR or ~/.claude>/plugins/installed_plugins.json;
      # True if any key of its "plugins" mapping starts with "crew@", False if none does,
      # None if the file is missing or has another shape (the check is then skipped)
  ```

- [x] **Step 1: Write the failing tests:**
  - `test_plugin_installed_reads_registry`: a fake config dir with `{"plugins": {"crew@agent-crew": []}}`
    → `True`; with only `other@x` → `False`; no file → `None`.
  - `test_agent_without_plugin_prints_install_command`: registry without `crew@…` → exit 2, stderr one line
    containing `crew plugin is not installed` and `PLUGIN_INSTALL`; `FakeExec` not called; the token is
    not read (the token file may be absent in this test).
  - `test_init_prints_plugin_step`: `crew init` output ends with the line
    `next: install the Claude Code plugin: <PLUGIN_INSTALL>` when `plugin_installed` is not `True`.
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement. `run_agent` calls `plugin_installed(os.environ)` right after the role
  check and raises `AgentError` only on `False`. `--check` prints `plugin: crew installed` or
  `plugin: unknown (registry not found)`. In the README's "Set up a project", put the plugin install
  first as a numbered step, then `crew init`, then `crew labels sync`.
- [x] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [x] **Step 5:** Commit `feat: check the crew plugin is installed before starting an agent`.

### Task 3: Requirements tables need a Why column (R14)

**Files:**
- Modify: `src/crew/docs/requirements.py`
- Test: `tests/docs/test_requirements.py` (the fixture stays as it is)

**Interfaces:**
- Produces: finding code `REQ-WHY` (error), one per table, at the table's header line, message
  `requirements table has no Why column`. A table counts when at least one of its rows is a requirement.

- [x] **Step 1: Write the failing test** `test_table_without_why`: parsing `requirements-mixed.md` gives
  exactly two `REQ-WHY` findings, at the header lines of the `AREA DOC` and `AREA LATER` tables, and
  still 12 requirements. Change `test_mixed_requirements_parse` to assert that the only findings are
  those two.
- [x] **Step 2:** Run `uv run pytest tests/docs -v`. Expected: FAIL.
- [x] **Step 3:** Implement. When the header is read, remember whether a `why` column exists and the
  header line. Emit the finding when the table's first requirement row is seen.
- [x] **Step 4:** Run `uv run pytest -v`. Expected: PASS. Fix any other fixture under
  `tests/fixtures/project/` that now fails `test_fixture_project_clean` by adding a Why column to it.
- [x] **Step 5:** Commit `feat: flag requirements tables without a Why column`.

### Task 4: `crew next` says why each ready unit is left out (R9)

**Files:**
- Modify: `src/crew/graph.py` (move `RUNNING` and `BUSY` here from `cli.py`), `src/crew/cli.py` (`_cmd_next`)
- Test: `tests/test_graph.py`, `tests/test_inbox.py` (CLI test)

**Interfaces:**
- Produces:
  ```python
  RUNNING = "crew:in-progress"
  BUSY = frozenset({"crew:in-review", "crew:changes-requested", "crew:owner-accept", "crew:owner-stuck"})

  @dataclass(frozen=True)
  class Skipped:
      number: int
      reason: str

  def ready_report(units, running: list[int], max_agents: int, busy: list[int] = ()
                   ) -> tuple[list[int], list[Skipped]]
  # next_ready() keeps its signature and returns ready_report(...)[0]
  ```
  Every unit labeled `crew:ready` that is not picked gets one `Skipped`, with the first reason that
  applies, in this order and with exactly this wording:
  `already running` · `has an open PR (<label>)` · `waits on the owner (<label>)` ·
  `in a dependency cycle` · `depends on open #12, #15` · `owns overlap with #7` ·
  `WIP limit reached (2 of 2 agents)`.

- [x] **Step 1: Write the failing tests:**
  - `test_ready_report_reasons`: one fixture with a ready unit for each reason; assert the exact
    `Skipped` list, ordered by unit number.
  - `test_next_cli_prints_left_out`: `crew next` output has the picks, then a `Left out` block of lines
    `  #N <title> — <reason>`.
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement `ready_report` by moving the body of `next_ready` into it and recording a
  reason wherever a unit is filtered out. The overlap reason names the first overlapping unit.
- [x] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [x] **Step 5:** Commit `feat: explain why crew next leaves ready units out`.

### Task 5: Label states that agree between issue and PR (R11, R12, R13)

**Files:**
- Modify: `src/crew/labels.py`, `src/crew/github.py`, `src/crew/cli.py` (`labels set-state`, `labels check`, inbox section)
- Test: `tests/test_labels.py` (new), `tests/test_inbox.py`

**Interfaces:**
- Consumes: `GitHub.list_issues`, `GitHub.list_prs`, `GitHub.set_labels`.
- Produces:
  ```python
  # Flow labels: at most one on an issue or PR at a time. The owner asks
  # crew:owner-decision and crew:owner-proposal may stack on top of a flow label.
  FLOW = ("crew:rough", "crew:ready", "crew:in-progress", "crew:in-review",
          "crew:changes-requested", "crew:owner-accept", "crew:owner-stuck")
  STATES = ("rough", "ready", "in-progress", "in-review", "changes-requested",
            "owner-accept", "owner-stuck", "done")      # "done" removes every flow label

  def set_state(github: GitHub, number: int, state: str) -> list[int]
      # number may be an issue or a PR. Applies to the issue and all its open PRs
      # (via closingIssuesReferences): removes the flow labels it carries, then adds crew:<state>.
      # Returns the numbers changed, ascending. A number found among the open PRs
      # (list_prs("open")) is a PR; any other number is an issue.

  @dataclass(frozen=True)
  class LabelProblem:
      number: int
      message: str
      fix_remove: tuple[str, ...]   # empty: not safe to fix automatically

  def label_problems(open_issues: list[dict], closed_issues: list[dict],
                     open_prs: list[dict], merged_prs: list[dict]) -> list[LabelProblem]

  # GitHub gains:
  def labels_of(self, number: int) -> set[str]   # gh api repos/<repo>/issues/<n>; works for PRs too
  ```
  Problems, in this order:
  - a closed issue or merged PR carrying any flow label → `fix_remove` = those labels;
  - an open issue or PR carrying more than one flow label → report only;
  - an open PR whose flow label differs from its linked open issue's → report only, message
    `PR #P has crew:owner-accept, its issue #N has crew:in-review`.
- CLI:
  - `crew labels set-state <N> <state>` prints one line `#N: crew:<state>` per number changed.
  - `crew labels check [--fix]` prints `#N: <message>` per problem; exit 1 when any is left unfixed.
    `--fix` applies the `fix_remove` ones and prints `fixed #N`.
  - `crew inbox` (with or without `--peek`) prints a `Label problems` block after the cycles when
    there are any.

- [x] **Step 1: Write the failing tests**, with the fake `run` from `tests/test_github.py`:
  - `test_set_state_moves_issue_and_pr_together`: issue 5 with `crew:in-review`, open PR 9 closing #5 with
    `crew:owner-accept` → `set_state(gh, 9, "in-review")` removes `crew:owner-accept` from 9, adds
    `crew:in-review` to 9, leaves 5's `crew:in-review`, and returns `[5, 9]`. Assert no DELETE call for
    a label that wasn't on the item.
  - `test_set_state_keeps_owner_decision`: an issue with `crew:rough` and `crew:owner-decision` set to
    `ready` keeps `crew:owner-decision`.
  - `test_set_state_done_clears_flow_labels`.
  - `test_label_problems_kinds`: one example per problem kind; assert messages and `fix_remove`.
  - `test_labels_check_fix_cli`: exit 0 after `--fix` when only fixable problems exist; exit 1 otherwise.
  - `test_inbox_lists_label_problems`.
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement. `crew inbox` fetches closed issues too (`list_issues("closed")`).
  Reject an unknown state with `CliError` listing `STATES`.
- [x] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [x] **Step 5:** Commit `feat: move issue and PR state labels together and check their consistency`.

### Task 6: `crew check-owns` (R3)

**Files:**
- Create: `src/crew/owns.py`, `tests/test_owns.py`
- Modify: `src/crew/github.py`, `src/crew/cli.py`, `src/crew/templates/github/workflows/crew-docs.yml`

**Interfaces:**
- Consumes: `parse_unit_body` (`owns`, `delta_text`), the `_TARGET` pattern in `units.py` (expose it as
  `delta_target(delta_text: str | None) -> str | None`).
- Produces:
  ```python
  def owns_match(path: str, glob: str) -> bool
  def outside_owns(paths: list[str], owns: list[str], allowed: list[str] = ()) -> list[str]
  # GitHub gains:
  def pr_files(self, number: int) -> list[str]        # gh pr diff N --name-only
  def pr_linked_issues(self, number: int) -> list[int]  # gh pr view N --json closingIssuesReferences
  ```
  CLI: `crew check-owns <PR> [--range REV_RANGE] [--root PATH]`. Without `--range`, the paths come
  from the PR on GitHub. With it, they come from `git diff --name-only <REV_RANGE>` run in `--root`.
  The allowed set is the linked issue's Owns plus its spec delta's `Target:` file.
  - Each outside path prints `<path>:1: OWNS-OUTSIDE not in the Owns of #N`, and the command exits 1.
  - Clean: prints `all <k> changed paths are inside the Owns of #N` and exits 0.
  - A PR that closes no issue: prints `PR #P closes no issue; nothing to check` and exits 0.
  - An issue with no Owns: `<issue>:1: OWNS-NONE #N lists no owned paths`, exit 1.

  **Glob rules:** `**` matches across `/`; `*` and `?` stay within one path segment. A pattern
  without wildcards matches that exact path, and everything under it when it names a directory
  (`docs/` or `docs` matches `docs/a.md`).

- [x] **Step 1: Write the failing tests:**
  - `test_owns_match_rules`: `src/api/**` ⊇ `src/api/a/b.py`; `src/*.py` ∌ `src/a/b.py`; `docs/x.md`
    matches only itself; `docs/` and `docs` ⊇ `docs/a.md`; `docs` ∌ `docs2/a.md`.
  - `test_outside_owns_allows_delta_target`.
  - `test_check_owns_cli_outside_path_exit_1`, `test_check_owns_cli_clean`,
    `test_check_owns_pr_without_issue_ok`, `test_check_owns_range_uses_git_diff` (fake `run` for git).
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement. The glob is translated to a regex by hand. Python 3.12 has no
  `PurePath.full_match`, and `fnmatch` lets `*` cross `/`. In `crew-docs.yml`, add a second step
  `- run: crew check-owns ${{ github.event.pull_request.number }}` with
  `env: GH_TOKEN: ${{ github.token }}`.
- [x] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [x] **Step 5:** Commit `feat: add crew check-owns to keep a PR inside its unit's owned paths`.

### Task 7: Skills — merge, review, implement, refine (R1, R2, R6, R7, R10, R11, R12)

**Files:**
- Modify: `plugins/crew/skills/merge/SKILL.md`, `review/SKILL.md`, `implement/SKILL.md`, `refine/SKILL.md`
- Test: `tests/test_plugin_files.py`

**Interfaces:**
- Consumes: `crew labels set-state` (Task 5), `crew check-owns` (Task 6), `crew next` reasons (Task 4).
- Every label change in these four skills uses `crew labels set-state <N> <state>` instead of raw
  `gh issue edit` / `gh pr edit` label flags.

**Required content:**
- **merge**, section "Shape the history", in this order:
  1. `git fetch origin && git rebase origin/main`, before any squash. If the branch has conflicts,
     resolve them inside Owns or stop.
  2. Squash per `merge_rules`.
  3. `crew check-owns P --range origin/main...HEAD`. Any outside path → stop, comment the paths with
     the PR's full URL, `crew labels set-state P changes-requested`.
  4. `git push --force-with-lease`, then `crew check-owns P` (GitHub's view).

  After `gh pr merge`, run `crew check-owns P --range <merge-sha>^..<merge-sha>`, where `<merge-sha>`
  is `gh pr view P --json mergeCommit`. If it lists outside paths, `main` already has them and only
  the owner may fix `main`. So set `crew:owner-stuck` on the issue, with a comment naming the paths.
  Cleanup is `crew labels set-state <N> done`.
- **review:** every outcome is set with `crew labels set-state`, so the issue and the PR move
  together. Step 1 adds `crew check-owns P`; outside paths are a failing finding.
- **implement:**
  - Before asking for review, squash your own fixups per the project's merge rules and push with
    `git push --force-with-lease`. Don't wait for the owner's go-ahead.
  - Request review with `crew labels set-state N in-review`, also after owner feedback, which
    removes `crew:owner-accept`.
  - If the change grows well past what the issue suggests (more than about 25 new IDs, or more than
    about 10 questions for the owner), comment on the issue with the PR or branch's full URL, set
    `crew:owner-decision`, and stop before opening the PR.
- **refine:**
  - Given one unit, refine only that unit. Take units from `crew next --rough` only when asked to
    refine the backlog.
  - The same size rule as implement: if refining shows the unit will exceed it, say so on the issue
    and propose a split.

- [x] **Step 1: Write the failing tests:**
  - `test_merge_rebases_before_squashing`: in the merge skill, the first `git rebase origin/main`
    comes before the first `squash`, and the text contains `crew check-owns P --range origin/main...HEAD`
    and `<merge-sha>^..<merge-sha>`.
  - `test_label_changes_use_set_state`: none of the four skills contains `--add-label` or
    `--remove-label`; each contains `crew labels set-state`.
  - `test_implement_squashes_and_flags_size`: contains `--force-with-lease`, `25`, `10`.
  - `test_refine_one_unit_only`: contains `only that unit`.
- [x] **Step 2:** Run `uv run pytest tests/test_plugin_files.py -v`. Expected: FAIL.
- [x] **Step 3:** Edit the four skills.
- [x] **Step 4:** Run `uv run pytest -v`. Expected: PASS (including `test_skills_reference_existing_cli_commands`).
- [x] **Step 5:** Commit `feat: rebase before squashing, check owned paths and move labels together in the skills`.

### Task 8: Briefs and kickoff — URLs, one requirements file, stated reasons (R4, R5, R8)

**Files:**
- Modify: all five `plugins/crew/agents/*.md`, `plugins/crew/skills/kickoff/SKILL.md`, `plugins/crew/skills/inbox/SKILL.md`
- Test: `tests/test_plugin_files.py`

**Required content:**
- **Every brief's Rules:** "Whenever you open or mention a PR or issue to the owner, in the session or
  on GitHub, give its full URL (`https://github.com/<repo>/pull/N`), not only `#N`."
- **Lead brief, Kickoff section, and `crew:kickoff` step 2:** "If requirements already live in another
  file under `paths.requirements` (or elsewhere), propose merging them into one file and ask the
  owner before going on. Record the answer on the PR."
- **Lead and architect briefs:** "When a `crew` command's result surprises you, read the reason it
  prints (for example `crew next`'s *Left out* lines) before you name a cause. Never guess one."
- **`crew:inbox`:** when presenting items, give each item's URL as printed.

- [ ] **Step 1: Write the failing tests:** add `"full URL"` to the shared phrases in
  `test_agent_brief_covers_shared_rules`. Add `test_lead_and_kickoff_propose_one_requirements_file`
  (both contain `propose merging`) and `test_lead_and_architect_read_stated_reason` (both contain
  `reason it prints`).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Edit the briefs and skills. Keep every body under its line limit.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: give full URLs, propose one requirements file and read stated reasons in briefs`.

---

## Part 2 — the supervisor

### Task 9: Verify the platform assumptions (gate)

No code. Write the results into a `## Platform findings` section at the end of this plan. Then
adjust the constants and JSON paths that Tasks 10 and 14 name, if they differ.

- [ ] **Step 1: Weekly usage.** Start one session with a status line that dumps its input:
  `claude --settings '{"statusLine":{"type":"command","command":"cat > <scratch>/statusline.json"}}'`.
  Send one message, then read the file. Record whether `rate_limits.seven_day.used_percentage`,
  `rate_limits.seven_day.resets_at`, `rate_limits.five_hour.used_percentage` and
  `rate_limits.five_hour.resets_at` exist, and the format of `resets_at` (epoch seconds or ISO 8601).
  **Gate:** if no weekly reading exists, stop here. Propose an alternative to the owner (for example
  a manually entered usage figure, or agent-hours as the budget) and wait for the decision before
  Task 10.
- [ ] **Step 2: Agents in herdr.**
  1. Run `herdr workspace create --cwd <repo> --label crew-check --no-focus` and record the JSON path
     of the workspace id.
  2. Run `herdr tab create --workspace <id> --cwd <repo> --label t --no-focus` and record the path of
     the new pane id.
  3. Run `herdr pane run <pane> "crew agent lead --check"`, then `herdr pane read <pane>`. The
     identity lines should appear.
  4. Run `herdr pane run <pane> "crew agent lead"`, then `herdr agent get <pane>`. Record whether
     herdr detects the `claude` started through `crew agent` (`agent_status` and its path in the
     JSON), and the statuses seen after `herdr agent prompt <pane> "Say hi"`.
  5. Close the workspace's panes.
- [ ] **Step 3: Launch flags.** Check that `claude --agent crew:lead --permission-mode auto --settings
  '<json>' "hi"` starts, and that the `--settings` status line replaces the user's own only in that
  session.
- [ ] **Step 4:** Commit the findings with this plan: `docs: record platform findings for the supervisor`.
  The commit is folded into Task 10's commit when the history is cleaned up.

### Task 10: Usage readings and agent launch flags

**Files:**
- Create: `src/crew/usage.py`, `tests/test_usage.py`
- Modify: `src/crew/agent.py` (`agent_argv`), `src/crew/cli.py` (`usage`, `usage record`, `agent --auto`)

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Usage:
      week_percent: float
      week_resets_at: datetime          # aware, UTC
      five_hour_percent: float
      five_hour_resets_at: datetime
      recorded_at: datetime

  USAGE_STALE = timedelta(minutes=30)
  def usage_path(env: Mapping[str, str]) -> Path
      # $CREW_USAGE_FILE, else $XDG_STATE_HOME (default ~/.local/state)/crew/usage-<account>.json,
      # <account> = the last part of $CLAUDE_CONFIG_DIR, or "default" when unset
  def record_statusline(payload: str, path: Path, now: datetime) -> str
      # parses Claude Code's status-line JSON; writes a Usage atomically (tmp file + rename)
      # when rate_limits is present; returns the status-line text
  def read_usage(path: Path) -> Usage | None   # None: missing or unreadable
  def is_fresh(usage: Usage | None, now: datetime) -> bool

  def agent_argv(role: str, prompt: str | None, model: str | None, auto: bool = False) -> list[str]
      # always adds --settings '{"statusLine":{"type":"command","command":"crew usage record"}}';
      # with auto, adds --permission-mode auto
  ```
- CLI:
  - `crew usage record`: the status-line command. It reads stdin, always exits 0, and prints
    `crew · week 41% (resets Mon 09:00) · 5h 12%`, or `crew · no usage data`.
  - `crew usage`: prints the reading and its age, or `no usage reading yet; it appears once a crew
    agent session has drawn its status line` (exit 0).
  - `crew agent … --auto`.

- [ ] **Step 1: Write the failing tests:**
  - `test_record_statusline_writes_reading`: a payload in the shape found in Task 9, with both `resets_at`
    formats (epoch and ISO) → the file holds the values, the text matches the format above.
  - `test_record_statusline_without_rate_limits`: no file written, text `crew · no usage data`.
  - `test_record_statusline_bad_json_never_fails`: `"{"` → returns the no-data text, raises nothing.
  - `test_usage_path_per_account`: `CLAUDE_CONFIG_DIR=/x/.claude-work` → name `usage-.claude-work.json`;
    `CREW_USAGE_FILE` wins.
  - `test_is_fresh`: 29 minutes old → True; 31 → False; None → False.
  - `test_agent_argv_settings_and_auto`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: record weekly usage from the agents' status line`.

### Task 11: This week's budget (`crew budget`)

**Files:**
- Create: `src/crew/budget.py`, `tests/test_budget.py`
- Modify: `src/crew/cli.py`

**Interfaces:**
- Consumes: `Usage`, `read_usage`, `usage_path` (Task 10); `read_state` / `write_state`; `Config.budget_cap_percent`.
- Produces:
  ```python
  def effective_cap(config: Config, state: dict, now: datetime) -> tuple[int, str]
      # (percent, "default") or (percent, "this week until <ISO>"); an override whose
      # "until" has passed is ignored
  def week_override(percent: int, usage: Usage) -> dict
      # {"percent": percent, "until": usage.week_resets_at ISO} for state["budget_override"]
  ```
- CLI: `crew budget` prints `cap 75% (default)` or `cap 95% this week (until <local time>), then 75%`,
  followed by the usage line from `crew usage`. `crew budget --week N` takes N from 1 to 100 and
  needs a usage reading for the reset time; without one it fails with
  `crew: error: no usage reading yet, so the week's reset time is unknown; start any crew agent first`.
  `crew budget --reset` drops the override.

- [ ] **Step 1: Write the failing tests:** `test_override_applies_until_week_reset`,
  `test_override_expires_at_reset`, `test_week_needs_reading`, `test_week_out_of_range`,
  `test_budget_cli_output`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: add crew budget to raise this week's cap`.

### Task 12: GitHub snapshot and owner activity

**Files:**
- Create: `src/crew/supervisor/__init__.py`, `src/crew/supervisor/snapshot.py`, `tests/supervisor/__init__.py`, `tests/supervisor/test_snapshot.py`
- Modify: `src/crew/github.py`

**Interfaces:**
- Consumes: `build_units`, `GitHub`, `Config` (`owner_login`, `agent_login`, `ci_checks`).
- Produces:
  ```python
  # GitHub gains:
  PR_DETAIL_FIELDS = ("number,title,url,state,labels,headRefName,closingIssuesReferences,"
                      "reviews,comments,commits,statusCheckRollup")
  def pr_detail(self, number: int) -> dict
  def issue_comments(self, number: int) -> list[dict]

  @dataclass(frozen=True)
  class OwnerActivity:
      kind: Literal["approved", "feedback", "none"]
      at: str          # ISO time of the owner's latest unanswered action, "" for none

  def owner_activity(comments: list[dict], reviews: list[dict], commits: list[dict],
                     owner_login: str, agent_login: str) -> OwnerActivity
  def checks_state(pr: dict, required: list[str]) -> Literal["pass", "fail", "pending", "none"]

  @dataclass
  class Snapshot:
      units: dict[int, Unit]
      prs: dict[int, dict]                    # open PRs, pr_detail dicts
      decisions: dict[int, OwnerActivity]     # open issues labeled crew:owner-decision
      problems: list[LabelProblem]

  def take_snapshot(github: GitHub, config: Config) -> Snapshot
      # problems = label_problems(open issues, [], open PRs, []): closed items aren't acted on
  ```
  **Owner activity rule:**
  - The *answer mark* is the latest of the comments and reviews by `agent_login` and the PR's
    commits (`committedDate`).
  - The owner's comments and reviews later than the mark are *unanswered*. Login comparison is
    case-insensitive.
  - None unanswered → `none`. If the latest unanswered one is a review with state `APPROVED` →
    `approved`. Otherwise → `feedback`.

  **Checks rule:** with `ci_checks` empty, every check in `statusCheckRollup` counts. Otherwise only
  the named ones count, and a missing one is `pending`. Any `FAILURE`, `CANCELLED`, `TIMED_OUT` or
  `ACTION_REQUIRED` conclusion → `fail`. Any check not `COMPLETED` → `pending`. No checks → `none`.

- [ ] **Step 1: Write the failing tests:**
  - `test_owner_comment_before_run_is_unanswered` (Review Focus 1): the owner's comment is later than the
    last agent comment and commit → `feedback`. No notion of "run start" enters the rule.
  - `test_latest_owner_action_wins` (Review Focus 5): comment then approve → `approved`; approve then
    comment → `feedback`.
  - `test_agent_reply_answers_owner`: an agent comment after the owner's → `none`.
  - `test_owner_login_case_insensitive`.
  - `test_checks_state_cases`: pass, fail, pending, none, and a required check missing → pending.
  - `test_take_snapshot_calls`: with a fake `run`, one `pr_detail` call per open PR, and
    `issue_comments` only for issues labeled `crew:owner-decision`.
- [ ] **Step 2:** Run `uv run pytest tests/supervisor -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: read PR state and the owner's unanswered activity for the supervisor`.

### Task 13: The planner

**Files:**
- Create: `src/crew/supervisor/planner.py`, `tests/supervisor/test_planner.py`
- Modify: `src/crew/config.py`, `src/crew/templates/crew/config.yaml`, `tests/test_config.py`

**Interfaces:**
- Consumes: `Snapshot`, `OwnerActivity`, `checks_state` (Task 12); `ready_report`, `rough_order`,
  `RUNNING`, `BUSY` (Task 4); `FLOW` (Task 5).
- Produces:
  ```python
  # Config gains (validated; defaults shown):
  poll_seconds: int = 120            # >= 30
  refine_ahead: int = 2              # >= 0
  stop_grace_minutes: int = 15       # >= 1
  estimates: dict[str, int]          # minutes; defaults below; unknown keys are a ConfigError
  DEFAULT_ESTIMATES = {"merge": 15, "fix": 30, "review": 20, "followup": 30,
                       "resume": 60, "implement": 90, "refine": 20}

  Kind = Literal["merge", "fix", "review", "followup", "resume", "implement", "refine"]

  @dataclass(frozen=True)
  class Action:
      kind: Kind
      number: int              # the issue, or the PR for review and merge
      issue: int | None        # the unit's issue when number is a PR
      role: str                # crew agent role
      model: str | None        # None: the agent definition's model
      prompt: str
      branch: str | None       # worktree branch; None: run in the main checkout
      detach: bool = False     # review worktrees are detached

  @dataclass(frozen=True)
  class Housekeeping:
      number: int
      state: str               # for set_state
      comment: str | None

  @dataclass
  class Plan:
      actions: list[Action]
      housekeeping: list[Housekeeping]
      waiting: list[str]       # why more doesn't start (shown in --dry-run and the log)
      idle: bool               # nothing to do now or later without the owner

  @dataclass(frozen=True)
  class Live:                  # what the planner needs about a live agent
      kind: Kind
      number: int
      issue: int | None

  def slug(title: str) -> str  # lowercase, runs of non-alphanumerics -> "-", trimmed, <= 40 chars, cut at a "-"
  def unit_branch(number: int, title: str) -> str   # "unit/<n>-<slug>"
  def plan(snapshot: Snapshot, live: list[Live], paused: list[dict], config: Config,
           free_slots: int, minutes_left: float) -> Plan
  ```
  **Rules.** Each target gets at most one action. A target that has a live agent, or that appears
  in `snapshot.problems`, is skipped, and the skip is noted in `waiting`.
  1. **Housekeeping**, done by the supervisor itself:
     - an open PR whose owner activity is `feedback`, and whose flow label isn't
       `crew:changes-requested` → `(PR, "changes-requested", None)`;
     - a PR in `crew:in-review` whose checks are `fail` →
       `(PR, "changes-requested", "CI failed: <names>. (crew run)")`.
  2. **merge:** a PR with `crew:owner-accept` and owner activity `approved` → implementer, prompt
     `Use crew:merge on PR #P (<url>). The owner approved it; read their comments first, and if any asks for a change, set changes-requested instead of merging.`,
     branch = `headRefName`.
  3. **fix:** a PR with `crew:changes-requested` → implementer, prompt
     `Use crew:implement on issue #N: changes are requested on PR #P (<url>).`, branch = `headRefName`.
  4. **review:** a PR with `crew:in-review` and checks `pass` (or `none`) → reviewer. The model is
     `sonnet` unless the PR or its issue has `crew:owner-facing`, in which case it is None (the brief's
     Opus). Prompt `Use crew:review on PR #P (<url>).`, branch = `headRefName`, `detach=True`.
  5. **followup:** an issue in `snapshot.decisions`, or an open PR labeled `crew:owner-decision`,
     whose owner activity isn't `none` → architect, prompt
     `The owner answered on #N (<url>). Continue from their answer: for a unit, use crew:refine on issue #N only; for a decision document, write the ADR per your brief.`,
     no branch.
  6. **resume:** each `paused` entry `{"number", "branch"}` whose issue is still `crew:in-progress` →
     implementer, prompt
     `Use crew:implement on issue #N: resume the work pushed on branch <branch> in an earlier run.`.
  7. **implement:** `ready_report(units, running=<issues of live implement/resume/fix agents>,
     max_agents=<live + free_slots>, busy=<issues with an open PR or crew:in-progress and no live agent and not paused>)`
     picks → implementer, prompt `Use crew:implement on issue #N (<url>).`,
     branch = `unit_branch(N, title)`. The `Skipped` reasons go into `waiting`.
  8. **refine:** while fewer than `refine_ahead` ready units remain unpicked and no refine agent is
     live, take the first unit of `rough_order` → architect, prompt
     `Use crew:refine on issue #N only (<url>).`, no branch. At most one refine action per plan.

  Actions keep this order (finish work before starting new work). The list is cut at `free_slots`.
  An action whose `estimates[kind]` exceeds `minutes_left` is dropped, with
  `not enough time for <kind> #N (<m> min)` in `waiting`.

  `idle` is true when there are no actions and no housekeeping, no PR has checks `pending`, and no
  dropped action is waiting only on slots or time.

- [ ] **Step 1: Write the failing tests** (snapshots built by hand, no `gh`):
  - `test_config_run_keys_defaults_and_validation` in `tests/test_config.py`.
  - `test_slug_and_unit_branch`: `"Add CSV export (v2)!"` → `unit/12-add-csv-export-v2`; a long title is
    cut to ≤ 40 slug characters at a `-`.
  - `test_owner_feedback_becomes_housekeeping_then_fix`: the first plan has housekeeping for the PR;
    the next plan, with the label applied, has a fix action.
  - `test_ci_failure_housekeeping_names_checks`.
  - `test_approved_owner_accept_merges`.
  - `test_review_model_by_kind`: internal → `sonnet`; owner-facing → None.
  - `test_pending_checks_wait_and_not_idle`.
  - `test_followup_on_answered_decision`.
  - `test_resume_only_paused_units` (an in-progress unit that isn't paused is busy: no resume, and its
    Owns block overlapping ready units).
  - `test_priority_order_and_free_slots`: with one free slot and a merge, a fix and an implement
    available, only the merge is chosen.
  - `test_not_enough_time_drops_action`.
  - `test_refine_ahead_keeps_one_refiner`.
  - `test_live_agent_target_skipped` and `test_label_problem_target_skipped`.
  - `test_idle_when_everything_waits_on_owner`.
- [ ] **Step 2:** Run `uv run pytest tests/supervisor/test_planner.py tests/test_config.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Add the four keys to the config template with one-line comments.
- [ ] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: plan supervisor actions from GitHub state`.

### Task 14: herdr driver and worktrees

**Files:**
- Create: `src/crew/supervisor/herdr.py`, `src/crew/supervisor/worktrees.py`, `tests/supervisor/test_herdr.py`, `tests/supervisor/test_worktrees.py`

**Interfaces:**
- Produces:
  ```python
  class HerdrError(Exception): ...
  class Herdr:
      def __init__(self, run=subprocess.run): ...
      def create_workspace(self, cwd: Path, label: str) -> str      # workspace id
      def open_tab(self, workspace: str, cwd: Path, label: str) -> str  # pane id, --no-focus
      def run_command(self, pane: str, command: str) -> None        # herdr pane run
      def status(self, pane: str) -> str | None
          # agent_status from `herdr agent get`; None when no agent is in the pane or the pane is gone
      def prompt(self, pane: str, text: str) -> None                # herdr agent prompt (no --wait)
      def read(self, pane: str, lines: int = 40) -> str             # --source recent-unwrapped
      def close(self, pane: str) -> None                            # herdr pane close; a gone pane is fine

  def worktree_for(root: Path, branch: str, detach: bool = False, run=subprocess.run) -> Path
  ```
  JSON paths are the ones Task 9 recorded. Failures raise `HerdrError` with herdr's error text,
  except the "gone" cases noted above.

  **Worktree rules:**
  - Run `git fetch origin` first.
  - The path is `<root.parent>/<root.name>-unit-<n>` for `unit/<n>-…` branches. Any other branch
    gets `<root.parent>/<root.name>-<branch with "/" → "-">`, and a detached review gets
    `<root.parent>/<root.name>-review-<branch with "/" → "-">`.
  - An existing worktree for the branch (`git worktree list --porcelain`) is reused. A reused
    detached review worktree is moved to the current commit with
    `git -C <path> checkout --detach origin/<branch>`.
  - New branch with no remote branch: `git worktree add -b <branch> <path> origin/main`.
  - Remote branch exists: `git worktree add <path> <branch>` if a local branch exists, otherwise
    `git worktree add --track -b <branch> <path> origin/<branch>`.
  - Detached: `git worktree add --detach <path> origin/<branch>`.

- [ ] **Step 1: Write the failing tests** with fake `run`s that record argv and return canned output:
  `test_open_tab_returns_pane_id`, `test_status_none_when_pane_gone`, `test_herdr_failure_is_herdr_error`,
  `test_worktree_new_unit_branch`, `test_worktree_reuses_existing`, `test_worktree_tracks_remote_branch`,
  `test_worktree_detached_review_refreshes`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: drive herdr panes and unit worktrees for the supervisor`.

### Task 15: The run loop — start, track and finish agents

**Files:**
- Create: `src/crew/supervisor/loop.py`, `tests/supervisor/test_loop.py`
- Modify: `src/crew/cli.py` (`run`), `src/crew/init.py` (gitignore `.crew/run.json`), `tests/test_init.py`

**Interfaces:**
- Consumes: Tasks 10–14, `set_state` (Task 5), `GitHub.comment`.
- Produces:
  ```python
  RUN_PATH = Path(".crew") / "run.json"     # gitignored; separate from state.json so crew inbox can't clobber it
  START_TIMEOUT = 120                       # seconds for herdr to see the agent
  NUDGE = ("You stopped before the unit moved on. Continue the task. If you can't, use the safety "
           "valve in your brief: comment, label, push, stop.")

  @dataclass
  class AgentRecord:
      pane: str; kind: Kind; number: int; issue: int | None; role: str
      branch: str | None; flow_at_start: list[str]; started_at: str
      nudges: int = 0; limited: bool = False

  class RunError(Exception): ...            # reported as crew: error:

  class Supervisor:
      def __init__(self, root: Path, config: Config, github: GitHub, herdr: Herdr,
                   until: datetime, cap: int | None, dry_run: bool,
                   clock=lambda: datetime.now(UTC), sleep=time.sleep, out=print,
                   worktree=worktree_for, usage_file: Path | None = None): ...
      def tick(self) -> str | None          # None: keep going; else the reason the run ends
      def run(self, once: bool = False) -> int
  ```
  - CLI: `crew run --until <when> [--cap N] [--dry-run] [--once] [--root PATH]`. `<when>` is parsed in
    Task 16. Until then, accept ISO 8601 only.
  - `init_project` appends both `.crew/state.json` and `.crew/run.json` to `.gitignore` when missing.

  **One tick, in order:**
  1. **Usage and cap** (the cap checks themselves come in Task 16).
  2. **Snapshot.**
  3. **Update agents.** For each record, read `herdr.status(pane)`:
     - `None` → the agent is gone: drop it and log it.
     - `working` → leave it.
     - `idle`, `done` or `blocked` → compare the target's flow labels (plus `crew:owner-decision`,
       and whether it is closed or merged) with `flow_at_start`:
       - changed → finished: close the pane and drop it;
       - unchanged and 5-hour window full → `limited = True` (Task 16);
       - unchanged and `nudges == 0` → prompt `NUDGE`, `nudges = 1`;
       - unchanged again → stuck: comment on the target "crew run: the agent stopped twice without
         finishing. Last output:" with the last 20 pane lines in a code block, then `set_state`
         `owner-stuck`, close the pane and drop it.
  4. **Housekeeping:** apply each item with `set_state` and `comment`.
  5. **Plan** with `free_slots = max_agents − len(agents)`. When `is_fresh(usage)` is false:
     `free_slots = 1` if there are no agents (one agent starts, and its status line brings a fresh
     reading), else 0.
  6. **Start each action:**
     - make the worktree (or use the root when `branch` is None);
     - create the run's herdr workspace on first use, labeled `crew run`, and store its id;
     - open a tab labeled `<kind> #<number>` in the worktree;
     - run `shlex.join(["crew", "agent", role, "--auto", "--root", str(cwd), *model_args, prompt])`;
     - poll `status` until it isn't None, up to `START_TIMEOUT`. On timeout: read the pane, close it,
       and raise `RunError("agent for <kind> #N did not start: <last pane line>")`;
     - record the agent with its flow labels at start.
  7. Write `run.json` (`pid`, `until`, `cap`, `workspace`, `agents`, `paused`).
  8. If `plan.idle` and there are no agents → return `"nothing to do: everything waits on the owner"`.

  **`--dry-run`:** prints the housekeeping, actions and `waiting` lines of each tick and changes
  nothing: no labels, comments, worktrees, panes or `run.json`. `--once` runs a single tick.

  **Start of `run()`:** if `run.json` holds a `pid` that is alive and isn't this process, raise
  `RunError("a run is already active (pid N)")`. Otherwise adopt the agents in `run.json` whose panes
  still have an agent, and drop the rest.

- [ ] **Step 1: Write the failing tests** with fake `GitHub`, `Herdr`, clock, sleep and worktree:
  - `test_tick_starts_planned_agents_with_crew_agent_command`: the exact `run_command` string for an
    implement action (`--auto`, `--root <worktree>`, the prompt last).
  - `test_finished_agent_pane_closed`.
  - `test_idle_without_progress_nudged_then_stuck`: first idle → one `NUDGE` prompt; second idle →
    comment, `owner-stuck`, pane closed.
  - `test_gone_agent_dropped`.
  - `test_agent_that_never_starts_ends_run_with_error`: `crew run --once` exits 2 with one line.
  - `test_stale_usage_starts_one_probe_agent_only` (Review Focus 3): three implement actions are
    possible, but there is no reading → one start in tick 1, none in tick 2 while the reading is still
    missing.
  - `test_restart_adopts_live_agents` (Review Focus 2): `run.json` lists a live pane for #12 → no new
    agent for #12.
  - `test_second_run_refused_while_first_alive` (Review Focus 2): `run.json` with the pid of a live
    process (`os.getppid()`) → exit 2.
  - `test_dry_run_changes_nothing`.
  - `test_ends_when_idle_and_no_agents`.
  - `test_init_ignores_run_file`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Tick errors from `GitHubError` are logged and retried at the next tick.
  Three in a row end the run with that error. Other errors end the run.
- [ ] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: add crew run, which keeps agents busy in herdr`.

### Task 16: Stopping — end time, cap, 5-hour window, wind-down

**Files:**
- Create: `src/crew/supervisor/until.py`, `tests/supervisor/test_until.py`
- Modify: `src/crew/supervisor/loop.py`, `src/crew/cli.py`, `tests/supervisor/test_loop.py`

**Interfaces:**
- Produces:
  ```python
  def parse_until(text: str, now: datetime) -> datetime
      # "07:00" -> next 07:00 after now (local time); "Mon 07:00" / "monday 07:00" -> next such
      # weekday and time after now; "2026-11-20T07:00" (local) or with an offset -> that time,
      # ValueError if it is not after now. Returned aware.
  FIVE_HOUR_FULL = 98.0                     # percent
  RESET_SLACK = timedelta(minutes=2)
  WIND_DOWN = ("The run is ending. Commit your work in progress on your branch (a wip: commit is "
               "fine), push it, comment on the issue what is done and what remains, then stop. "
               "Don't change the labels.")
  CONTINUE = "The usage limit has reset. Continue where you stopped."
  ```
  **Tick additions** (before step 2 of Task 15):
  - `now ≥ until` → end `"end time reached"`.
  - A fresh reading with `week_percent ≥ cap` → end `"budget cap reached (<p>% of <cap>%)"`. The cap is
    `--cap`, or else `effective_cap`.
  - A fresh reading with `five_hour_percent ≥ FIVE_HOUR_FULL` and `five_hour_resets_at > now` → log
    `waiting for the 5-hour window to reset at <local time>`. Update the agents (without nudging), start
    nothing, and use `min(poll_seconds, seconds until resets_at + RESET_SLACK)` as the sleep.
  - After `five_hour_resets_at + RESET_SLACK` → prompt `CONTINUE` to every `limited` agent and clear
    the flag.
  - `minutes_left` for the planner is `(until − now)` in minutes.

  **Wind-down,** at any end reason, Ctrl-C included:
  1. Prompt `WIND_DOWN` to every agent.
  2. Poll until each is idle, done or gone, for at most `stop_grace_minutes`.
  3. Close every pane.
  4. Each implement, resume or fix record whose issue still has `crew:in-progress` goes into `paused`
     as `{"number", "branch"}`.
  5. Write `run.json` without `pid` and agents.
  6. Print a summary: the reason, then the started, finished, stuck and paused units with their URLs.

  Exit 0 for a normal end, 2 for `RunError`.

- [ ] **Step 1: Write the failing tests:**
  - `test_parse_until_rolls_forward` (Review Focus 4): at 08:00 `"07:00"` gives 07:00 tomorrow; on a Monday at 15:00 `"Mon 07:00"`
    gives next Monday; a past ISO time raises `ValueError`; `"25:00"` raises.
  - `test_ends_at_until`, `test_ends_at_cap_with_cli_cap_override`.
  - `test_waits_out_five_hour_window_then_continues`: the agents become `limited` and aren't nudged;
    after the reset, `CONTINUE` is sent once.
  - `test_wind_down_pushes_and_pauses`: `WIND_DOWN` is sent, panes are closed, and the in-progress
    unit is in `paused`.
  - `test_next_run_resumes_paused_unit` (with the planner from Task 13).
  - `test_bad_until_is_clean_error`: CLI exit 2, one line.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v && uv run ruff check`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: stop runs at the end time or budget cap and wait out usage resets`.

### Task 17: Run and budget skills, docs, release

**Files:**
- Create: `plugins/crew/skills/run/SKILL.md`, `plugins/crew/skills/budget/SKILL.md`
- Modify: `plugins/crew/skills/implement/SKILL.md`, `plugins/crew/agents/lead.md`, `tests/test_plugin_files.py`, `README.md`, `docs/workflow.md`, `pyproject.toml`, `src/crew/__init__.py`, `plugins/crew/.claude-plugin/plugin.json`

**Required content:**
- **run** (lead, with the owner):
  1. Ask for the end time and confirm it.
  2. Show `crew budget`.
  3. Show `crew run --until <when> --dry-run --once`.
  4. With the owner's go-ahead, start `crew run --until <when>` in its own herdr tab
     (`herdr tab create --label "crew run" --no-focus`, then `herdr pane run`).

  Never start a run without the owner's say-so in this session.
- **budget** (lead): `crew budget`; `crew budget --week N` when the owner raises this week's cap;
  `crew budget --reset`.
- **implement**, step 1.3: "If the session starts in a worktree already on `unit/<N>-…` (a run made
  it), work there and skip creating one."
- **lead brief:** a *Runs* section that points to `crew:run` and `crew:budget`.
- **README:**
  - replace "Automated runs come in a later version" with an *Automated runs* section: `crew run`, its
    flags, the stop rules, the status-line usage file, `crew budget`, and what `--dry-run` shows;
  - new rows in the CLI and settings tables (`check-owns`, `labels set-state`, `labels check`,
    `usage`, `budget`, `run`; `poll_seconds`, `refine_ahead`, `stop_grace_minutes`, `estimates`);
  - a note that projects set up with an older `crew init` add the `crew check-owns` step to
    `crew-docs.yml` by hand.
- **`docs/workflow.md`:** the runs section, describing the supervisor as built.
- **Version** `0.3.0` everywhere.

- [ ] **Step 1: Write the failing tests:** add `run` and `budget` to `SKILLS`; `test_run_skill_needs_owner_go_ahead`
  (contains `--dry-run` and `go-ahead`).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Write the skills and docs, and bump the version.
- [ ] **Step 4:** Run `uv run pytest -v && uv run ruff check && claude plugin validate plugins/crew`. Expected: PASS.
- [ ] **Step 5: Smoke test** in a scratch private repo (`gh repo create <owner>/crew-sandbox --private`),
  with the agents' account added as a collaborator:
  1. `crew init`, `crew labels sync`. File one tiny ready internal unit, for example "add a
     `hello.txt`" with Owns `hello.txt`.
  2. `crew run --until <now + 45 min> --dry-run --once`. Expected: one implement action.
  3. `crew run --until <now + 45 min>`. Expected: an implementer opens a PR, a reviewer passes and
     merges it, and the run ends with "nothing to do".
  4. `crew labels check`. Expected: no problems.

  Ask the owner before deleting the sandbox repo.
- [ ] **Step 6:** Commit `feat: add run and budget skills and document automated runs`. With the
  owner's go-ahead, push, tag `v0.3.0` and push the tag.

