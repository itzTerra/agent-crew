"""``crew watch``: follow the active run's event log for the lead."""

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from crew.supervisor.events import append_event, format_event, read_events
from crew.supervisor.loop import RUN_PATH, is_crew_run

POLL = 2  # seconds between reads: the lead is told within seconds, and the file stays cheap
START_WAIT = 60  # seconds to wait for a run to appear; covers a run that is still starting

CURSOR_PATH = Path(".crew") / "watch.json"  # gitignored; where the last `crew watch` stopped
NOTHING_TO_WATCH = "nothing to watch: no active run and no unreported end"
LIVE_MARKER = "--- live from here"


def _read_run(root: Path) -> dict:
    try:
        data = json.loads((root / RUN_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_cursor(root: Path, run: object, total: int) -> int | None:
    """The number of events already handled for ``run``, or None if there is no usable cursor."""
    try:
        data = json.loads((root / CURSOR_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("run") != run:
        return None
    handled = data.get("handled")
    if isinstance(handled, bool) or not isinstance(handled, int) or not 0 <= handled <= total:
        return None
    return handled


def _write_cursor(root: Path, run: object, handled: int) -> None:
    path = root / CURSOR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"run": run, "handled": handled}) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _live_pid(root: Path, alive: Callable[[int], bool]) -> int | None:
    pid = _read_run(root).get("pid")
    return pid if isinstance(pid, int) and alive(pid) else None


def _has_unreported_end(events: list[dict]) -> bool:
    reported = {event.get("run") for event in events if event.get("type") == "reported"}
    return any(event.get("type") == "end" and event.get("run") not in reported for event in events)


def run_status(
    root: Path, alive: Callable[[int], bool] = is_crew_run
) -> Literal["active", "ended", "none"]:
    """Say whether there is a run to watch.

    @param root: project root
    @param alive: tells whether a pid is a live ``crew run``
    @returns ``active`` with a live run, ``ended`` with an end nobody reported, else ``none``
    """
    if _live_pid(root, alive) is not None:
        return "active"
    if _has_unreported_end(read_events(root)):
        return "ended"
    return "none"


def _is_started(root: Path, events: list[dict], pid: int | None) -> bool:
    if pid is None or not events or events[0].get("type") != "start":
        return False
    return _read_run(root).get("run_id") == events[0].get("run")


def watch(
    root: Path,
    replay: bool,
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[int], bool] = is_crew_run,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Follow the latest run: print its new owner items, then its end.

    @param root: project root
    @param replay: print every event so far, then a marker, instead of resuming from the
        cursor in ``.crew/watch.json`` (or, without one for this run, skipping old items)
    @param out: prints one line
    @param sleep: waits the given seconds
    @param alive: tells whether a pid is a live ``crew run``
    @param clock: monotonic seconds, used only to bound the wait for a run
    @returns 0 after reporting the end, 1 if there was nothing to watch, 2 if the run died
    """
    waited_from = clock()
    while True:
        events = read_events(root)
        pid = _live_pid(root, alive)
        if pid is not None:
            # a live run whose start isn't in the file yet makes any old end stale
            if _is_started(root, events, pid):
                break
        elif _has_unreported_end(events):
            break
        if clock() - waited_from >= START_WAIT:
            out(NOTHING_TO_WATCH)
            return 1
        sleep(POLL)

    run = events[0].get("run") if events else None

    def emit(batch: list[dict], offset: int, skip_items: bool = False) -> bool:
        """Print a batch that starts at event ``offset``; True once it held the run's end."""
        for index, event in enumerate(batch, start=offset + 1):
            lines: list[str] = []
            if not (skip_items and event.get("type") == "item"):
                try:
                    lines = format_event(event)
                except (KeyError, ValueError, TypeError):
                    pass  # one malformed line must not stop the watch
            for line in lines:
                out(line)
            ended = bool(lines) and event.get("type") == "end"
            if ended:
                append_event(root, {"run": event.get("run"), "type": "reported", "at": _now()})
            _write_cursor(root, run, index)
            if ended:
                return True
        return False

    resumed = None if replay else _read_cursor(root, run, len(events))
    if replay:
        done = emit(events, 0)
        if not done:
            out(LIVE_MARKER)
    elif resumed is not None:
        done = emit(events[resumed:], resumed)
    else:
        done = emit(events, 0, skip_items=True)
    if done:
        return 0
    handled = len(events)

    while True:
        if pid is None or not alive(pid):
            events = read_events(root)
            if emit(events[handled:], handled):
                return 0
            out(f"run stopped without an end report (pid {pid}); its pane shows why")
            return 2
        sleep(POLL)
        events = read_events(root)
        done = emit(events[handled:], handled)
        handled = len(events)
        if done:
            return 0


def _now() -> str:
    return datetime.now(UTC).isoformat()
