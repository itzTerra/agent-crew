"""Command-line entry point.

Every expected failure prints one line ``crew: error: <message>`` to stderr and exits 2.
Document or ready findings exit 1; success exits 0.
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from crew import __version__
from crew.agent import AgentError
from crew.config import ConfigError, load_config
from crew.docs.markdown import DocumentReadError
from crew.findings import Finding, has_errors
from crew.github import GitHub, GitHubError
from crew.owns import OwnsError
from crew.supervisor.herdr import Herdr, HerdrError
from crew.supervisor.loop import RunError
from crew.supervisor.worktrees import WorktreeError

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class CliError(Exception):
    """An expected failure, reported as a single error line."""


class _Parser(argparse.ArgumentParser):
    """Argument errors become one ``crew: error:`` line, like every other failure."""

    def error(self, message: str):
        raise CliError(f"{self.prog.removeprefix('crew ')}: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="crew", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"crew {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    init = commands.add_parser("init", help="write the crew files into a project")
    init.add_argument("--repo", required=True, help="GitHub repo as owner/name")
    init.add_argument("--owner", required=True, help="the product owner's GitHub login")
    init.add_argument("--agent", required=True, help="the agents' GitHub login")
    init.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    init.set_defaults(handler=_cmd_init)

    docs = commands.add_parser("check-docs", help="check requirements, specs, ADRs and pitches")
    docs.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    docs.add_argument("--strict", action="store_true", help="treat uncited requirements as errors")
    docs.set_defaults(handler=_cmd_check_docs)

    issue = commands.add_parser("check-issue", help="check a unit against the Definition of Ready")
    source = issue.add_mutually_exclusive_group(required=True)
    source.add_argument("--number", type=int, help="issue number on GitHub")
    source.add_argument("--file", type=Path, help="a file holding the issue body")
    issue.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    issue.set_defaults(handler=_cmd_check_issue)

    owns = commands.add_parser("check-owns", help="check a PR changes only its unit's owned paths")
    owns.add_argument("pr", type=int, help="pull request number")
    owns.add_argument("--range", help="take the paths from `git diff --name-only RANGE` instead")
    owns.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    owns.set_defaults(handler=_cmd_check_owns)

    labels = commands.add_parser("labels", help="manage the crew label set")
    label_commands = labels.add_subparsers(dest="labels_command", metavar="<action>", required=True)
    sync = label_commands.add_parser("sync", help="create or update the crew labels on GitHub")
    sync.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    sync.set_defaults(handler=_cmd_labels_sync)
    set_state = label_commands.add_parser(
        "set-state", help="move an issue and its PRs (or a PR and its issue) to one state"
    )
    set_state.add_argument("number", type=int, help="issue or PR number")
    set_state.add_argument("state", help="rough, ready, in-progress, in-review, …, or done")
    set_state.add_argument(
        "--root", type=Path, default=Path.cwd(), help="project root (default: .)"
    )
    set_state.set_defaults(handler=_cmd_labels_set_state)
    check = label_commands.add_parser("check", help="find state labels that disagree")
    check.add_argument("--fix", action="store_true", help="remove labels left on closed items")
    check.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    check.set_defaults(handler=_cmd_labels_check)

    inbox = commands.add_parser("inbox", help="show what is waiting on the owner")
    inbox.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    inbox.add_argument(
        "--peek",
        action="store_true",
        help="don't mark the inbox as seen (for agents; the owner's session omits this)",
    )
    inbox.set_defaults(handler=_cmd_inbox)

    next_ = commands.add_parser("next", help="show the ready units in pick order")
    next_.add_argument(
        "--rough", action="store_true", help="list the rough units in refinement order instead"
    )
    next_.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    next_.set_defaults(handler=_cmd_next)

    agent = commands.add_parser("agent", help="start an agent session as the agents' GitHub login")
    agent.add_argument("role", help="lead, architect, designer, implementer or reviewer")
    agent.add_argument("prompt", nargs="?", help="the first message for the agent")
    agent.add_argument("--model", help="override the agent's model")
    agent.add_argument(
        "--check", action="store_true", help="print the identity the agent would use; start nothing"
    )
    agent.add_argument(
        "--auto", action="store_true", help="run in Claude Code's auto permission mode"
    )
    agent.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    agent.set_defaults(handler=_cmd_agent)

    budget = commands.add_parser("budget", help="show or raise this week's budget cap")
    change = budget.add_mutually_exclusive_group()
    change.add_argument(
        "--week", type=int, metavar="N", help="cap this week at N%% of the weekly limit (1-100)"
    )
    change.add_argument("--reset", action="store_true", help="go back to the default cap")
    budget.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    budget.set_defaults(handler=_cmd_budget)

    run = commands.add_parser("run", help="keep crew agents busy in herdr until an end time")
    run.add_argument(
        "--until", required=True, metavar="WHEN", help="end time: 07:00, Mon 07:00 or ISO 8601"
    )
    run.add_argument("--cap", type=int, metavar="N", help="weekly budget cap for this run, in %%")
    run.add_argument(
        "--dry-run", action="store_true", help="show what each tick would do; change nothing"
    )
    run.add_argument("--once", action="store_true", help="run a single tick")
    run.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    run.set_defaults(handler=_cmd_run)

    usage = commands.add_parser("usage", help="show the latest weekly usage reading")
    usage_commands = usage.add_subparsers(dest="usage_command", metavar="<action>")
    record = usage_commands.add_parser(
        "record", help="the agents' status-line command: store the reading from stdin"
    )
    record.set_defaults(handler=_cmd_usage_record)
    usage.set_defaults(handler=_cmd_usage)
    return parser


def make_github(repo: str) -> GitHub:
    """Build the GitHub client; a seam for tests."""
    return GitHub(repo)


def make_herdr() -> Herdr:
    """Build the herdr driver; a seam for tests."""
    return Herdr()


def run_clock() -> datetime:
    """The run's clock; a seam for tests."""
    return datetime.now(UTC)


