import io
import json
from datetime import UTC, datetime, timedelta

from crew import usage
from crew.agent import agent_argv
from crew.cli import main
from crew.usage import Usage, is_fresh, read_usage, record_statusline, usage_path

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
WEEK_RESET = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
FIVE_RESET = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)


def payload(week_reset, five_reset, week=41, five=12):
    return json.dumps(
        {
            "session_id": "s",
            "rate_limits": {
                "five_hour": {"used_percentage": five, "resets_at": five_reset},
                "seven_day": {"used_percentage": week, "resets_at": week_reset},
            },
        }
    )


def test_record_statusline_writes_reading(tmp_path):
    path = tmp_path / "state" / "usage.json"
    local_reset = WEEK_RESET.astimezone().strftime("%a %H:%M")
    for week_reset, five_reset in (
        (int(WEEK_RESET.timestamp()), int(FIVE_RESET.timestamp())),
        (WEEK_RESET.isoformat(), FIVE_RESET.isoformat().replace("+00:00", "Z")),
    ):
        text = record_statusline(payload(week_reset, five_reset), path, NOW)
        assert text == f"crew · week 41% (resets {local_reset}) · 5h 12%"
        assert read_usage(path) == Usage(41.0, WEEK_RESET, 12.0, FIVE_RESET, NOW)
    assert [p.name for p in path.parent.iterdir()] == ["usage.json"]  # no temp file left


def test_record_statusline_without_rate_limits(tmp_path):
    path = tmp_path / "usage.json"
    assert record_statusline(json.dumps({"session_id": "s"}), path, NOW) == "crew · no usage data"
    assert not path.exists()


def test_record_statusline_bad_json_never_fails(tmp_path):
    path = tmp_path / "usage.json"
    assert record_statusline("{", path, NOW) == "crew · no usage data"
    bad = json.dumps({"rate_limits": {"seven_day": {"used_percentage": "x"}}})
    assert record_statusline(bad, path, NOW) == "crew · no usage data"
    assert not path.exists()


def test_usage_path_per_account(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": "/x/.claude-work", "XDG_STATE_HOME": str(tmp_path)}
    assert usage_path(env) == tmp_path / "crew" / "usage-.claude-work.json"
    assert usage_path({"XDG_STATE_HOME": str(tmp_path)}).name == "usage-default.json"
    assert usage_path({**env, "CREW_USAGE_FILE": str(tmp_path / "u.json")}) == tmp_path / "u.json"


def test_is_fresh():
    reading = Usage(1, WEEK_RESET, 1, FIVE_RESET, NOW)
    assert is_fresh(reading, NOW + timedelta(minutes=29))
    assert not is_fresh(reading, NOW + timedelta(minutes=31))
    assert not is_fresh(None, NOW)


def test_read_usage_missing_or_bad(tmp_path):
    assert read_usage(tmp_path / "none.json") is None
    (tmp_path / "bad.json").write_text("[]")
    assert read_usage(tmp_path / "bad.json") is None


def test_agent_argv_settings_and_auto():
    settings = json.dumps({"statusLine": {"type": "command", "command": "crew usage record"}})
    assert agent_argv("implementer", "go", None, auto=True) == [
        "claude", "--agent", "crew:implementer", "--permission-mode", "auto",
        "--settings", settings, "go",
    ]  # fmt: skip
    assert agent_argv("lead", None, "sonnet") == [
        "claude", "--agent", "crew:lead", "--model", "sonnet", "--settings", settings,
    ]  # fmt: skip


def test_usage_record_cli_always_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CREW_USAGE_FILE", str(tmp_path / "u.json"))
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert main(["usage", "record"]) == 0
    assert capsys.readouterr().out.strip() == "crew · no usage data"
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(payload(int(WEEK_RESET.timestamp()), int(FIVE_RESET.timestamp())))
    )
    assert main(["usage", "record"]) == 0
    assert capsys.readouterr().out.startswith("crew · week 41% (resets ")
    assert read_usage(tmp_path / "u.json").week_percent == 41


def test_usage_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CREW_USAGE_FILE", str(tmp_path / "u.json"))
    assert main(["usage"]) == 0
    assert capsys.readouterr().out.strip() == (
        "no usage reading yet; it appears once a crew agent session has drawn its status line"
    )
    record_statusline(payload(WEEK_RESET.isoformat(), FIVE_RESET.isoformat()), tmp_path / "u.json",
                      datetime.now(UTC))  # fmt: skip
    assert main(["usage"]) == 0
    out = capsys.readouterr().out
    assert "week 41%" in out and "5h 12%" in out and "ago" in out


def test_agent_env_pins_usage_file(tmp_path):
    from crew.agent import agent_env

    base = {"XDG_STATE_HOME": str(tmp_path)}
    env = agent_env(base, "t", "botty", 42, tmp_path / "gh")
    assert env["CREW_USAGE_FILE"] == str(usage.usage_path(base))
