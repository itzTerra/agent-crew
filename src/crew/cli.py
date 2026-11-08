"""Command-line entry point.

Every expected failure prints one line ``crew: error: <message>`` to stderr and exits 2.
Document or ready findings exit 1; success exits 0.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from crew import __version__
from crew.config import ConfigError, load_config
from crew.docs.markdown import DocumentReadError
from crew.findings import Finding, has_errors
from crew.github import GitHub, GitHubError

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

RUNNING = "crew:in-progress"
# Units with an open PR: they hold their owned paths but no agent slot.
BUSY = frozenset(
    {"crew:in-review", "crew:changes-requested", "crew:owner-accept", "crew:owner-stuck"}
)


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

    labels = commands.add_parser("labels", help="manage the crew label set")
    label_commands = labels.add_subparsers(dest="labels_command", metavar="<action>", required=True)
    sync = label_commands.add_parser("sync", help="create or update the crew labels on GitHub")
    sync.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: .)")
    sync.set_defaults(handler=_cmd_labels_sync)

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
    return parser


def make_github(repo: str) -> GitHub:
    """Build the GitHub client; a seam for tests."""
    return GitHub(repo)


def _cmd_labels_sync(args: argparse.Namespace) -> int:
    from crew.labels import LABELS

    config = load_config(args.root)
    written = make_github(config.repo).ensure_labels(LABELS)
    for name in written:
        print(f"synced {name}")
    if not written:
        print("labels already up to date")
    return EXIT_OK


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


def _cmd_inbox(args: argparse.Namespace) -> int:
    from crew.graph import build_units, find_cycles
    from crew.inbox import merged_without_owner, owner_inbox
    from crew.state import read_state, write_state

    config = load_config(args.root)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    github = make_github(config.repo)
    units = build_units(github.list_issues("open"))
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

    _print_cycles(find_cycles(units))
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
    from crew.graph import build_units, find_cycles, next_ready, rough_order

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
    picks = next_ready(units, running, config.max_agents, busy)
    for number in picks:
        print(f"#{number} {units[number].title}")
    if not picks:
        print("nothing ready")
    _print_cycles(find_cycles(units))
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
    except (CliError, ConfigError, GitHubError, DocumentReadError) as exc:
        print(f"crew: error: {exc}", file=sys.stderr)
    except OSError as exc:
        where = f" ({exc.filename})" if exc.filename else ""
        print(f"crew: error: {exc.strerror or exc}{where}", file=sys.stderr)
    return EXIT_ERROR
