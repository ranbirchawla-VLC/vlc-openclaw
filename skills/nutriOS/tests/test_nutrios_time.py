"""Tests for nutrios_time — built TDD, one function at a time."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import nutrios_time


# ---------------------------------------------------------------------------
# now()
# ---------------------------------------------------------------------------

def test_now_returns_utc_aware():
    dt = nutrios_time.now()
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# parse()
# ---------------------------------------------------------------------------

_EXPECTED_UTC = datetime(2026, 4, 24, 15, 30, 0, tzinfo=timezone.utc)

def test_parse_z_suffix():
    assert nutrios_time.parse("2026-04-24T15:30:00Z") == _EXPECTED_UTC

def test_parse_plus_zero_offset():
    assert nutrios_time.parse("2026-04-24T15:30:00+00:00") == _EXPECTED_UTC

def test_parse_negative_offset():
    # -07:00 means 08:30 local = 15:30 UTC
    assert nutrios_time.parse("2026-04-24T08:30:00-07:00") == _EXPECTED_UTC

def test_parse_raises_on_naive():
    with pytest.raises(ValueError):
        nutrios_time.parse("2026-04-24T15:30:00")


# ---------------------------------------------------------------------------
# meal_slot()
# Bins by local hour in user TZ. Boundary cases drive the assertions.
# America/Denver is UTC-6 in summer (MDT).
# ---------------------------------------------------------------------------

# UTC offset for MDT (Mountain Daylight Time) is -06:00
# So local hour = UTC hour - 6
# We pick a date in summer (2026-04-25) when Denver is on MDT (-6).

_TZ = "America/Denver"

def _utc_for_local_hour(local_hour: int) -> datetime:
    """Build a UTC datetime that maps to the given local hour in Denver on 2026-04-25."""
    from zoneinfo import ZoneInfo
    local_dt = datetime(2026, 4, 25, local_hour, 0, 0, tzinfo=ZoneInfo(_TZ))
    return local_dt.astimezone(timezone.utc)

def test_meal_slot_breakfast_start():
    assert nutrios_time.meal_slot(_utc_for_local_hour(4), _TZ) == "breakfast"

def test_meal_slot_breakfast_end():
    # 10:59 → breakfast
    from zoneinfo import ZoneInfo
    local_dt = datetime(2026, 4, 25, 10, 59, 0, tzinfo=ZoneInfo(_TZ))
    assert nutrios_time.meal_slot(local_dt.astimezone(timezone.utc), _TZ) == "breakfast"

def test_meal_slot_lunch_start():
    assert nutrios_time.meal_slot(_utc_for_local_hour(11), _TZ) == "lunch"

def test_meal_slot_lunch_end():
    from zoneinfo import ZoneInfo
    local_dt = datetime(2026, 4, 25, 14, 59, 0, tzinfo=ZoneInfo(_TZ))
    assert nutrios_time.meal_slot(local_dt.astimezone(timezone.utc), _TZ) == "lunch"

def test_meal_slot_snack_between_lunch_and_dinner():
    # 15:00-16:59 local → snack
    assert nutrios_time.meal_slot(_utc_for_local_hour(15), _TZ) == "snack"
    assert nutrios_time.meal_slot(_utc_for_local_hour(16), _TZ) == "snack"

def test_meal_slot_dinner_start():
    assert nutrios_time.meal_slot(_utc_for_local_hour(17), _TZ) == "dinner"

def test_meal_slot_dinner_end():
    from zoneinfo import ZoneInfo
    local_dt = datetime(2026, 4, 25, 21, 59, 0, tzinfo=ZoneInfo(_TZ))
    assert nutrios_time.meal_slot(local_dt.astimezone(timezone.utc), _TZ) == "dinner"

def test_meal_slot_snack_late_night():
    # 22:00 local → snack
    assert nutrios_time.meal_slot(_utc_for_local_hour(22), _TZ) == "snack"

def test_meal_slot_snack_early_morning():
    # 03:00 local → snack
    assert nutrios_time.meal_slot(_utc_for_local_hour(3), _TZ) == "snack"

# ---------------------------------------------------------------------------
# window()
# Half-open intervals [start_utc, end_utc). Boundaries are local calendar days.
# ---------------------------------------------------------------------------

def test_window_today_respects_local_date():
    """UTC 03:00 on the 25th is local 21:00 on the 24th in Denver (MDT -06:00).
    window('today') must return the 24th's boundaries, not the UTC 25th's."""
    from zoneinfo import ZoneInfo
    # 2026-04-25T03:00:00Z = 2026-04-24T21:00:00 MDT
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)
    start, end = nutrios_time.window(now_utc, _TZ, "today")
    # Expect boundaries of 2026-04-24 in Denver
    expected_start = datetime(2026, 4, 24, 0, 0, 0, tzinfo=ZoneInfo(_TZ)).astimezone(timezone.utc)
    expected_end   = datetime(2026, 4, 25, 0, 0, 0, tzinfo=ZoneInfo(_TZ)).astimezone(timezone.utc)
    assert start == expected_start
    assert end == expected_end

def test_window_today_is_half_open():
    now_utc = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    start, end = nutrios_time.window(now_utc, _TZ, "today")
    assert start < end

def test_window_yesterday_contiguous_with_today():
    now_utc = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    today_start, _ = nutrios_time.window(now_utc, _TZ, "today")
    _, yest_end    = nutrios_time.window(now_utc, _TZ, "yesterday")
    assert yest_end == today_start

def test_window_last_7d_spans_seven_days():
    """last_7d is a rolling 7-day window ending at start-of-local-tomorrow."""
    # Denver at UTC 2026-04-25T03:00:00 = local 2026-04-24T21:00:00 MDT
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)
    start, end = nutrios_time.window(now_utc, _TZ, "last_7d")
    delta = end - start
    assert delta.days == 7

def test_window_last_7d_starts_at_local_6_days_ago():
    """Denver user at local 2026-04-24: last_7d starts at 2026-04-18 local."""
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)  # local 2026-04-24 21:00
    start, end = nutrios_time.window(now_utc, _TZ, "last_7d")
    expected_start = datetime(2026, 4, 18, 0, 0, 0, tzinfo=ZoneInfo(_TZ)).astimezone(timezone.utc)
    expected_end   = datetime(2026, 4, 25, 0, 0, 0, tzinfo=ZoneInfo(_TZ)).astimezone(timezone.utc)
    assert start == expected_start
    assert end == expected_end

def test_window_last_7d_contains_now():
    """The window must contain now itself."""
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)
    start, end = nutrios_time.window(now_utc, _TZ, "last_7d")
    assert start <= now_utc < end

def test_window_last_7d_excludes_8_days_ago():
    """An instant 7 local days + 1 minute before now must not be in the window."""
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)  # local 2026-04-24 21:00
    start, _ = nutrios_time.window(now_utc, _TZ, "last_7d")
    # 7 days + 1 minute before local 2026-04-24T21:00 = local 2026-04-17T20:59
    zone = ZoneInfo(_TZ)
    seven_days_plus = datetime(2026, 4, 17, 20, 59, 0, tzinfo=zone).astimezone(timezone.utc)
    assert seven_days_plus < start


def test_meal_slot_tz_independent():
    """Same instant must produce the same slot regardless of input tzinfo."""
    from zoneinfo import ZoneInfo
    # 17:30 Denver local = dinner
    local_dt = datetime(2026, 4, 25, 17, 30, 0, tzinfo=ZoneInfo(_TZ))
    utc_dt = local_dt.astimezone(timezone.utc)
    # Express the same moment in UTC+5:30 (IST)
    ist = ZoneInfo("Asia/Kolkata")
    ist_dt = utc_dt.astimezone(ist)
    assert nutrios_time.meal_slot(utc_dt, _TZ) == "dinner"
    assert nutrios_time.meal_slot(ist_dt, _TZ) == "dinner"
