"""Tests for build_macro_grid."""

from __future__ import annotations
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_macro_grid import build_grid


_WEEKDAY_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def _grid(**kwargs) -> dict:
    """Call build_grid with standard fixture defaults for unspecified params."""
    defaults: dict[str, Any] = dict(
        estimated_tdee_kcal=2350,
        target_deficit_kcal=3500,
        protein_floor_g=175,
        fat_ceiling_g=65,
        dose_weekday="sunday",
        deficit_unit="weekly_kcal",
        per_weekday_targets=None,
    )
    return build_grid(**{**defaults, **kwargs})


def _row(result: dict, weekday: str) -> dict:
    return next(r for r in result["rows"] if r["weekday"] == weekday)


# ── all-baseline (no per_weekday_targets) ─────────────────────────────────────

def test_all_baseline_row_count():
    assert len(_grid()["rows"]) == 7


def test_all_baseline_sun_sat_ordering():
    assert [r["weekday"] for r in _grid()["rows"]] == _WEEKDAY_ORDER


def test_all_baseline_calories():
    # baseline = round(2350 - 3500/7) = round(2350 - 500) = 1850
    for row in _grid()["rows"]:
        assert row["calories"] == 1850


def test_all_baseline_protein_fat_carbs():
    # carbs = (1850 - 175*4 - 65*9) // 4 = 565 // 4 = 141
    for row in _grid()["rows"]:
        assert row["protein_g"] == 175
        assert row["fat_g"] == 65
        assert row["carbs_g"] == 141


def test_weekly_kcal_target():
    assert _grid()["weekly_kcal_target"] == 12950  # 2350*7 - 3500


def test_floor_ceiling_stored_on_row():
    for row in _grid()["rows"]:
        assert row["protein_floor_g"] == 175
        assert row["fat_ceiling_g"] == 65


def test_restrictions_empty_on_all_rows():
    for row in _grid()["rows"]:
        assert row["restrictions"] == []


# ── deficit_unit ──────────────────────────────────────────────────────────────

def test_deficit_unit_daily_kcal_normalizes():
    # daily 500 * 7 = 3500 weekly; same result as weekly fixture
    result = _grid(target_deficit_kcal=500, deficit_unit="daily_kcal")
    for row in result["rows"]:
        assert row["calories"] == 1850
    assert result["weekly_kcal_target"] == 12950


# ── single-day target ─────────────────────────────────────────────────────────

def test_single_day_target_calories():
    result = _grid(per_weekday_targets={"wednesday": {"calories": 2000}})
    assert _row(result, "wednesday")["calories"] == 2000
    for row in result["rows"]:
        if row["weekday"] != "wednesday":
            assert row["calories"] == 1850


def test_single_day_target_protein_above_floor():
    # protein_g=200 > baseline floor 175; valid
    result = _grid(per_weekday_targets={"monday": {"protein_g": 200}})
    assert _row(result, "monday")["protein_g"] == 200


def test_single_day_target_fat_below_ceiling():
    # fat_g=50 < baseline ceiling 65; valid
    result = _grid(per_weekday_targets={"friday": {"fat_g": 50}})
    assert _row(result, "friday")["fat_g"] == 50


# ── multi-day target ──────────────────────────────────────────────────────────

def test_multi_day_target_calories():
    result = _grid(per_weekday_targets={
        "sunday": {"calories": 2100},
        "saturday": {"calories": 1600},
    })
    assert _row(result, "sunday")["calories"] == 2100
    assert _row(result, "saturday")["calories"] == 1600
    for row in result["rows"]:
        if row["weekday"] not in ("sunday", "saturday"):
            assert row["calories"] == 1850


# ── per-day floor/ceiling overrides ──────────────────────────────────────────

def test_per_day_protein_floor_allows_below_cycle_baseline():
    # per-day floor=120 allows protein_g=130 even though cycle baseline=175
    result = _grid(per_weekday_targets={"tuesday": {"protein_floor_g": 120, "protein_g": 130}})
    tue = _row(result, "tuesday")
    assert tue["protein_g"] == 130
    assert tue["protein_floor_g"] == 120


