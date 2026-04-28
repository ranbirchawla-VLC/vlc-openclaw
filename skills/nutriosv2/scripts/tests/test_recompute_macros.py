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


# ── single-day override ───────────────────────────────────────────────────────

def test_single_override_monday_calories():
    # Override offset 1 (Monday after Sunday dose) = 1550 cal
    # remaining = 12600 - 1550 = 11050; floor: 11050 // 6 = 1841
    rows = _recompute(overrides={1: {"calories": 1550}})
    assert rows[1].calories == 1550
    for i in [0, 2, 3, 4, 5, 6]:
        assert rows[i].calories == 1841


def test_single_override_preserves_protein_fat_on_other_days():
    rows = _recompute(overrides={1: {"calories": 1550}})
    for i in [0, 2, 3, 4, 5, 6]:
        assert rows[i].protein_g == 175
        assert rows[i].fat_g == 65


# ── multi-day override ────────────────────────────────────────────────────────

def test_multi_day_override_calories():
    # weekly=14000, protein=180, fat=60
    # overrides: offset0=2500, offset3=1500
    # remaining = 14000-2500-1500 = 10000 for 5 days; 10000//5 = 2000
    rows = recompute(
        estimated_tdee_kcal=2500,    # 2500*7 - 3500 = 14000
        target_deficit_kcal=3500,
        protein_floor_g=180,
        fat_ceiling_g=60,
        overrides={0: {"calories": 2500}, 3: {"calories": 1500}},
    )
    assert rows[0].calories == 2500
    assert rows[3].calories == 1500
    for i in [1, 2, 4, 5, 6]:
        assert rows[i].calories == 2000


# ── error cases ───────────────────────────────────────────────────────────────

def test_override_sum_exceeds_weekly_target_raises():
    # 10000 + 5000 = 15000 > 12600
    with pytest.raises(ValueError, match="exceed"):
        _recompute(overrides={0: {"calories": 10000}, 1: {"calories": 5000}})


def test_override_violates_protein_floor_raises():
    # protein_g=100 < protein_floor_g=175
    with pytest.raises(ValueError, match="protein"):
        _recompute(overrides={0: {"calories": 1800, "protein_g": 100}})


def test_override_violates_fat_ceiling_raises():
    # fat_g=80 > fat_ceiling_g=65
    with pytest.raises(ValueError, match="fat"):
        _recompute(overrides={0: {"calories": 1800, "fat_g": 80}})


def test_override_exhausts_remaining_budget_below_floor_raises():
    # Monday=9000; remaining=12600-9000=3600 for 6 days = 600/day
    # 600 < 175*4+65*9=1285; carbs_kcal < 0 → cannot satisfy constraints
    with pytest.raises(ValueError, match="cannot satisfy"):
        _recompute(overrides={1: {"calories": 9000}})
