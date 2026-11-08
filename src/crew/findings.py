"""Findings reported by the document and ready checks."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Finding:
    """One problem at one line of one document."""

    path: Path
    line: int
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"

    def format(self, root: Path) -> str:
        """Render as ``<relative path>:<line>: [warning: ]<CODE> <message>``."""
        try:
            shown = self.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            shown = self.path.as_posix()
        prefix = "warning: " if self.severity == "warning" else ""
        return f"{shown}:{self.line}: {prefix}{self.code} {self.message}"


def has_errors(findings: list[Finding]) -> bool:
    """Whether any finding is an error rather than a warning."""
    return any(f.severity == "error" for f in findings)
