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


def parse(s: str) -> datetime:
    """Parse ISO8601 string to UTC-aware datetime. Raises ValueError on naive input."""
    # Python 3.11+ fromisoformat handles Z, but be explicit for clarity
    normalized = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        raise ValueError(f"Naive datetime string not accepted: {s!r}")
    return dt.astimezone(timezone.utc)
