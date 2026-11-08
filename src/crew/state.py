"""Local, gitignored crew state in ``.crew/state.json``."""

import json
from pathlib import Path

STATE_PATH = Path(".crew") / "state.json"


def read_state(root: Path) -> dict:
    """The state dict; empty when the file is missing or unreadable."""
    try:
        data = json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(root: Path, state: dict) -> None:
    """Replace the state file with ``state``."""
    path = root / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
