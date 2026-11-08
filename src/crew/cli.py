"""Command-line entry point.

Every expected failure prints one line ``crew: error: <message>`` to stderr and exits 2.
Document or ready findings exit 1; success exits 0.
"""

import argparse
import sys

from crew import __version__

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class CliError(Exception):
    """An expected failure, reported as a single error line."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crew", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"crew {__version__}")
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


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
    except CliError as exc:
        print(f"crew: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
