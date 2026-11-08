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

In the project's repo:

```sh
crew init --repo <owner>/<name> --owner <your-github-login> --agent <agents-github-login>
crew labels sync
```

`crew init` writes only files that don't exist yet:

| File | What it is |
|---|---|
| `.crew/config.yaml` | Project settings (see below) |
| `.gitignore` entry | `.crew/state.json`, the local state |
| `.github/ISSUE_TEMPLATE/unit.md` | The unit template: Goal, Bet, Spec delta, Owns, Depends on, Kind |
| `.github/pull_request_template.md` | Summary, Closes #, Spec changes, How to run, Manual checklist, Review rounds |
| `.github/workflows/crew-docs.yml` | Runs `crew check-docs` on every PR |
| `docs/specs/`, `docs/pitches/`, `docs/adr/` | READMEs and templates for living specs, pitches and ADRs |

`crew labels sync` creates or updates the `crew:` labels on GitHub. Run it again after upgrading.

`crew-docs.yml` installs the CLI from this repo at the tag of the version that wrote it
(`@v0.2.0`), so a change here can't break a project's CI. To upgrade, edit the tag.

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

## CLI

| Command | What it does |
|---|---|
| `crew init` | Write the crew files into a project (never overwrites) |
| `crew labels sync` | Create or update the label set on GitHub |
| `crew check-docs [--strict]` | Check requirements, living specs, ADRs and pitches, and the references between them |
| `crew check-issue (--number N \| --file PATH)` | Check a unit against the definition of ready |
| `crew inbox [--peek]` | What waits on the owner, what merged without them, and dependency cycles; marks the inbox as seen unless `--peek` |
| `crew next [--rough]` | The ready units in the order workers should take them, and dependency cycles; with `--rough`, the rough units in refinement order |

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

Automated runs come in a later version. Until then you start the agents yourself, for example in
herdr panes, one per agent.

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