def test_per_day_fat_ceiling_allows_above_cycle_baseline():
    # per-day ceiling=90 allows fat_g=80 even though cycle baseline=65
    result = _grid(per_weekday_targets={"thursday": {"fat_ceiling_g": 90, "fat_g": 80}})
    thu = _row(result, "thursday")
    assert thu["fat_g"] == 80
    assert thu["fat_ceiling_g"] == 90


def test_per_day_floor_stored_only_on_override_day():
    result = _grid(per_weekday_targets={"tuesday": {"protein_floor_g": 120, "protein_g": 130}})
    for row in result["rows"]:
        if row["weekday"] != "tuesday":
            assert row["protein_floor_g"] == 175


def test_per_day_ceiling_stored_only_on_override_day():
    result = _grid(per_weekday_targets={"thursday": {"fat_ceiling_g": 90, "fat_g": 80}})
    for row in result["rows"]:
        if row["weekday"] != "thursday":
            assert row["fat_ceiling_g"] == 65


# ── per-day floor/ceiling only (no explicit macro value) ─────────────────────

def test_per_day_floor_only_sets_protein_to_floor():
    # protein_floor_g=120 without protein_g: day_protein defaults to the per-day floor
    result = _grid(per_weekday_targets={"tuesday": {"protein_floor_g": 120}})
    tue = _row(result, "tuesday")
    assert tue["protein_g"] == 120
    assert tue["protein_floor_g"] == 120


def test_per_day_ceiling_only_sets_fat_to_ceiling():
    # fat_ceiling_g=90 without fat_g: day_fat defaults to the per-day ceiling
    result = _grid(per_weekday_targets={"thursday": {"fat_ceiling_g": 90}})
    thu = _row(result, "thursday")
    assert thu["fat_g"] == 90
    assert thu["fat_ceiling_g"] == 90


# ── floor/ceiling boundary (equality is valid) ───────────────────────────────

def test_protein_at_per_day_floor_boundary_is_valid():
    # protein_g == effective floor is valid; constraint check uses strict <
    result = _grid(per_weekday_targets={"monday": {"protein_floor_g": 140, "protein_g": 140}})
    assert _row(result, "monday")["protein_g"] == 140


def test_fat_at_per_day_ceiling_boundary_is_valid():
    # fat_g == effective ceiling is valid; constraint check uses strict >
    result = _grid(per_weekday_targets={"monday": {"fat_ceiling_g": 80, "fat_g": 80}})
    assert _row(result, "monday")["fat_g"] == 80


# ── constraint violations ─────────────────────────────────────────────────────

def test_protein_below_cycle_floor_without_per_day_floor_raises():
    with pytest.raises(ValueError, match="protein"):
        _grid(per_weekday_targets={"tuesday": {"protein_g": 120}})


def test_constraint_error_names_the_day():
    with pytest.raises(ValueError, match="tuesday"):
        _grid(per_weekday_targets={"tuesday": {"protein_g": 120}})


def test_fat_above_cycle_ceiling_without_per_day_ceiling_raises():
    with pytest.raises(ValueError, match="fat"):
        _grid(per_weekday_targets={"tuesday": {"fat_g": 80}})


def test_calories_too_low_for_constraints_raises():
    # 800 - 175*4 - 65*9 = 800 - 700 - 585 = -485 < 0
    with pytest.raises(ValueError, match="cannot satisfy"):
        _grid(per_weekday_targets={"monday": {"calories": 800}})


def test_per_day_floor_violation_raises():
    # explicit per-day floor=150, protein_g=120 < 150 is still an error
    with pytest.raises(ValueError, match="protein"):
        _grid(per_weekday_targets={"tuesday": {"protein_floor_g": 150, "protein_g": 120}})


def test_invalid_deficit_unit_raises():
    with pytest.raises(ValueError, match="deficit_unit"):
        build_grid(
            estimated_tdee_kcal=2350,
            target_deficit_kcal=3500,
            protein_floor_g=175,
            fat_ceiling_g=65,
            dose_weekday="sunday",
            deficit_unit="bad_unit",
        )


def test_invalid_weekday_key_raises():
    with pytest.raises(ValueError, match="invalid"):
        build_grid(
            estimated_tdee_kcal=2350,
            target_deficit_kcal=3500,
            protein_floor_g=175,
            fat_ceiling_g=65,
            dose_weekday="sunday",
            per_weekday_targets={"notaday": {"calories": 2000}},
        )
