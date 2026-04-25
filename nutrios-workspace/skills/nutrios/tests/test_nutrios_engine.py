"""Tests for nutrios_engine — TDD, built function by function.

Engine is pure: no I/O, no datetime.now() calls, time always passed as param.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import nutrios_engine as engine
from nutrios_models import (
    MacroRange, DayMacros, DayPattern, Goals, Mesocycle, ResolvedDay,
    Protocol, Treatment, BiometricSnapshot, Clinical,
    WeighIn, Event, NeedsSetup,
    FoodLogEntry, DoseLogEntry,
    GateResult, SetupStatus, Flag,
)


# ---------------------------------------------------------------------------
# merge_range()
# ---------------------------------------------------------------------------

def test_merge_range_null_override_returns_default():
    default = MacroRange(min=175)
    result = engine.merge_range(default, None)
    assert result.min == 175
    assert result.max is None

def test_merge_range_both_null_override_returns_default():
    default = MacroRange(min=175)
    override = MacroRange()  # both ends null
    result = engine.merge_range(default, override)
    assert result.min == 175
    assert result.max is None

def test_merge_range_override_max_only():
    default = MacroRange(min=175)
    override = MacroRange(max=200)
    result = engine.merge_range(default, override)
    assert result.min == 175  # inherited
    assert result.max == 200  # from override

def test_merge_range_override_both_ends():
    default = MacroRange(min=150, max=250)
    override = MacroRange(min=180, max=220)
    result = engine.merge_range(default, override)
    assert result.min == 180
    assert result.max == 220


# ---------------------------------------------------------------------------
# macro_range_check()
# ---------------------------------------------------------------------------

def test_macro_range_check_unset():
    assert engine.macro_range_check(180, MacroRange()) == "UNSET"

def test_macro_range_check_low():
    assert engine.macro_range_check(174, MacroRange(min=175)) == "LOW"

def test_macro_range_check_ok_at_min_boundary():
    assert engine.macro_range_check(175, MacroRange(min=175)) == "OK"

def test_macro_range_check_over():
    assert engine.macro_range_check(66, MacroRange(max=65)) == "OVER"

def test_macro_range_check_ok_at_max_boundary():
    assert engine.macro_range_check(65, MacroRange(max=65)) == "OK"

def test_macro_range_check_ok_within_range():
    assert engine.macro_range_check(180, MacroRange(min=150, max=200)) == "OK"
