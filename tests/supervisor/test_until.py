from datetime import datetime, timedelta

import pytest

from crew.supervisor.until import parse_until


def local(*args):
    return datetime(*args).astimezone()


def test_parse_until_rolls_forward():
    monday_8 = local(2026, 11, 9, 8, 0)
    assert parse_until("07:00", monday_8) == local(2026, 11, 10, 7, 0)
    assert parse_until("09:30", monday_8) == local(2026, 11, 9, 9, 30)
    monday_15 = local(2026, 11, 9, 15, 0)
    assert parse_until("Mon 07:00", monday_15) == local(2026, 11, 16, 7, 0)
    assert parse_until("monday 07:00", monday_15) == local(2026, 11, 16, 7, 0)
    friday = local(2026, 11, 13, 21, 0)
    assert parse_until("Mon 07:00", friday) == local(2026, 11, 16, 7, 0)
    assert parse_until("2026-11-20T07:00", monday_8) == local(2026, 11, 20, 7, 0)
    with_offset = parse_until("2026-11-20T07:00+00:00", monday_8)
    assert with_offset.utcoffset() == timedelta(0) and with_offset.hour == 7
    for bad in ("2026-11-01T07:00", "25:00", "7", "Funday 07:00", "Mon 7:61", ""):
        with pytest.raises(ValueError):
            parse_until(bad, monday_8)
    assert parse_until("07:00", monday_8).tzinfo is not None