def run_sleep(seconds: float) -> None:
    """The run's sleep; a seam for tests."""
    time.sleep(seconds)


def _cmd_labels_sync(args: argparse.Namespace) -> int:
    from crew.labels import LABELS

    config = load_config(args.root)
    written = make_github(config.repo).ensure_labels(LABELS)
    for name in written:
        print(f"synced {name}")
    if not written:
        print("labels already up to date")
    return EXIT_OK


def _cmd_labels_set_state(args: argparse.Namespace) -> int:
    from crew.labels import DONE, STATES, set_state

    if args.state not in STATES:
        raise CliError(f"unknown state {args.state!r}; choose one of {', '.join(STATES)}")
    config = load_config(args.root)
    shown = "done" if args.state == DONE else f"crew:{args.state}"
    try:
        changed = set_state(make_github(config.repo), args.number, args.state)
    except ValueError as exc:
        raise CliError(str(exc)) from None
    for number in changed:
        print(f"#{number}: {shown}")
    return EXIT_OK


def _fetch_label_problems(github: GitHub, open_issues=None, open_prs=None, merged=None):
    from crew.labels import label_problems

    return label_problems(
        github.list_issues("open") if open_issues is None else open_issues,
        github.list_issues("closed"),
        github.list_prs("open") if open_prs is None else open_prs,
        github.list_prs("merged") if merged is None else merged,
    )


