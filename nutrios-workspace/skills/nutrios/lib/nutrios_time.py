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


def parse(s: str) -> datetime:
    """Parse ISO8601 string to UTC-aware datetime. Raises ValueError on naive input."""
    # Python 3.11+ fromisoformat handles Z, but be explicit for clarity
    normalized = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        raise ValueError(f"Naive datetime string not accepted: {s!r}")
    return dt.astimezone(timezone.utc)
