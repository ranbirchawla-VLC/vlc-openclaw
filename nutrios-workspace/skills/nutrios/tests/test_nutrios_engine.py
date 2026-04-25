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


# ---------------------------------------------------------------------------
# range_proximity()
# ---------------------------------------------------------------------------

def test_range_proximity_none_when_no_active_bounds():
    assert engine.range_proximity(100, MacroRange()) is None

def test_range_proximity_near_max():
    r = MacroRange(max=65)
    # distance = 65 - 55 = 10; 10/65 = 15.4% → within 20% → hint
    p = engine.range_proximity(55, r)
    assert p is not None
    assert p.end == "max"
    assert abs(p.distance_g - 10.0) < 0.01

def test_range_proximity_near_min():
    r = MacroRange(min=175)
    # 175 * 1.2 = 210, so 180 is within 20% above min → hint
    p = engine.range_proximity(185, r)
    assert p is not None
    assert p.end == "min"

def test_range_proximity_none_when_far():
    r = MacroRange(max=65)
    # 20 is very far below 65, so NOT within 20% → None
    assert engine.range_proximity(20, r) is None

def test_range_proximity_none_when_over():
    # If already over max, proximity hint is not relevant
    r = MacroRange(max=65)
    assert engine.range_proximity(70, r) is None


# ---------------------------------------------------------------------------
# resolve_day()
# ---------------------------------------------------------------------------

def _make_goals(
    day_type: str = "rest",
    pattern_deficit: int | None = None,
    pattern_protein_min: int | None = None,
) -> Goals:
    defaults = DayMacros(
        protein_g=MacroRange(min=175),
        fat_g=MacroRange(max=65),
    )
    patterns = []
    if pattern_deficit is not None or pattern_protein_min is not None:
        p = DayPattern(
            day_type=day_type,
            deficit_kcal=pattern_deficit,
            protein_g=MacroRange(min=pattern_protein_min) if pattern_protein_min else MacroRange(),
        )
        patterns.append(p)
    return Goals(
        active_cycle_id="cyc1",
        weekly_schedule={"friday": day_type},
        defaults=defaults,
        day_patterns=patterns,
    )


def _make_mesocycle(tdee: int | None = 2600, deficit: int = 400) -> Mesocycle:
    return Mesocycle(
        cycle_id="cyc1",
        phase="cut",
        start_date=date(2026, 1, 1),
        tdee_kcal=tdee,
        deficit_kcal=deficit,
    )


# now = Friday 2026-04-24T12:00:00 UTC
_NOW = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)  # Friday


def test_resolve_day_kcal_from_tdee_deficit():
    goals = _make_goals("rest")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, goals, meso)
    assert rd.kcal_target == 2200

def test_resolve_day_kcal_none_when_tdee_none():
    goals = _make_goals("rest")
    meso = _make_mesocycle(tdee=None, deficit=400)
    rd = engine.resolve_day(_NOW, goals, meso)
    assert rd.kcal_target is None

def test_resolve_day_pattern_deficit_overrides_cycle():
    goals = _make_goals("rest", pattern_deficit=600)
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, goals, meso)
    assert rd.kcal_target == 2000   # 2600 - 600

def test_resolve_day_pattern_protein_overrides_default():
    goals = _make_goals("rest", pattern_protein_min=200)
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, goals, meso)
    assert rd.protein_g.min == 200  # pattern override


# ---------------------------------------------------------------------------
# current_weight()
# ---------------------------------------------------------------------------

def _wi(id: int, weight: float, supersedes: int | None = None) -> WeighIn:
    return WeighIn(id=id, ts_iso="2026-04-24T12:00:00Z", weight_lbs=weight, supersedes=supersedes)


def test_current_weight_empty():
    assert engine.current_weight([]) is None

def test_current_weight_single():
    assert engine.current_weight([_wi(1, 218.0)]) == 218.0

def test_current_weight_supersedes_chain():
    """Entry 1 is superseded by entry 2. Entry 3 is independent. Most recent active = 3."""
    entries = [
        _wi(1, 220.0),
        _wi(2, 219.0, supersedes=1),  # supersedes 1 — entry 1 is now inactive
        _wi(3, 218.0),                # most recent active
    ]
    assert engine.current_weight(entries) == 218.0

def test_current_weight_all_active_returns_highest_id():
    entries = [_wi(1, 220.0), _wi(2, 219.0), _wi(3, 218.0)]
    assert engine.current_weight(entries) == 218.0


# ---------------------------------------------------------------------------
# weight_change()
# ---------------------------------------------------------------------------

def _wi_at(id: int, weight: float, days_ago: int) -> WeighIn:
    ts = (datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc) - timedelta(days=days_ago))
    return WeighIn(id=id, ts_iso=ts.isoformat(), weight_lbs=weight)


def test_weight_change_since_7_days():
    """5 entries spanning 14 days; since_days=7 should use the most recent entry older than 7 days."""
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        _wi_at(1, 222.0, 14),
        _wi_at(2, 221.0, 10),
        _wi_at(3, 220.0, 8),   # most recent older than 7 days
        _wi_at(4, 219.0, 3),
        _wi_at(5, 218.0, 0),   # current
    ]
    wc = engine.weight_change(entries, now, since_days=7)
    assert wc.current_lbs == 218.0
    assert wc.prior_lbs == 220.0
    assert abs(wc.delta_lbs - (-2.0)) < 0.01
    assert wc.since_days == 7


# ---------------------------------------------------------------------------
# weight_trend()
# ---------------------------------------------------------------------------

def test_weight_trend_last_n():
    entries = [_wi_at(i, 220.0 - i, i) for i in range(10)]
    rows = engine.weight_trend(entries, last_n=5)
    assert len(rows) == 5
    # last_n=5 means the 5 entries with highest ids
    ids = [r.weight_lbs for r in rows]
    assert len(ids) == 5
