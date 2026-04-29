"""Tests for calculate_macros.py."""

from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from calculate_macros import run_calculate_macros

_BASE = {"calories": 400, "protein_g": 30, "fat_g": 15, "carbs_g": 40}


def test_portion_one_servings_one_returns_base():
    assert run_calculate_macros(_BASE, portion=1.0, servings=1.0) == _BASE


def test_portion_half():
    result = run_calculate_macros(_BASE, portion=0.5)
    assert result["calories"] == 200
    assert result["protein_g"] == 15
    assert result["fat_g"] == 8  # round(7.5) = 8 (nearest even: 8)
    assert result["carbs_g"] == 20


def test_bankers_rounding_rounds_half_to_even():
    # 13 * 0.5 = 6.5; banker's rounding → 6 (nearest even), not 7
    base = {"calories": 13, "protein_g": 13, "fat_g": 13, "carbs_g": 13}
    result = run_calculate_macros(base, portion=0.5)
    assert result["calories"] == 6


def test_servings_double():
    result = run_calculate_macros(_BASE, portion=1.0, servings=2.0)
    assert result["calories"] == 800
    assert result["protein_g"] == 60
    assert result["fat_g"] == 30
    assert result["carbs_g"] == 80


def test_combined_portion_and_servings():
    # 0.5 portion × 2 servings = 1.0 factor
    assert run_calculate_macros(_BASE, portion=0.5, servings=2.0) == _BASE


def test_integer_portion_and_servings_coerced():
    result = run_calculate_macros(_BASE, portion=1, servings=3)
    assert result["calories"] == 1200
    assert result["protein_g"] == 90


def test_portion_zero_returns_zeros():
    result = run_calculate_macros(_BASE, portion=0)
    assert result == {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}


def test_servings_zero_returns_zeros():
    result = run_calculate_macros(_BASE, portion=1.0, servings=0)
    assert result == {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}


def test_fractional_rounding():
    # 400 * (1/3) = 133.33... → rounds to 133
    result = run_calculate_macros(_BASE, portion=1 / 3)
    assert result["calories"] == 133


def test_missing_macro_key_raises():
    bad = {"calories": 400, "protein_g": 30, "fat_g": 15}  # missing carbs_g
    with pytest.raises(Exception):
        run_calculate_macros(bad, portion=1.0)


def test_negative_portion_raises():
    with pytest.raises(Exception):
        run_calculate_macros(_BASE, portion=-0.5)


def test_negative_servings_raises():
    with pytest.raises(Exception):
        run_calculate_macros(_BASE, portion=1.0, servings=-1.0)


def test_returns_integers():
    result = run_calculate_macros(_BASE, portion=0.3)
    for v in result.values():
        assert isinstance(v, int), f"expected int, got {type(v).__name__}"


def test_whole_number_float_macros_accepted():
    # LLMs often emit 400.0 for integer-typed fields; must not raise
    float_base = {"calories": 400.0, "protein_g": 30.0, "fat_g": 15.0, "carbs_g": 40.0}
    result = run_calculate_macros(float_base, portion=1.0)
    assert result == _BASE


def test_fractional_float_macros_rejected():
    # Pydantic v2 (non-strict) accepts whole-number floats but rejects fractional ones
    float_base = {"calories": 400.9, "protein_g": 30.0, "fat_g": 15.0, "carbs_g": 40.0}
    with pytest.raises(Exception):
        run_calculate_macros(float_base, portion=1.0)
