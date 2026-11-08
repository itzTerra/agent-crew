"""Command-line entry point.

Every expected failure prints one line ``crew: error: <message>`` to stderr and exits 2.
Document or ready findings exit 1; success exits 0.
"""

import argparse
import sys
from pathlib import Path

from crew import __version__
from crew.config import ConfigError, load_config
from crew.findings import Finding, has_errors

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class CliError(Exception):
    """An expected failure, reported as a single error line."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crew", description=__doc__.splitlines()[0])
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
    return parser


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
    else:
        raise CliError("--number needs GitHub access, which is not available yet")
    return _report(check_unit(body, args.root, config), args.root)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_OK
    try:
        return handler(args)
    except (CliError, ConfigError) as exc:
        print(f"crew: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
