"""Tests for scripts/write_meal_log.py; TDD first."""

from __future__ import annotations
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from write_meal_log import _Input, run_write_meal_log
from common import CorruptStateError
from models import MealLog


# ── helpers ───────────────────────────────────────────────────────────────────

def _ad_hoc_input(**kwargs) -> _Input:
    defaults = dict(
        user_id=42,
        food_description="protein shake",
        macros=dict(calories=200, protein_g=30, fat_g=5, carbs_g=10),
        source="ad_hoc",
        recipe_id=None,
        recipe_name_snapshot=None,
        supersedes_log_id=None,
        active_timezone="America/Denver",
    )
    return _Input(**{**defaults, **kwargs})


def _recipe_input(**kwargs) -> _Input:
    defaults = dict(
        user_id=42,
        food_description="usual lunch",
        macros=dict(calories=600, protein_g=50, fat_g=20, carbs_g=60),
        source="recipe",
        recipe_id=7,
        recipe_name_snapshot="usual lunch",
        supersedes_log_id=None,
        active_timezone="America/Denver",
    )
    return _Input(**{**defaults, **kwargs})


# ── first write: log_id = 1, file created, valid JSON ─────────────────────────

def test_first_write_log_id_is_one(tmp_path):
    inp = _ad_hoc_input()
    result = run_write_meal_log(inp, data_root=str(tmp_path))
    assert result["log_id"] == 1


def test_first_write_creates_file(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))
    log_file = tmp_path / "42" / "meal_log.jsonl"
    assert log_file.exists()


def test_first_write_line_parses_to_meal_log(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))
    log_file = tmp_path / "42" / "meal_log.jsonl"
    line = json.loads(log_file.read_text().strip())
    log = MealLog(**line)
    assert log.log_id == 1
    assert log.user_id == 42
    assert log.source == "ad_hoc"
    assert log.macros.calories == 200


# ── second write: log_id = 2, file has two lines ──────────────────────────────

def test_second_write_log_id_is_two(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))
    result = run_write_meal_log(inp, data_root=str(tmp_path))
    assert result["log_id"] == 2


def test_second_write_file_has_two_lines(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))
    run_write_meal_log(inp, data_root=str(tmp_path))
    log_file = tmp_path / "42" / "meal_log.jsonl"
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2


# ── supersedes_log_id passes through ─────────────────────────────────────────

def test_supersedes_passes_through_to_record(tmp_path):
    first = _ad_hoc_input()
    run_write_meal_log(first, data_root=str(tmp_path))
    correction = _ad_hoc_input(supersedes_log_id=1)
    result = run_write_meal_log(correction, data_root=str(tmp_path))
    assert result["log_id"] == 2
    log_file = tmp_path / "42" / "meal_log.jsonl"
    lines = log_file.read_text().strip().splitlines()
    second_record = json.loads(lines[1])
    assert second_record["supersedes"] == 1


# ── input validation ──────────────────────────────────────────────────────────

def test_recipe_source_with_null_recipe_id_rejected(tmp_path):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _Input(
            user_id=42,
            food_description="lunch",
            macros=dict(calories=600, protein_g=50, fat_g=20, carbs_g=60),
            source="recipe",
            recipe_id=None,
            recipe_name_snapshot=None,
            supersedes_log_id=None,
            active_timezone="America/Denver",
        )


def test_ad_hoc_source_with_recipe_id_rejected(tmp_path):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _Input(
            user_id=42,
            food_description="shake",
            macros=dict(calories=200, protein_g=30, fat_g=5, carbs_g=10),
            source="ad_hoc",
            recipe_id=5,
            recipe_name_snapshot=None,
            supersedes_log_id=None,
            active_timezone="America/Denver",
        )


# ── concurrent-ish: two back-to-back writes yield 1 and 2 ────────────────────

def test_corrupt_jsonl_raises_on_next_log_id(tmp_path):
    # Corrupt line in meal_log.jsonl must raise CorruptStateError, not silently
    # skip and risk log_id collision.
    log_path = tmp_path / "42" / "meal_log.jsonl"
    os.makedirs(str(tmp_path / "42"), exist_ok=True)
    log_path.write_text("{ not valid json }\n")
    inp = _ad_hoc_input()
    with pytest.raises(CorruptStateError):
        run_write_meal_log(inp, data_root=str(tmp_path))


def test_two_back_to_back_writes_no_collision(tmp_path):
    inp = _ad_hoc_input()
    r1 = run_write_meal_log(inp, data_root=str(tmp_path))
    r2 = run_write_meal_log(inp, data_root=str(tmp_path))
    assert r1["log_id"] == 1
    assert r2["log_id"] == 2


# ── atomic append: failure before write leaves prior lines intact ─────────────

def test_failed_write_leaves_prior_lines_intact(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))  # line 1 written cleanly

    import write_meal_log as wml_mod

    def raising_append(path: str, record: dict) -> None:
        raise RuntimeError("simulated append failure")

    # Patch append_jsonl in the write_meal_log module namespace so the
    # failure happens at the actual JSONL write, not at the trace json.dumps.
    with patch.object(wml_mod, "append_jsonl", raising_append):
        with pytest.raises(RuntimeError):
            run_write_meal_log(inp, data_root=str(tmp_path))

    log_file = tmp_path / "42" / "meal_log.jsonl"
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1  # only the first record survived
    assert json.loads(lines[0])["log_id"] == 1


# ── timestamp and timezone fields set by Python ───────────────────────────────

def test_timestamp_utc_ends_with_z(tmp_path):
    inp = _ad_hoc_input()
    run_write_meal_log(inp, data_root=str(tmp_path))
    log_file = tmp_path / "42" / "meal_log.jsonl"
    record = json.loads(log_file.read_text().strip())
    assert record["timestamp_utc"].endswith("Z")


def test_timezone_at_log_matches_input(tmp_path):
    inp = _ad_hoc_input(active_timezone="Europe/London")
    run_write_meal_log(inp, data_root=str(tmp_path))
    log_file = tmp_path / "42" / "meal_log.jsonl"
    record = json.loads(log_file.read_text().strip())
    assert record["timezone_at_log"] == "Europe/London"


# ── NB-6: macros field is now typed Macros, not dict ─────────────────────────

def test_macros_float_protein_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _Input(
            user_id=42,
            food_description="protein shake",
            macros=dict(calories=200, protein_g=30.5, fat_g=5, carbs_g=10),
            source="ad_hoc",
            recipe_id=None,
            recipe_name_snapshot=None,
            supersedes_log_id=None,
            active_timezone="America/Denver",
        )
