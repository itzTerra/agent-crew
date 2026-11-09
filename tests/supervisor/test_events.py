from datetime import UTC, datetime, timedelta

from crew.supervisor.events import (
    EVENTS_PATH,
    append_event,
    format_event,
    new_run_id,
    read_events,
    start_log,
)

NOW = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)


def test_start_log_truncates_and_writes_start(tmp_path):
    (tmp_path / ".crew").mkdir()
    append_event(tmp_path, {"run": "old", "type": "item", "at": "x"})
    start_log(tmp_path, "r1", NOW, NOW + timedelta(hours=2), "p9")
    events = read_events(tmp_path)
    assert len(events) == 1
    assert events[0]["type"] == "start"
    assert events[0]["run"] == "r1"
    assert events[0]["pane"] == "p9"


def test_read_events_skips_broken_lines(tmp_path):
    path = tmp_path / EVENTS_PATH
    path.parent.mkdir()
    path.write_text('{"run": "x", "type": "start"}\n{"run": "x", "ty', encoding="utf-8")
    assert len(read_events(tmp_path)) == 1


def test_read_events_missing_file_is_empty(tmp_path):
    assert read_events(tmp_path) == []


def test_format_item_line():
    event = {
        "run": "r1",
        "type": "item",
        "at": NOW.isoformat(),
        "number": 12,
        "ask": "accept",
        "title": "Add login",
        "url": "https://github.com/example/app/pull/40",
    }
    assert format_event(event)[0].endswith(
        "waiting on you: #12 [accept] Add login — https://github.com/example/app/pull/40"
    )


def test_format_end_lists_summary_and_pane():
    event = {
        "run": "r1",
        "type": "end",
        "at": NOW.isoformat(),
        "reason": "end time reached",
        "error": False,
        "pane": "p9",
        "started": ["implement #7 u"],
        "finished": [],
        "stuck": ["review #9 v"],
        "paused": [],
    }
    lines = format_event(event)
    assert lines[0].endswith("run ended: end time reached")
    assert lines[1:] == [
        "Started:",
        "  implement #7 u",
        "Stuck:",
        "  review #9 v",
        "run pane: p9",
    ]


def test_format_reported_is_empty():
    assert format_event({"run": "r1", "type": "reported", "at": NOW.isoformat()}) == []


def test_new_run_id():
    assert new_run_id(42, NOW) == "42-20261109T220000Z"
