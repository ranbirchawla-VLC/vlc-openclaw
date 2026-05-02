"""Tests for recompute_macros_with_overrides."""

from __future__ import annotations
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recompute_macros_with_overrides import recompute


# ── helpers ───────────────────────────────────────────────────────────────────

def _recompute(**kwargs):
    """Call recompute with standard fixture defaults for unspecified params."""
    defaults = dict(
        estimated_tdee_kcal=2300,
        target_deficit_kcal=3500,
        protein_floor_g=175,
        fat_ceiling_g=65,
        overrides={},
    )
    return recompute(**{**defaults, **kwargs})


def _row(rows: list, weekday: str):
    return next(r for r in rows if r.weekday == weekday)


# ── no overrides ──────────────────────────────────────────────────────────────

def test_no_overrides_flat_calories():
    # weekly_intake = 2300*7 - 3500 = 12600; 12600 // 7 = 1800 per day
    rows = _recompute()
    assert len(rows) == 7
    for row in rows:
        assert row.calories == 1800


def test_no_overrides_protein_fat_carbs():
    # carbs = (1800 - 175*4 - 65*9) // 4 = (1800 - 700 - 585) // 4 = 515 // 4 = 128
    rows = _recompute()
    for row in rows:
        assert row.protein_g == 175
        assert row.fat_g == 65
        assert row.carbs_g == 128


# ── output ordering ───────────────────────────────────────────────────────────

def test_output_ordered_sun_sat():
    rows = _recompute()
    assert [r.weekday for r in rows] == [
        "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"
    ]


def test_output_ordered_sun_sat_with_override():
    # Ordering holds regardless of which day is overridden
    rows = _recompute(overrides={"wednesday": {"calories": 1500}})
    assert [r.weekday for r in rows] == [
        "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"
    ]


# ── single-day override ───────────────────────────────────────────────────────

def test_single_override_monday_calories():
    # Override Monday = 1550 cal
    # remaining = 12600 - 1550 = 11050; floor: 11050 // 6 = 1841
    rows = _recompute(overrides={"monday": {"calories": 1550}})
    assert _row(rows, "monday").calories == 1550
    for row in rows:
        if row.weekday != "monday":
            assert row.calories == 1841


def test_single_override_preserves_protein_fat_on_other_days():
    rows = _recompute(overrides={"monday": {"calories": 1550}})
    for row in rows:
        if row.weekday != "monday":
            assert row.protein_g == 175
            assert row.fat_g == 65


# ── multi-day override ────────────────────────────────────────────────────────

def test_multi_day_override_calories():
    # weekly=14000, protein=180, fat=60
    # overrides: sunday=2500, wednesday=1500
    # remaining = 14000-2500-1500 = 10000 for 5 days; 10000//5 = 2000
    rows = recompute(
        estimated_tdee_kcal=2500,    # 2500*7 - 3500 = 14000
        target_deficit_kcal=3500,
        protein_floor_g=180,
        fat_ceiling_g=60,
        overrides={"sunday": {"calories": 2500}, "wednesday": {"calories": 1500}},
    )
    assert _row(rows, "sunday").calories == 2500
    assert _row(rows, "wednesday").calories == 1500
    for row in rows:
        if row.weekday not in ("sunday", "wednesday"):
            assert row.calories == 2000


# ── per-day floor/ceiling overrides ──────────────────────────────────────────

def test_per_day_protein_floor_override_applies_to_correct_day():
    # Wednesday gets protein_floor_g=200; other days stay at baseline 175
    rows = _recompute(overrides={"wednesday": {"protein_floor_g": 200}})
    wed = _row(rows, "wednesday")
    assert wed.protein_floor_g == 200
    assert wed.protein_g == 200
    for row in rows:
        if row.weekday != "wednesday":
            assert row.protein_floor_g == 175


def test_per_day_fat_ceiling_override_applies_to_correct_day():
    # Friday gets fat_ceiling_g=80; other days stay at baseline 65
    rows = _recompute(overrides={"friday": {"fat_ceiling_g": 80}})
    fri = _row(rows, "friday")
    assert fri.fat_ceiling_g == 80
    assert fri.fat_g == 80
    for row in rows:
        if row.weekday != "friday":
            assert row.fat_ceiling_g == 65


def test_floor_ceiling_only_override_gets_redistributed_calories():
    # Wednesday has floor override but no calorie override → gets per-day redistribution
    # weekly=12600, no calorie overrides, so all 7 days = 12600 // 7 = 1800
    rows = _recompute(overrides={"wednesday": {"protein_floor_g": 200}})
    wed = _row(rows, "wednesday")
    assert wed.calories == 1800


# ── error cases ───────────────────────────────────────────────────────────────

def test_override_sum_exceeds_weekly_target_raises():
    # 10000 + 5000 = 15000 > 12600
    with pytest.raises(ValueError, match="exceed"):
        _recompute(overrides={"sunday": {"calories": 10000}, "monday": {"calories": 5000}})


def test_override_violates_protein_floor_raises():
    # protein_g=100 < protein_floor_g=175
    with pytest.raises(ValueError, match="protein"):
        _recompute(overrides={"sunday": {"calories": 1800, "protein_g": 100}})


def test_override_violates_fat_ceiling_raises():
    # fat_g=80 > fat_ceiling_g=65
    with pytest.raises(ValueError, match="fat"):
        _recompute(overrides={"sunday": {"calories": 1800, "fat_g": 80}})


def test_override_exhausts_remaining_budget_below_floor_raises():
    # Monday=9000; remaining=12600-9000=3600 for 6 days = 600/day
    # 600 < 175*4+65*9=1285; carbs_kcal < 0 → cannot satisfy constraints
    with pytest.raises(ValueError, match="cannot satisfy"):
        _recompute(overrides={"monday": {"calories": 9000}})
