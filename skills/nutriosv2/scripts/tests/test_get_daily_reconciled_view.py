"""Tests for scripts/get_daily_reconciled_view.py — TDD first."""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from get_daily_reconciled_view import _Input, run_get_daily_reconciled_view
from common import CorruptStateError, append_jsonl
from lock_mesocycle import _Input as LockInput, run_lock_mesocycle


# ── fixtures ──────────────────────────────────────────────────────────────────

def _seven_rows(calories: int = 2000) -> list[dict]:
    return [
        dict(calories=calories, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for _ in range(7)
    ]


def _lock_cycle(tmp_path, user_id: int = 42, start_date: str = "2026-04-21",
                dose_weekday: int = 0, calories: int = 2000, weeks: int = 4) -> None:
    # start_date="2026-04-21" is a Tuesday; dose_weekday=0 (Mon) — misaligned per NB-10/NB-11.
    # Tests exercise the offset formula, not lock_mesocycle validation.
    inp = LockInput(
        user_id=user_id,
        name="test cycle",
        weeks=weeks,
        start_date=start_date,
        dose_weekday=dose_weekday,
        macro_table=_seven_rows(calories),
        intent=dict(target_deficit_kcal=3500, protein_floor_g=180, rationale="cut"),
    )
    run_lock_mesocycle(inp, data_root=str(tmp_path))


def _append_meal(tmp_path, user_id: int, log_id: int, timestamp_utc: str,
                 timezone_at_log: str = "America/Denver", calories: int = 300,
                 supersedes: int | None = None) -> None:
    path = str(tmp_path / str(user_id) / "meal_log.jsonl")
    record = dict(
        log_id=log_id,
        user_id=user_id,
        timestamp_utc=timestamp_utc,
        timezone_at_log=timezone_at_log,
        food_description="test food",
        macros=dict(calories=calories, protein_g=20, fat_g=10, carbs_g=30),
        source="ad_hoc",
        recipe_id=None,
        recipe_name_snapshot=None,
        supersedes=supersedes,
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    append_jsonl(path, record)


def _view(tmp_path, user_id: int = 42, date: str = "2026-04-25",
          tz: str = "America/Denver") -> dict:
    inp = _Input(user_id=user_id, date=date, active_timezone=tz)
    return run_get_daily_reconciled_view(inp, data_root=str(tmp_path))


# ── empty log returns zeros, target from mesocycle ───────────────────────────

def test_empty_log_returns_zero_consumed(tmp_path):
    _lock_cycle(tmp_path)
    result = _view(tmp_path)
    assert result["consumed"]["calories"] == 0
    assert result["consumed"]["protein_g"] == 0


def test_empty_log_target_from_active_mesocycle(tmp_path):
    _lock_cycle(tmp_path, calories=2000)
    result = _view(tmp_path)
    assert result["target"] is not None
    assert result["target"]["calories"] == 2000


def test_no_active_mesocycle_target_is_null(tmp_path):
    # No cycle locked — active.txt absent.
    result = _view(tmp_path)
    assert result["target"] is None
    assert result["remaining"] is None
    assert result["consumed"]["calories"] == 0


# ── single entry today: consumed reflects it ─────────────────────────────────

def test_single_entry_today_consumed(tmp_path):
    _lock_cycle(tmp_path)
    # 2026-04-25T18:00:00Z = noon MDT (UTC-6); in Denver this is 2026-04-25
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-25T18:00:00Z", calories=400)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 400


def test_single_entry_remaining_equals_target_minus_consumed(tmp_path):
    _lock_cycle(tmp_path, calories=2000)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-25T18:00:00Z", calories=400)
    result = _view(tmp_path, date="2026-04-25")
    assert result["remaining"]["calories"] == 2000 - 400


# ── date filter: yesterday's entry excluded ───────────────────────────────────

def test_yesterday_entry_excluded(tmp_path):
    _lock_cycle(tmp_path)
    # 2026-04-24 in UTC is 2026-04-23 in Denver (UTC-6 in April)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-24T18:00:00Z", calories=500)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 0


# ── timezone filter: entry past midnight in active_timezone ──────────────────

def test_entry_past_midnight_local_included_by_local_date(tmp_path):
    _lock_cycle(tmp_path)
    # 2026-04-26T04:00:00Z = 2026-04-25 22:00 MDT (UTC-6).
    # UTC date is 2026-04-26, local Denver date is 2026-04-25.
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-26T04:00:00Z", calories=300)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 300


def test_entry_utc_yesterday_but_local_today_included(tmp_path):
    # UTC-6: 2026-04-25T00:30:00Z = 2026-04-24 18:30 MDT → local date 2026-04-24
    # 2026-04-25T06:01:00Z = 2026-04-25 00:01 MDT → local date 2026-04-25 ✓
    _lock_cycle(tmp_path)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-25T06:01:00Z", calories=250)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 250


@pytest.mark.parametrize("timestamp_utc,tz,date,expected_calories", [
    # US spring DST transition: 2026-03-08 02:00 clocks forward to 03:00 (MST→MDT)
    # 2026-03-08T07:00:00Z = 2026-03-08 00:00 MST (UTC-7) → local date 2026-03-08
    ("2026-03-08T07:00:00Z", "America/Denver", "2026-03-08", 100),
    # After DST spring-forward: 2026-03-09T06:00:00Z = 2026-03-09 00:00 MDT (UTC-6)
    ("2026-03-09T06:00:00Z", "America/Denver", "2026-03-09", 200),
])
def test_dst_boundary_date_filter(tmp_path, timestamp_utc, tz, date, expected_calories):
    _lock_cycle(tmp_path, start_date="2026-03-02", dose_weekday=0)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc=timestamp_utc,
                 timezone_at_log=tz, calories=expected_calories)
    result = _view(tmp_path, date=date, tz=tz)
    assert result["consumed"]["calories"] == expected_calories


# ── supersede: second supersedes first, only second counts ───────────────────

def test_second_supersedes_first_only_second_macros(tmp_path):
    _lock_cycle(tmp_path)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-25T18:00:00Z", calories=600)
    _append_meal(tmp_path, user_id=42, log_id=2, timestamp_utc="2026-04-25T19:00:00Z",
                 calories=400, supersedes=1)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 400
    assert len(result["entries"]) == 1
    assert result["entries"][0]["log_id"] == 2


def test_supersede_chain_three_entries_only_last_counts(tmp_path):
    _lock_cycle(tmp_path)
    _append_meal(tmp_path, user_id=42, log_id=1, timestamp_utc="2026-04-25T17:00:00Z", calories=600)
    _append_meal(tmp_path, user_id=42, log_id=2, timestamp_utc="2026-04-25T18:00:00Z",
                 calories=500, supersedes=1)
    _append_meal(tmp_path, user_id=42, log_id=3, timestamp_utc="2026-04-25T19:00:00Z",
                 calories=450, supersedes=2)
    result = _view(tmp_path, date="2026-04-25")
    assert result["consumed"]["calories"] == 450
    assert len(result["entries"]) == 1
    assert result["entries"][0]["log_id"] == 3


# ── corrupt JSONL line raises CorruptStateError ───────────────────────────────

def test_corrupt_jsonl_line_raises(tmp_path):
    _lock_cycle(tmp_path)
    log_path = tmp_path / "42" / "meal_log.jsonl"
    os.makedirs(str(tmp_path / "42"), exist_ok=True)
    log_path.write_text("{ valid json line: false }\n")
    with pytest.raises(CorruptStateError) as exc_info:
        _view(tmp_path)
    assert "meal_log.jsonl" in str(exc_info.value)


# ── expired mesocycle: target returned with is_expired=True ──────────────────

def test_expired_mesocycle_returns_target_with_is_expired(tmp_path):
    # 1-week cycle starting 2026-04-14 → end_date = 2026-04-21.
    # Query date 2026-04-25 is past end_date.
    _lock_cycle(tmp_path, start_date="2026-04-14", dose_weekday=1, calories=2000, weeks=1)
    result = _view(tmp_path, date="2026-04-25")
    assert result["target"] is not None
    assert result["is_expired"] is True


def test_active_mesocycle_is_expired_false(tmp_path):
    _lock_cycle(tmp_path, start_date="2026-04-21", dose_weekday=1, calories=2000)
    result = _view(tmp_path, date="2026-04-25")
    assert result["is_expired"] is False


# ── dose-offset math: offset = (date.weekday() - dose_weekday) % 7 ───────────

def test_dose_offset_zero_on_dose_weekday(tmp_path):
    # dose_weekday=1 (Tuesday). Query on a Tuesday: 2026-04-28 (Tuesday).
    # Offset should be 0 → macro_table[0].
    rows = [
        dict(calories=1000 + i * 100, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for i in range(7)
    ]
    inp = LockInput(
        user_id=42, name="offset test", weeks=8,
        start_date="2026-04-21",  # Tuesday
        dose_weekday=1,  # Tuesday
        macro_table=rows,
        intent=dict(rationale=""),
    )
    run_lock_mesocycle(inp, data_root=str(tmp_path))
    result = _view(tmp_path, date="2026-04-28")  # Tuesday → offset 0
    assert result["target"]["calories"] == 1000


def test_dose_offset_one_day_after(tmp_path):
    # dose_weekday=1 (Tuesday). Wednesday = offset 1 → macro_table[1].
    rows = [
        dict(calories=1000 + i * 100, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for i in range(7)
    ]
    inp = LockInput(
        user_id=42, name="offset test", weeks=8,
        start_date="2026-04-21",
        dose_weekday=1,
        macro_table=rows,
        intent=dict(rationale=""),
    )
    run_lock_mesocycle(inp, data_root=str(tmp_path))
    result = _view(tmp_path, date="2026-04-29")  # Wednesday → offset 1
    assert result["target"]["calories"] == 1100


def test_dose_offset_six_days_after(tmp_path):
    # dose_weekday=1 (Tuesday). Monday = offset 6 → macro_table[6].
    rows = [
        dict(calories=1000 + i * 100, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for i in range(7)
    ]
    inp = LockInput(
        user_id=42, name="offset test", weeks=8,
        start_date="2026-04-21",
        dose_weekday=1,
        macro_table=rows,
        intent=dict(rationale=""),
    )
    run_lock_mesocycle(inp, data_root=str(tmp_path))
    result = _view(tmp_path, date="2026-04-27")  # Monday → offset 6
    assert result["target"]["calories"] == 1600


def test_dose_offset_wraps_correctly_across_weeks(tmp_path):
    # dose_weekday=1 (Tuesday). Two Tuesdays should both be offset 0.
    rows = [
        dict(calories=1000 + i * 100, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for i in range(7)
    ]
    inp = LockInput(
        user_id=42, name="offset test", weeks=8,
        start_date="2026-04-21",
        dose_weekday=1,
        macro_table=rows,
        intent=dict(rationale=""),
    )
    run_lock_mesocycle(inp, data_root=str(tmp_path))
    result1 = _view(tmp_path, date="2026-04-28")  # Tuesday week 1
    result2 = _view(tmp_path, date="2026-05-05")  # Tuesday week 2
    assert result1["target"]["calories"] == 1000
    assert result2["target"]["calories"] == 1000
