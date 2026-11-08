"""When a run stops: the end time, the 5-hour window, and what agents are told at the end."""

import re
from datetime import date, datetime, time, timedelta

FIVE_HOUR_FULL = 98.0  # percent
RESET_SLACK = timedelta(minutes=2)
WIND_DOWN = (
    "The run is ending. Commit your work in progress on your branch (a wip: commit is "
    "fine), push it, comment on the issue what is done and what remains, then stop. "
    "Don't change the labels."
)
CONTINUE = "The usage limit has reset. Continue where you stopped."

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_CLOCK = re.compile(r"^(?:([A-Za-z]+)\s+)?(\d{1,2}):(\d{2})$")


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock).astimezone()


def parse_until(text: str, now: datetime) -> datetime:
    """The run's end time, as an aware datetime.

    ``07:00`` is the next 07:00 after ``now`` (local time); ``Mon 07:00`` or
    ``monday 07:00`` the next such weekday and time; an ISO 8601 time (local, or with an
    offset) is taken as is and must be after ``now``.

    Raises:
        ValueError: the text is none of these, or names a time that isn't after ``now``.
    """
    text = text.strip()
    local_now = now.astimezone()
    if match := _CLOCK.match(text):
        day_name, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
        if hour > 23 or minute > 59:
            raise ValueError(f"{text!r} is not a time of day")
        clock = time(hour, minute)
        if day_name is None:
            candidate = _at(local_now.date(), clock)
            if candidate <= now:
                candidate = _at(local_now.date() + timedelta(days=1), clock)
            return candidate
        weekday = next(
            (
                i
                for i, name in enumerate(DAYS)
                if len(day_name) >= 3 and name.startswith(day_name.lower())
            ),
            None,
        )
        if weekday is None:
            raise ValueError(f"{day_name!r} is not a day of the week")
        ahead = (weekday - local_now.weekday()) % 7
        candidate = _at(local_now.date() + timedelta(days=ahead), clock)
        if candidate <= now:
            candidate = _at(local_now.date() + timedelta(days=ahead + 7), clock)
        return candidate
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"{text!r} is not an end time; use 07:00, Mon 07:00 or an ISO 8601 time"
        ) from None
    moment = moment if moment.tzinfo else moment.astimezone()
    if moment <= now:
        raise ValueError(f"{text!r} is not in the future")
    return moment
