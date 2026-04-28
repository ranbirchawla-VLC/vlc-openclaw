"""Tests for scripts/models.py — Pydantic model validation."""

from __future__ import annotations
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models import Intent, MacroRow, MealLog, Macros, Mesocycle


def _macro_row(**kwargs) -> MacroRow:
    defaults = dict(calories=2000, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
    return MacroRow(**{**defaults, **kwargs})


def _intent(**kwargs) -> Intent:
    return Intent(**kwargs)


def _seven_rows() -> list[dict]:
    return [
        dict(calories=2000, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for _ in range(7)
    ]


def _mesocycle(**kwargs) -> Mesocycle:
    defaults = dict(
        mesocycle_id=1,
        user_id=123,
        name="test",
        weeks=4,
        start_date="2026-05-01",
        end_date="2026-05-29",
        dose_weekday=0,
        macro_table=_seven_rows(),
        intent=dict(rationale=""),
        status="active",
        created_at="2026-04-25T00:00:00Z",
        ended_at=None,
    )
    return Mesocycle(**{**defaults, **kwargs})


# ── MacroRow ──────────────────────────────────────────────────────────────────

def test_macro_row_valid():
    r = _macro_row()
    assert r.calories == 2000
    assert r.restrictions == []


def test_macro_row_with_restrictions():
    r = _macro_row(restrictions=["low fat after dose"])
    assert r.restrictions == ["low fat after dose"]


def test_macro_row_missing_field():
    with pytest.raises(ValidationError):
        MacroRow(calories=2000, protein_g=180, fat_g=70)  # missing carbs_g, restrictions


def test_macro_row_strict_rejects_float_calories():
    with pytest.raises(ValidationError):
        MacroRow(calories=2000.5, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])


# ── Intent ────────────────────────────────────────────────────────────────────

def test_intent_all_none_is_valid():
    i = _intent(rationale="")
    assert i.target_deficit_kcal is None
    assert i.protein_floor_g is None


def test_intent_with_values():
    i = _intent(target_deficit_kcal=3500, protein_floor_g=180, fat_ceiling_g=60, rationale="cut")
    assert i.target_deficit_kcal == 3500


def test_intent_strict_rejects_string_deficit():
    with pytest.raises(ValidationError):
        Intent(target_deficit_kcal="3500", rationale="")


# ── Mesocycle ─────────────────────────────────────────────────────────────────

def test_mesocycle_valid():
    c = _mesocycle()
    assert c.mesocycle_id == 1
    assert c.status == "active"
    assert len(c.macro_table) == 7


def test_mesocycle_weeks_lt_one_rejected():
    with pytest.raises(ValidationError):
        _mesocycle(weeks=0)


def test_mesocycle_dose_weekday_out_of_range():
    with pytest.raises(ValidationError):
        _mesocycle(dose_weekday=7)


def test_mesocycle_macro_table_wrong_length():
    with pytest.raises(ValidationError):
        _mesocycle(macro_table=_seven_rows()[:3])


def test_mesocycle_status_invalid_literal():
    with pytest.raises(ValidationError):
        _mesocycle(status="pending")


def test_mesocycle_ended_at_nullable():
    c = _mesocycle(status="ended", ended_at="2026-06-01T00:00:00Z")
    assert c.ended_at == "2026-06-01T00:00:00Z"


# ── Macros sub-model ──────────────────────────────────────────────────────────

def test_macros_valid():
    m = Macros(calories=500, protein_g=40, fat_g=20, carbs_g=50)
    assert m.calories == 500


def test_macros_strict_rejects_float():
    with pytest.raises(ValidationError):
        Macros(calories=500.5, protein_g=40, fat_g=20, carbs_g=50)


def test_macros_strict_rejects_string():
    with pytest.raises(ValidationError):
        Macros(calories="500", protein_g=40, fat_g=20, carbs_g=50)


def test_macros_missing_field():
    with pytest.raises(ValidationError):
        Macros(calories=500, protein_g=40, fat_g=20)


# ── MealLog ───────────────────────────────────────────────────────────────────

def _macros(**kwargs) -> dict:
    defaults = dict(calories=500, protein_g=40, fat_g=20, carbs_g=50)
    return {**defaults, **kwargs}


def _meal_log(**kwargs) -> MealLog:
    defaults = dict(
        log_id=1,
        user_id=42,
        timestamp_utc="2026-04-25T14:00:00Z",
        timezone_at_log="America/Denver",
        food_description="protein shake",
        macros=_macros(),
        source="ad_hoc",
        recipe_id=None,
        recipe_name_snapshot=None,
        supersedes=None,
    )
    return MealLog(**{**defaults, **kwargs})


def test_meal_log_ad_hoc_valid():
    log = _meal_log()
    assert log.log_id == 1
    assert log.source == "ad_hoc"
    assert log.recipe_id is None
    assert log.supersedes is None


def test_meal_log_recipe_valid():
    log = _meal_log(source="recipe", recipe_id=7, recipe_name_snapshot="usual lunch")
    assert log.recipe_id == 7
    assert log.recipe_name_snapshot == "usual lunch"


def test_meal_log_strict_rejects_string_log_id():
    with pytest.raises(ValidationError):
        _meal_log(log_id="1")


def test_meal_log_strict_rejects_string_user_id():
    with pytest.raises(ValidationError):
        _meal_log(user_id="42")


def test_meal_log_invalid_source():
    with pytest.raises(ValidationError):
        _meal_log(source="manual")


def test_meal_log_recipe_source_requires_recipe_id():
    with pytest.raises(ValidationError):
        _meal_log(source="recipe", recipe_id=None)


def test_meal_log_ad_hoc_forbids_recipe_id():
    with pytest.raises(ValidationError):
        _meal_log(source="ad_hoc", recipe_id=5)


def test_meal_log_supersedes_none_on_fresh():
    log = _meal_log()
    assert log.supersedes is None


def test_meal_log_supersedes_int_on_correction():
    log = _meal_log(supersedes=3)
    assert log.supersedes == 3


def test_meal_log_macros_rejects_float():
    with pytest.raises(ValidationError):
        _meal_log(macros=dict(calories=500.5, protein_g=40, fat_g=20, carbs_g=50))
