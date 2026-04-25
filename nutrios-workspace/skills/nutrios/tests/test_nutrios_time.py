"""Tests for nutrios_time — built TDD, one function at a time."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

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
