# agent-crew

A Claude Code plugin, `crew`, and a Python CLI, `crew`, for building a project with a small crew
of Claude Code agents while you act as the product owner. All state lives in the repo and on
GitHub: issues are units of work, labels say whose turn it is, and pull requests carry every
review finding and every piece of owner feedback.

The plugin gives a project:

- **role agents:** `crew:lead`, `crew:architect`, `crew:designer`, `crew:implementer`,
  `crew:reviewer`;
- **skills:** `crew:inbox`, `crew:kickoff`, `crew:pitch`, `crew:refine`, `crew:relay`,
  `crew:implement`, `crew:review`, `crew:merge`;
- **document standards** for requirements, living specs, ADRs and shaped pitches, with a CI
  format check (`crew check-docs`);
- a **label set**, an issue template for units, and a PR template;
- an **owner inbox** that lists only what waits on you, most blocking first.

How the workflow fits together: [`docs/workflow.md`](docs/workflow.md).

## Install

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), the
[GitHub CLI](https://cli.github.com/) (`gh auth login` done), and Claude Code.

```sh
git clone https://github.com/itzTerra/agent-crew <path-to-agent-crew>

# the CLI
uv tool install --editable <path-to-agent-crew>

# the plugin
claude plugin marketplace add <path-to-agent-crew>
claude plugin install crew@agent-crew
```

## Set up a project

1. Install the Claude Code plugin, if you haven't (`crew agent` refuses to start without it):

   ```sh
   claude plugin marketplace add https://github.com/itzTerra/agent-crew
   claude plugin install crew@agent-crew
   ```

2. In the project's repo, write the crew files:

   ```sh
   crew init --repo <owner>/<name> --owner <your-github-login> --agent <agents-github-login>
   ```

3. Create the labels:

   ```sh
   crew labels sync
   ```

`crew init` writes only files that don't exist yet:

| File | What it is |
|---|---|
| `.crew/config.yaml` | Project settings (see below) |
| `.gitignore` entries | `.crew/state.json` and `.crew/run.json`, the local state |
| `.github/ISSUE_TEMPLATE/unit.md` | The unit template: Goal, Bet, Spec delta, Owns, Depends on, Kind |
| `.github/pull_request_template.md` | Summary, Closes #, Spec changes, How to run, Manual checklist, Review rounds |
| `.github/workflows/crew-docs.yml` | Runs `crew check-docs` and `crew check-owns` on every PR |
| `docs/specs/`, `docs/pitches/`, `docs/adr/` | READMEs and templates for living specs, pitches and ADRs |

`crew labels sync` creates or updates the `crew:` labels on GitHub. Run it again after upgrading.

`crew-docs.yml` installs the CLI from this repo at the tag of the version that wrote it
(`@v0.3.1`), so a change here can't break a project's CI. To upgrade, edit the tag. Projects set
up with an older `crew init` add the `crew check-owns` step by hand, after `crew check-docs`:

```yaml
      - run: crew check-owns ${{ github.event.pull_request.number }}
        env:
          GH_TOKEN: ${{ github.token }}
```

### Settings

`.crew/config.yaml`:

| Key | Default | Meaning |
|---|---|---|
| `repo` | required | `owner/name` on GitHub |
| `owner_login` | required | The product owner's login; only their comments and approvals count as the owner's |
| `agent_login` | required | The login the agents use |
| `paths.requirements` / `specs` / `adr` / `pitches` | `docs/…` | Where each kind of document lives |
| `paths.practices` | `CLAUDE.md` | The project's coding practices file |
| `budget_cap_percent` | 75 | Share of the weekly usage limit agents may use |
| `max_agents` | 2 | Agents at once (the work-in-progress limit) |
| `docker_run` | `""` | Command that runs a branch locally; `{branch}` is replaced |
| `ci_checks` | `[]` | CI checks that must be green before review |
| `owner_decisions_extra` | `[]` | Decisions reserved for the owner, beyond the standard list |
| `merge_rules` | `""` | Merge rules (text or a file path) for the `crew:merge` skill |
| `poll_seconds` | 120 | `crew run`: seconds between looks at GitHub (at least 30) |
| `refine_ahead` | 2 | `crew run`: ready units to keep refined ahead of the workers |
| `stop_grace_minutes` | 15 | `crew run`: how long agents get to commit and push when the run ends |
| `estimates` | see below | `crew run`: minutes per kind of action; a run doesn't start what it can't finish in time |

## CLI

| Command | What it does |
|---|---|
| `crew init` | Write the crew files into a project (never overwrites) |
| `crew labels sync` | Create or update the label set on GitHub |
| `crew check-docs [--strict]` | Check requirements, living specs, ADRs and pitches, and the references between them |
| `crew check-issue (--number N \| --file PATH)` | Check a unit against the definition of ready |
| `crew inbox [--peek]` | What waits on the owner, what merged without them, and dependency cycles; marks the inbox as seen unless `--peek` |
| `crew next [--rough]` | The ready units in the order workers should take them, why each other ready unit is left out, and dependency cycles; with `--rough`, the rough units in refinement order |
| `crew check-owns PR [--range REV_RANGE]` | Check that a PR changes only the paths its unit owns (plus its spec delta's target); with `--range`, the paths come from `git diff --name-only` |
| `crew labels set-state N STATE` | Move an issue and its open PRs (or a PR and its issues) to one state: `rough`, `ready`, `in-progress`, `in-review`, `changes-requested`, `owner-accept`, `owner-stuck`, or `done` to clear them |
| `crew labels check [--fix]` | State labels that disagree; `--fix` removes those left on closed issues and merged PRs |
| `crew agent ROLE [PROMPT] [--model M] [--auto] [--check]` | Start an agent session under the agents' login (see below) |
| `crew usage` | The latest weekly and 5-hour usage reading and its age |
| `crew budget [--week N \| --reset]` | The budget cap in force; raise it for this week, or go back to the default |
| `crew run --until WHEN [--cap N] [--dry-run] [--once]` | Keep agents busy in herdr until an end time (see *Automated runs*) |

Every command takes `--root PATH` (default: the current directory). Exit codes: 0 success,
1 findings, 2 error (one line on stderr: `crew: error: <message>`). Findings print as
`<path>:<line>: <CODE> <message>`; warnings as `<path>:<line>: warning: <CODE> <message>`.

## Running the crew by hand

**Agents work under their own GitHub login** (`agent_login`), not yours. Under your account, PRs
the agents open are yours, so you can't approve them (GitHub forbids approving your own PR) and
owner-facing units can never be merged; it also makes your input and the agents' indistinguishable.

`crew agent <role>` starts an agent session under that login:

1. Store the agents' token at `~/.config/crew/agent-token` with mode 600, or point
   `CREW_AGENT_TOKEN_FILE` at it.
2. Run `crew agent lead --check` once. It prints the GitHub login, the git name and email the
   agents will use, and how they push, and starts nothing; the token itself is never printed.

`crew agent` checks that the token belongs to `agent_login` and refuses to start otherwise; it
never falls back to your `gh` login. The session gets the token only through `GH_TOKEN`, commits
as the agents' noreply address, and pushes over HTTPS with gh's credential helper: your stored git
credentials are not used, `git@github.com:` and `ssh://git@github.com/` remotes are rewritten to
HTTPS, and any other SSH transport is refused, so your SSH key is never used. A token of
`owner_login`, and inherited `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN` and
`GH_HOST` values, are never passed to the session.

To let the crew work without you, see *Automated runs* below. By hand, you start the agents
yourself, for example in herdr panes, one per agent.

**Your session**, with the lead:

```sh
crew agent lead
```

Then ask for the inbox (`crew:inbox`), pitch an idea (`crew:pitch`), or run the kickoff once per
project (`crew:kickoff`). Give feedback on PRs directly on GitHub, or tell the lead and it posts it
for you (`crew:relay`).

**Workers**, each in its own pane:

```sh
crew agent architect "Use crew:refine on the top rough units"
crew agent implementer "Use crew:implement on issue #12"
crew agent reviewer "Use crew:review on PR #14"
```

`crew next` tells you which issues to start, without two workers touching the same paths. Each
agent's model is set in its definition (Opus for lead, architect and reviewer; Sonnet for
designer and implementer); pass `--model sonnet` (`crew agent reviewer --model sonnet "…"`) to review an internal unit more cheaply.

## Automated runs

`crew run` keeps up to `max_agents` agents busy in [herdr](https://herdr.dev) until an end time.
Nothing runs unless you start it; the lead's `crew:run` skill walks you through it.

```sh
crew budget                                   # the cap and the latest usage reading
crew run --until 07:00 --dry-run --once       # what the first tick would do; changes nothing
crew run --until "Mon 07:00"                  # the run, in its own herdr tab
```

`--until` takes `07:00` (the next 07:00), `Mon 07:00` (the next Monday at 07:00) or an ISO 8601
time. `--cap N` sets the weekly budget cap for this run only. `--once` runs a single tick.
`--dry-run` prints, for each tick, the label changes it would make, the agents it would start
(role and prompt) and why everything else waits, and changes nothing.

Every tick (`poll_seconds`) the run reads GitHub and then:

- turns owner feedback on a PR into `crew:changes-requested`, and a red CI on a PR in review into
  the same with a comment naming the checks;
- starts agents in this order: merge approved owner-facing PRs, fix PRs with changes requested,
  review PRs whose CI is green (Sonnet for internal units, Opus for owner-facing ones), follow up
  owner answers on `crew:owner-decision` items, resume units paused by an earlier run, implement
  ready units (the `crew next` order), and refine rough units to keep `refine_ahead` ready;
- each agent runs `crew agent <role> --auto` in its own herdr tab, in Claude Code's auto mode,
  in a worktree under `.crew/worktrees/`. Claude Code asks to trust every new git root, and each
  worktree is one, so the run marks the worktree it just made as trusted in Claude Code's config
  (`~/.claude.json`, or `.claude.json` in `CLAUDE_CONFIG_DIR`), the same flag the dialog's "Yes"
  sets;
- an agent that stops before its unit moves on is nudged once; if it stops again, the run
  comments its last output on the issue and sets `crew:owner-stuck`.

**Stopping.** The run stops at the end time or the budget cap, whichever comes first, and ends
early when everything waits on you. It doesn't start an action it can't finish before the end
(`estimates`, in minutes: merge 15, fix 30, review 20, followup 30, resume 60, implement 90,
refine 20). At the stop, and on Ctrl-C, every agent is told to commit and push its work in
progress and comment what remains; after `stop_grace_minutes` the panes close. Units left
in progress are recorded in `.crew/run.json`, and the next run resumes them. When the 5-hour usage
window is full, the run waits for it to reset and tells the agents to continue. Starting a
second run while one is active is refused; a restarted run adopts the agents still alive.

**Usage and the budget.** The cap counts the whole account's weekly usage, your own sessions
included: 75% by default (`budget_cap_percent`). `crew budget --week 95` raises it until the
weekly limit resets; `crew budget --reset` drops the raise. The reading comes from Claude Code's
status line: `crew agent` sets each session's status line to `crew usage record`, which stores the
latest `rate_limits` reading in `~/.local/state/crew/usage-<account>.json` (`$XDG_STATE_HOME`,
one file per `CLAUDE_CONFIG_DIR`; `CREW_USAGE_FILE` overrides it). With no reading, or one older
than 30 minutes, the run starts at most one agent, whose status line brings a fresh reading.

The crew plugin must be installed for your user (`claude plugin install crew@agent-crew`), or for
the project: run worktrees then get it from the project's `.claude/settings.json`.

## Development

```sh
uv sync
uv run pytest
uv run ruff check
claude plugin validate plugins/crew
```

To keep the repo free of private references, put words that must never be committed in a
gitignored `.private-words` file, one per line; `tests/test_no_private_references.py` fails on
any tracked file that contains one.

## License

MIT
