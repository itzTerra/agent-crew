"""The run event log: what ``crew run`` appends and ``crew watch`` follows."""

import json
from datetime import UTC, datetime
from pathlib import Path

EVENTS_PATH = Path(".crew") / "run-events.jsonl"  # gitignored; one JSON event per line
SUMMARY_SECTIONS = (
    ("started", "Started"),
    ("finished", "Finished"),
    ("stuck", "Stuck"),
    ("paused", "Paused"),
)


def new_run_id(pid: int, started: datetime) -> str:
    """Name a run by its process id and UTC start time.

    @param pid: process id of the supervisor
    @param started: timezone-aware start time
    @returns the run id, e.g. ``42-20261109T220000Z``
    """
    return f"{pid}-{started.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def start_log(root: Path, run_id: str, at: datetime, until: datetime, pane: str | None) -> None:
    """Begin a new log: drop the previous run's events and write the ``start`` event.

    @param root: project root
    @param run_id: id of the new run
    @param at: timezone-aware start time
    @param until: timezone-aware end time of the run
    @param pane: the pane the run lives in, if any
    """
    path = root / EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    append_event(
        root,
        {"run": run_id, "type": "start", "at": _iso(at), "until": _iso(until), "pane": pane},
    )


def append_event(root: Path, event: dict) -> None:
    """Append one event as one line.

    Not atomic: a reader can see a half-written last line, which `read_events` skips.

    @param root: project root
    @param event: JSON-serializable event
    """
    path = root / EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def read_events(root: Path) -> list[dict]:
    """Read every event that parses.

    @param root: project root
    @returns the events in file order; lines that don't parse are skipped, a missing file gives []
    """
    path = root / EVENTS_PATH
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _local(iso: str, fmt: str) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime(fmt)


def format_event(event: dict) -> list[str]:
    """Render an event as the lines `crew watch` prints.

    @param event: an event as written by the supervisor
    @returns the lines; empty for events that print nothing
    """
    kind = event.get("type")
    when = _local(event["at"], "%H:%M")
    if kind == "item":
        return [
            f"{when} waiting on you: #{event['number']} [{event['ask']}] "
            f"{event['title']} — {event['url']}"
        ]
    if kind == "start":
        return [f"{when} run started, until {_local(event['until'], '%a %H:%M')}"]
    if kind == "end":
        lines = [f"{when} run ended: {event['reason']}"]
        for key, title in SUMMARY_SECTIONS:
            if event.get(key):
                lines.append(f"{title}:")
                lines.extend(f"  {entry}" for entry in event[key])
        if event.get("pane"):
            lines.append(f"run pane: {event['pane']}")
        return lines
    return []
