import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crew.budget import effective_cap, week_override
from crew.cli import main
from crew.config import load_config
from crew.usage import Usage, record_statusline

PROJECT = Path(__file__).resolve().parent / "fixtures" / "project"
NOW = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
RESET = datetime(2026, 11, 13, 11, 0, tzinfo=UTC)
USAGE = Usage(41, RESET, 12, NOW + timedelta(hours=2), NOW)


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    (root / ".crew" / "state.json").unlink(missing_ok=True)
    monkeypatch.setenv("CREW_USAGE_FILE", str(tmp_path / "usage.json"))
    return root


def write_reading(path, reset=RESET):
    data = {
        "rate_limits": {
            "seven_day": {"used_percentage": 41, "resets_at": int(reset.timestamp())},
            "five_hour": {"used_percentage": 12, "resets_at": int(reset.timestamp())},
        }
    }
    record_statusline(json.dumps(data), path, datetime.now(UTC))


def test_override_applies_until_week_reset(root):
    config = load_config(root)
    state = {"budget_override": week_override(95, USAGE)}
    assert state["budget_override"] == {"percent": 95, "until": RESET.isoformat()}
    assert effective_cap(config, state, NOW) == (95, f"this week until {RESET.isoformat()}")
    assert effective_cap(config, {}, NOW) == (75, "default")


def test_override_expires_at_reset(root):
    config = load_config(root)
    state = {"budget_override": week_override(95, USAGE)}
    assert effective_cap(config, state, RESET) == (75, "default")
    assert effective_cap(config, {"budget_override": {"percent": "x"}}, NOW) == (75, "default")


def test_week_needs_reading(root, capsys):
    assert main(["budget", "--week", "95", "--root", str(root)]) == 2
    assert capsys.readouterr().err == (
        "crew: error: no usage reading yet, so the week's reset time is unknown; "
        "start any crew agent first\n"
    )


def test_week_out_of_range(root, tmp_path, capsys):
    write_reading(tmp_path / "usage.json", datetime.now(UTC) + timedelta(days=2))
    for value in ("0", "101"):
        assert main(["budget", "--week", value, "--root", str(root)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("crew: error: ") and "1" in err and "100" in err


def test_budget_cli_output(root, tmp_path, capsys):
    assert main(["budget", "--root", str(root)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "cap 75% (default)"
    assert lines[1].startswith("no usage reading yet")

    reset = datetime.now(UTC) + timedelta(days=2)
    write_reading(tmp_path / "usage.json", reset)
    assert main(["budget", "--week", "95", "--root", str(root)]) == 0
    local = reset.replace(microsecond=0).astimezone().strftime("%a %H:%M")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"cap 95% this week (until {local}), then 75%"
    assert lines[1].startswith("week 41%")
    state = json.loads((root / ".crew" / "state.json").read_text())
    assert state["budget_override"]["percent"] == 95

    assert main(["budget", "--reset", "--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "cap 75% (default)"
    assert "budget_override" not in json.loads((root / ".crew" / "state.json").read_text())
