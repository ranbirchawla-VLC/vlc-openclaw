"""Authoritative time module for NutriOS v2.

Single seam for time so tests can monkeypatch now().
Engine functions take now as a parameter; never call now() internally.
"""
from datetime import datetime, timezone, timedelta, date
from typing import Literal
from zoneinfo import ZoneInfo


def now() -> datetime:
    """Return current UTC-aware datetime. Monkeypatch seam for tests."""
    return datetime.now(timezone.utc)


def meal_slot(now: datetime, tz: str) -> Literal["breakfast", "lunch", "dinner", "snack"]:
    """Classify a UTC-aware datetime into a meal slot for the user's local timezone.

    Bins:
        breakfast  04:00–10:59 local
        lunch      11:00–14:59 local
        dinner     17:00–21:59 local
        snack      everything else
    """
    local_hour = now.astimezone(ZoneInfo(tz)).hour
    match local_hour:
        case h if 4 <= h <= 10:
            return "breakfast"
        case h if 11 <= h <= 14:
            return "lunch"
        case h if 17 <= h <= 21:
            return "dinner"
        case _:
            return "snack"


def window(
    now: datetime,
    tz: str,
    kind: Literal["today", "yesterday", "last_7d"],
) -> tuple[datetime, datetime]:
    """Return a half-open UTC interval [start, end) for the requested window.

    All boundaries are local calendar-day boundaries in the user's TZ.

        today:    [today_start,         today_start + 1 day)
        yesterday:[today_start - 1 day, today_start)
        last_7d:  [today_start - 6 days, today_start + 1 day)  — rolling 7 days including today
    """
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone)
    local_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    match kind:
        case "today":
            start_local = local_today
            end_local   = local_today + timedelta(days=1)
        case "yesterday":
            start_local = local_today - timedelta(days=1)
            end_local   = local_today
        case "last_7d":
            start_local = local_today - timedelta(days=6)
            end_local   = local_today + timedelta(days=1)

    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def to_local(now: datetime, tz: str) -> datetime:
    """Convert a UTC-aware datetime to the user's local timezone.

    Render uses this for display. Centralises ZoneInfo lookup so render
    never calls astimezone directly.
    """
    return now.astimezone(ZoneInfo(tz))


def parse(s: str) -> datetime:
    """Parse ISO8601 string to UTC-aware datetime. Raises ValueError on naive input."""
    # Python 3.11+ fromisoformat handles Z, but be explicit for clarity
    normalized = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        raise ValueError(f"Naive datetime string not accepted: {s!r}")
    return dt.astimezone(timezone.utc)