def _cmd_labels_check(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    github = make_github(config.repo)
    problems = _fetch_label_problems(github)
    left = 0
    for problem in problems:
        print(f"#{problem.number}: {problem.message}")
        if args.fix and problem.fix_remove:
            github.set_labels(problem.number, [], list(problem.fix_remove))
            print(f"fixed #{problem.number}")
        else:
            left += 1
    if not problems:
        print("no label problems")
    return EXIT_FINDINGS if left else EXIT_OK


def _report(findings: list[Finding], root: Path) -> int:
    """Print findings and return the exit code: 1 if any is an error, else 0."""
    for finding in findings:
        print(finding.format(root))
    return EXIT_FINDINGS if has_errors(findings) else EXIT_OK


def _cmd_check_docs(args: argparse.Namespace) -> int:
    from crew.docs.check import check_docs

    config = load_config(args.root)
    return _report(check_docs(args.root, config, strict=args.strict), args.root)


def _cmd_init(args: argparse.Namespace) -> int:
    from crew.init import init_project

    written = init_project(args.root, args.repo, args.owner, args.agent)
    for path in written:
        print(f"wrote {path.relative_to(args.root).as_posix()}")
    if not written:
        print("nothing to write: every crew file already exists")
    from crew.agent import PLUGIN_INSTALL, plugin_installed

    if plugin_installed(os.environ, args.root) is not True:
        print(f"next: install the Claude Code plugin: {PLUGIN_INSTALL}")
    return EXIT_OK


def _cmd_check_issue(args: argparse.Namespace) -> int:
    from crew.units import check_unit

    config = load_config(args.root)
    if args.file is not None:
        try:
            body = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(f"cannot read {args.file}: {exc.strerror}") from None
        except UnicodeDecodeError:
            raise CliError(f"{args.file} is not UTF-8 text") from None
    else:
        body = make_github(config.repo).issue_body(args.number)
    return _report(check_unit(body, args.root, config), args.root)


def _cmd_check_owns(args: argparse.Namespace) -> int:
    from crew.owns import changed_paths, outside_owns
    from crew.units import delta_target, parse_unit_body

    config = load_config(args.root)
    github = make_github(config.repo)
    issues = github.pr_linked_issues(args.pr)
    if not issues:
        print(f"PR #{args.pr} closes no issue; nothing to check")
        return EXIT_OK
    owned: list[str] = []
    allowed: list[str] = []
    missing = []
    for number in issues:
        unit = parse_unit_body(github.issue_body(number))
        owned += unit.owns
        if not unit.owns:
            missing.append(number)
        if target := delta_target(unit.delta_text):
            allowed.append(target)
    for number in missing:
        print(f"<issue>:1: OWNS-NONE #{number} lists no owned paths")
    paths = changed_paths(args.root, args.range) if args.range else github.pr_files(args.pr)
    outside = outside_owns(paths, owned, allowed)
    names = ", ".join(f"#{n}" for n in issues)
    for path in outside:
        print(f"{path}:1: OWNS-OUTSIDE not in the Owns of {names}")
    if missing or outside:
        return EXIT_FINDINGS
    print(f"all {len(paths)} changed paths are inside the Owns of {names}")
    return EXIT_OK


def _cmd_inbox(args: argparse.Namespace) -> int:
    from crew.graph import build_units, find_cycles
    from crew.inbox import merged_without_owner, owner_inbox, parked_ideas
    from crew.state import read_state, write_state

    config = load_config(args.root)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    github = make_github(config.repo)
    open_issues = github.list_issues("open")
    units = build_units(open_issues)
    open_prs = github.list_prs("open")
    merged = github.list_prs("merged")
    state = read_state(args.root)
    since = state.get("last_inbox")

    print("Waiting on you")
    items = owner_inbox(units, open_prs)
    for item in items:
        print(f"  #{item.number} [{item.ask}] blocks {item.blocks} — {item.title} — {item.url}")
    if not items:
        print("  nothing")

    print()
    print(f"Merged without you since {since}" if since else "Merged without you (all time)")
    merged_items = merged_without_owner(merged, since)
    for pr in merged_items:
        print(f"  #{pr['number']} {pr.get('title', '')} — {pr.get('url', '')}")
    if not merged_items:
        print("  nothing")
    if ideas := parked_ideas(units):
        print()
        print(f"Parked ideas: {ideas}")

    _print_cycles(find_cycles(units))
    problems = _fetch_label_problems(github, open_issues, open_prs, merged)
    if problems:
        print()
        print("Label problems")
        for problem in problems:
            print(f"  #{problem.number}: {problem.message}")
    if not args.peek:
        try:
            write_state(args.root, {**state, "last_inbox": now})
        except OSError as exc:
            raise CliError(f"cannot write .crew/state.json: {exc.strerror}") from None
    return EXIT_OK


def _print_cycles(cycles: list[list[int]]) -> None:
    if cycles:
        print()
        print("Dependency cycles (these units can't start until a dependency is removed)")
        for cycle in cycles:
            print("  " + " → ".join(f"#{n}" for n in [*cycle, cycle[0]]))


def _cmd_next(args: argparse.Namespace) -> int:
    from crew.graph import BUSY, RUNNING, build_units, find_cycles, ready_report, rough_order

    config = load_config(args.root)
    units = build_units(make_github(config.repo).list_issues("open"))
    if args.rough:
        picks = rough_order(units)
        for number in picks:
            print(f"#{number} {units[number].title}")
        if not picks:
            print("nothing rough")
        return EXIT_OK
    running = [n for n, u in units.items() if RUNNING in u.labels]
    busy = [n for n, u in units.items() if n not in running and u.labels & BUSY]
    picks, skipped = ready_report(units, running, config.max_agents, busy)
    for number in picks:
        print(f"#{number} {units[number].title}")
    if not picks:
        print("nothing ready")
    if skipped:
        print()
        print("Left out")
        for item in skipped:
            print(f"  #{item.number} {units[item.number].title} — {item.reason}")
    _print_cycles(find_cycles(units))
    return EXIT_OK


def _cmd_agent(args: argparse.Namespace) -> int:
    from crew.agent import run_agent

    config = load_config(args.root)
    run_agent(
        args.role,
        args.prompt,
        args.model,
        config.agent_login,
        config.owner_login,
        args.check,
        args.root,
        args.auto,
    )
    return EXIT_OK


def _cmd_budget(args: argparse.Namespace) -> int:
    from crew.budget import OVERRIDE_KEY, effective_cap, week_override
    from crew.config import BUDGET_MAX, BUDGET_MIN
    from crew.state import read_state
    from crew.usage import read_usage, usage_line, usage_path

    config = load_config(args.root)
    now = datetime.now(UTC)
    reading = read_usage(usage_path(os.environ))
    state = read_state(args.root)
    if args.week is not None:
        if not BUDGET_MIN <= args.week <= BUDGET_MAX:
            raise CliError(f"--week must be {BUDGET_MIN}–{BUDGET_MAX}, got {args.week}")
        if reading is None or reading.week_resets_at <= now:
            raise CliError(
                "no usage reading yet, so the week's reset time is unknown; "
                "start any crew agent first"
            )
        state = {**state, OVERRIDE_KEY: week_override(args.week, reading)}
        _write_state(args.root, state)
    elif args.reset:
        state = {k: v for k, v in state.items() if k != OVERRIDE_KEY}
        _write_state(args.root, state)
    percent, source = effective_cap(config, state, now)
    if source == "default":
        print(f"cap {percent}% (default)")
    else:
        until = datetime.fromisoformat(state[OVERRIDE_KEY]["until"])
        local = until.astimezone().strftime("%a %H:%M")
        print(f"cap {percent}% this week (until {local}), then {config.budget_cap_percent}%")
    print(usage_line(reading, now))
    return EXIT_OK


def _write_state(root: Path, state: dict) -> None:
    from crew.state import write_state

    try:
        write_state(root, state)
    except OSError as exc:
        raise CliError(f"cannot write .crew/state.json: {exc.strerror}") from None


def _cmd_run(args: argparse.Namespace) -> int:
    from crew.config import BUDGET_MAX, BUDGET_MIN
    from crew.supervisor.loop import Supervisor
    from crew.supervisor.until import parse_until

    root = args.root.resolve()  # git reports worktrees by absolute path
    config = load_config(root)
    if args.cap is not None and not BUDGET_MIN <= args.cap <= BUDGET_MAX:
        raise CliError(f"--cap must be {BUDGET_MIN}–{BUDGET_MAX}, got {args.cap}")
    clock, sleep = run_clock, run_sleep
    try:
        until = parse_until(args.until, clock())
    except ValueError as exc:
        raise CliError(f"--until: {exc}") from None
    supervisor = Supervisor(
        root,
        config,
        make_github(config.repo),
        make_herdr(),
        until=until,
        cap=args.cap,
        dry_run=args.dry_run,
        clock=lambda: clock(),
        sleep=lambda seconds: sleep(seconds),
    )
    return supervisor.run(once=args.once)


def _cmd_usage(args: argparse.Namespace) -> int:
    from crew.usage import read_usage, usage_line, usage_path

    print(usage_line(read_usage(usage_path(os.environ)), datetime.now(UTC)))
    return EXIT_OK


def _cmd_usage_record(args: argparse.Namespace) -> int:
    from crew.usage import NO_DATA, record_statusline, usage_path

    try:
        payload = sys.stdin.read()
        print(record_statusline(payload, usage_path(os.environ), datetime.now(UTC)))
    except Exception:  # noqa: BLE001 — a status-line command must never fail
        print(NO_DATA)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return EXIT_OK
        return handler(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    except (
        AgentError,
        CliError,
        ConfigError,
        GitHubError,
        DocumentReadError,
        OwnsError,
        RunError,
        HerdrError,
        WorktreeError,
    ) as exc:
        print(f"crew: error: {exc}", file=sys.stderr)
    except OSError as exc:
        where = f" ({exc.filename})" if exc.filename else ""
        print(f"crew: error: {exc.strerror or exc}{where}", file=sys.stderr)
    return EXIT_ERROR
