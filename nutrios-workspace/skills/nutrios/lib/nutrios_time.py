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
