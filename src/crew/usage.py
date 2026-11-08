"""Weekly and 5-hour usage, read from Claude Code's status-line input.

``crew agent`` sets each session's status line to ``crew usage record``. Claude Code pipes the
status-line JSON to it; when the JSON has ``rate_limits``, the latest reading is stored in a
per-account file that ``crew budget`` and ``crew run`` read.
"""

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

USAGE_STALE = timedelta(minutes=30)
USAGE_FILE_ENV = "CREW_USAGE_FILE"
NO_DATA = "crew · no usage data"


@dataclass(frozen=True)
class Usage:
    """One usage reading. Times are aware, in UTC."""

    week_percent: float
    week_resets_at: datetime
    five_hour_percent: float
    five_hour_resets_at: datetime
    recorded_at: datetime


def usage_path(env: Mapping[str, str]) -> Path:
    """Where the reading for this environment's Claude account is kept.

    ``$CREW_USAGE_FILE`` when set; otherwise
    ``$XDG_STATE_HOME/crew/usage-<account>.json`` (``~/.local/state`` by default), where
    ``<account>`` is the last part of ``$CLAUDE_CONFIG_DIR``, or ``default`` when unset.
    """
    if env.get(USAGE_FILE_ENV):
        return Path(env[USAGE_FILE_ENV]).expanduser()
    state = Path(env.get("XDG_STATE_HOME") or "~/.local/state").expanduser()
    config_dir = env.get("CLAUDE_CONFIG_DIR", "").rstrip("/")
    account = Path(config_dir).name if config_dir else "default"
    return state / "crew" / f"usage-{account}.json"


def _time(value) -> datetime:
    if isinstance(value, bool):
        raise ValueError("not a time")
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def _percent(value) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("not a number")
    return float(value)


def _parse_limits(limits: dict, now: datetime) -> Usage:
    week, five = limits["seven_day"], limits["five_hour"]
    return Usage(
        week_percent=_percent(week["used_percentage"]),
        week_resets_at=_time(week["resets_at"]),
        five_hour_percent=_percent(five["used_percentage"]),
        five_hour_resets_at=_time(five["resets_at"]),
        recorded_at=now.astimezone(UTC),
    )


def _number(value: float) -> str:
    return f"{value:g}"


def _local(moment: datetime, fmt: str) -> str:
    return moment.astimezone().strftime(fmt)


def describe(usage: Usage) -> str:
    """``week 41% (resets Mon 09:00) · 5h 12%``, in local time."""
    return (
        f"week {_number(usage.week_percent)}% (resets {_local(usage.week_resets_at, '%a %H:%M')})"
        f" · 5h {_number(usage.five_hour_percent)}%"
    )


def record_statusline(payload: str, path: Path, now: datetime) -> str:
    """Store the reading from one status-line input and return the status-line text.

    Never raises: bad input, or input without ``rate_limits``, writes nothing and returns
    the no-data text. The file is replaced atomically (a temp file, then a rename).
    """
    try:
        data = json.loads(payload)
        usage = _parse_limits(data["rate_limits"], now)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
        return NO_DATA
    try:
        _write(path, usage)
    except OSError:
        pass  # the status line still shows the reading
    return f"crew · {describe(usage)}"


def _write(path: Path, usage: Usage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "week_percent": usage.week_percent,
        "week_resets_at": usage.week_resets_at.isoformat(),
        "five_hour_percent": usage.five_hour_percent,
        "five_hour_resets_at": usage.five_hour_resets_at.isoformat(),
        "recorded_at": usage.recorded_at.isoformat(),
    }
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(record, out)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_usage(path: Path) -> Usage | None:
    """The stored reading, or None when the file is missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Usage(
            week_percent=_percent(data["week_percent"]),
            week_resets_at=_time(data["week_resets_at"]),
            five_hour_percent=_percent(data["five_hour_percent"]),
            five_hour_resets_at=_time(data["five_hour_resets_at"]),
            recorded_at=_time(data["recorded_at"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def is_fresh(usage: Usage | None, now: datetime) -> bool:
    """Whether a reading exists and is at most ``USAGE_STALE`` old."""
    return usage is not None and now - usage.recorded_at <= USAGE_STALE


def usage_line(usage: Usage | None, now: datetime) -> str:
    """The ``crew usage`` line: the reading and its age, or how one appears."""
    if usage is None:
        return (
            "no usage reading yet; it appears once a crew agent session has drawn its status line"
        )
    minutes = max(0, int((now - usage.recorded_at).total_seconds() // 60))
    stale = "" if is_fresh(usage, now) else " (stale)"
    return f"{describe(usage)} · read {minutes} min ago{stale}"
