import json

import pytest

from crew.cli import build_parser
from crew.supervisor.events import EVENTS_PATH, append_event, read_events
from crew.supervisor.loop import RUN_PATH
from crew.watch import CURSOR_PATH, START_WAIT, run_status, watch

RUN = "1-20261109T220000Z"
AT = "2026-11-09T22:00:00+00:00"


def ev(kind, run=RUN, **extra):
    return {"run": run, "type": kind, "at": AT, **extra}


def item(number):
    return ev("item", number=number, ask="review", title=f"thing {number}", url=f"u/{number}")


def end(run=RUN):
    return ev("end", run=run, reason="time is up")


def start(run=RUN):
    return ev("start", run=run, until=AT, pane=None)


def write_run(root, run=RUN, pid=1):
    path = root / RUN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "run_id": run}))


def write_events(root, *events):
    path = root / EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    for event in events:
        append_event(root, event)


def never_alive(pid):
    return False


def always_alive(pid):
    return True


class Lines(list):
    def __call__(self, line):
        self.append(line)


def test_status_none_active_ended(tmp_path):
    assert run_status(tmp_path, always_alive) == "none"
    write_events(tmp_path, start(), end())
    assert run_status(tmp_path, never_alive) == "ended"
    write_run(tmp_path)
    assert run_status(tmp_path, always_alive) == "active"
    append_event(tmp_path, ev("reported"))
    assert run_status(tmp_path, never_alive) == "none"


def test_watch_prints_new_items_and_end_then_marks_reported(tmp_path):
    write_events(tmp_path, start(), item(1))
    write_run(tmp_path)
    steps = [lambda: append_event(tmp_path, item(2)), lambda: append_event(tmp_path, end())]
    out = Lines()
    code = watch(tmp_path, False, out, lambda s: steps.pop(0)(), always_alive)
    text = "\n".join(out)
    assert code == 0
    assert "#2" in text and "#1" not in text
    assert "run ended: time is up" in text
    assert read_events(tmp_path)[-1]["type"] == "reported"


def test_watch_replay_prints_old_items_then_marker(tmp_path):
    write_events(tmp_path, start(), item(1))
    write_run(tmp_path)
    steps = [lambda: append_event(tmp_path, end())]
    out = Lines()
    assert watch(tmp_path, True, out, lambda s: steps.pop(0)(), always_alive) == 0
    marker = out.index("--- live from here")
    assert any("#1" in line for line in out[:marker])
    assert any("run ended" in line for line in out[marker:])


def test_watch_reports_unwatched_end_once(tmp_path):
    write_events(tmp_path, start(), end())
    ticks = iter(range(0, 1000, START_WAIT))
    out = Lines()
    assert watch(tmp_path, False, out, lambda s: None, never_alive, lambda: next(ticks)) == 0
    assert any("run ended" in line for line in out)
    out = Lines()
    assert watch(tmp_path, False, out, lambda s: None, never_alive, lambda: next(ticks)) == 1
    assert out[0].startswith("nothing to watch")


def test_watch_waits_for_run_to_start(tmp_path):
    new = "2-20261110T000000Z"
    write_events(tmp_path, start(), end(), ev("reported"))

    def begin():
        write_events(tmp_path, start(new))
        write_run(tmp_path, new, pid=2)

    steps = [begin, lambda: append_event(tmp_path, end(new))]
    out = Lines()
    assert watch(tmp_path, False, out, lambda s: steps.pop(0)(), always_alive) == 0
    assert any("run ended" in line for line in out)


def test_watch_dead_run_without_end(tmp_path):
    write_events(tmp_path, start())
    write_run(tmp_path, pid=7)
    answers = iter([True, False])
    out = Lines()
    code = watch(tmp_path, False, out, lambda s: None, lambda pid: next(answers))
    assert code == 2
    assert out[-1] == "run stopped without an end report (pid 7); its pane shows why"


def test_watch_skips_events_without_a_time(tmp_path):
    write_events(tmp_path, start(), {"run": RUN, "type": "item"})
    write_run(tmp_path)
    steps = [lambda: append_event(tmp_path, end())]
    out = Lines()
    assert watch(tmp_path, True, out, lambda s: steps.pop(0)(), always_alive) == 0


def test_watch_command_is_registered():
    args = build_parser().parse_args(["watch", "--replay"])
    assert args.replay is True and args.status is False


def test_watch_waits_for_new_run_despite_old_unreported_end(tmp_path):
    new = "2-20261110T000000Z"
    write_events(tmp_path, start(), end())
    write_run(tmp_path, new, pid=2)

    def begin():
        write_events(tmp_path, start(new))

    steps = [begin, lambda: append_event(tmp_path, end(new))]
    out = Lines()
    assert watch(tmp_path, False, out, lambda s: steps.pop(0)(), always_alive) == 0
    events = read_events(tmp_path)
    assert events[-1]["type"] == "reported" and events[-1]["run"] == new
    assert sum("run ended" in line for line in out) == 1


def interrupted(steps):
    """A sleep that runs the steps, then raises KeyboardInterrupt like an expired Monitor."""

    def sleep(seconds):
        if not steps:
            raise KeyboardInterrupt
        steps.pop(0)()

    return sleep


def test_rearm_resumes_with_item_that_arrived_between_watches(tmp_path):
    write_events(tmp_path, start(), item(1))
    write_run(tmp_path)
    first = Lines()
    steps = [lambda: append_event(tmp_path, item(2))]
    with pytest.raises(KeyboardInterrupt):
        watch(tmp_path, False, first, interrupted(steps), always_alive)
    assert "#2" in "\n".join(first) and "#1" not in "\n".join(first)
    assert json.loads((tmp_path / CURSOR_PATH).read_text()) == {"run": RUN, "handled": 3}
    append_event(tmp_path, item(3))
    second = Lines()
    steps = [lambda: append_event(tmp_path, end())]
    assert watch(tmp_path, False, second, lambda s: steps.pop(0)(), always_alive) == 0
    text = "\n".join(second)
    assert "#3" in text and "#2" not in text and "run ended" in text


def test_cursor_of_another_run_is_ignored(tmp_path):
    write_events(tmp_path, start(), item(1), item(2))
    write_run(tmp_path)
    (tmp_path / CURSOR_PATH).write_text(json.dumps({"run": "other", "handled": 1}))
    steps = [lambda: append_event(tmp_path, end())]
    out = Lines()
    assert watch(tmp_path, False, out, lambda s: steps.pop(0)(), always_alive) == 0
    assert "#1" not in "\n".join(out) and "#2" not in "\n".join(out)


def test_replay_ignores_cursor_but_updates_it(tmp_path):
    write_events(tmp_path, start(), item(1))
    write_run(tmp_path)
    (tmp_path / CURSOR_PATH).write_text(json.dumps({"run": RUN, "handled": 2}))
    steps = [lambda: append_event(tmp_path, end())]
    out = Lines()
    assert watch(tmp_path, True, out, lambda s: steps.pop(0)(), always_alive) == 0
    assert any("#1" in line for line in out)
    assert json.loads((tmp_path / CURSOR_PATH).read_text())["handled"] == 3
