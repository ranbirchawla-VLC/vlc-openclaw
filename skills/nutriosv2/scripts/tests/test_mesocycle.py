"""Tests for lock_mesocycle, get_active_mesocycle, compute_candidate_macros."""

from __future__ import annotations
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from compute_candidate_macros import _Input as MacrosInput, compute
from lock_mesocycle import _Input as LockInput, run_lock_mesocycle
from get_active_mesocycle import run_get_active_mesocycle


# ── helpers ───────────────────────────────────────────────────────────────────

def _seven_rows() -> list[dict]:
    return [
        dict(calories=2000, protein_g=180, fat_g=70, carbs_g=200, restrictions=[])
        for _ in range(7)
    ]


def _lock_input(**kwargs) -> LockInput:
    defaults = dict(
        user_id=1001,
        name="test cycle 1",
        weeks=4,
        start_date="2026-05-01",
        dose_weekday=0,
        macro_table=_seven_rows(),
        intent=dict(target_deficit_kcal=3500, protein_floor_g=180, rationale="cut"),
    )
    return LockInput(**{**defaults, **kwargs})


# ── compute_candidate_macros ──────────────────────────────────────────────────

def test_compute_all_inputs():
    # target_deficit_kcal is WEEKLY; 3500/7 = 500/day → calories = 2400 - 500 = 1900
    inp = MacrosInput(
        estimated_tdee_kcal=2400,
        target_deficit_kcal=3500,
        protein_floor_g=180,
        fat_ceiling_g=60,
    )
    result = compute(inp)
    assert result["calories"] == 1900
    assert result["protein_g"] == 180
    assert result["fat_g"] == 60
    # carbs = (1900 - 180*4 - 60*9) // 4 = (1900 - 720 - 540) // 4 = 640 // 4 = 160
    assert result["carbs_g"] == 160


def test_compute_weekly_deficit_1850_tdee_2350():
    # Regression: 1850/7 ≈ 264.3/day → 2350 - 264.3 ≈ 2086 (the fabrication bug case)
    inp = MacrosInput(
        estimated_tdee_kcal=2350,
        target_deficit_kcal=1850,
        protein_floor_g=175,
        fat_ceiling_g=65,
    )
    result = compute(inp)
    assert abs(result["calories"] - 2086) <= 1  # ±1 kcal rounding tolerance
    assert result["protein_g"] == 175
    assert result["fat_g"] == 65


def test_compute_deficit_zero_equals_tdee():
    inp = MacrosInput(estimated_tdee_kcal=2350, target_deficit_kcal=0)
    result = compute(inp)
    assert result["calories"] == 2350


def test_compute_partial_inputs_calories_only():
    # 3500 weekly / 7 = 500/day; 2400 - 500 = 1900
    inp = MacrosInput(estimated_tdee_kcal=2400, target_deficit_kcal=3500)
    result = compute(inp)
    assert result["calories"] == 1900
    assert result["protein_g"] is None
    assert result["fat_g"] is None
    assert result["carbs_g"] is None


def test_compute_no_inputs():
    inp = MacrosInput()
    result = compute(inp)
    assert all(v is None for v in result.values())


def test_compute_overconstrained_returns_none_carbs():
    # 3500 weekly / 7 = 500/day; 1500 - 500 = 1000 → protein + fat exceeds → null carbs
    inp = MacrosInput(
        estimated_tdee_kcal=1500,
        target_deficit_kcal=3500,
        protein_floor_g=200,
        fat_ceiling_g=80,
    )
    result = compute(inp)
    assert result["calories"] == 1000
    # 1000 - 200*4 - 80*9 = 1000 - 800 - 720 = -520 → null
    assert result["carbs_g"] is None


def test_compute_returns_weekly_and_daily_deficit():
    inp = MacrosInput(
        estimated_tdee_kcal=2400,
        target_deficit_kcal=3500,
        protein_floor_g=180,
        fat_ceiling_g=60,
    )
    result = compute(inp)
    assert result["weekly_deficit_kcal"] == 3500
    assert result["daily_deficit_kcal"] == 500


def test_compute_daily_unit_converts_to_weekly():
    # 500 daily → 3500 weekly; same macros as weekly=3500 with TDEE=2400
    inp_daily = MacrosInput(
        estimated_tdee_kcal=2400,
        target_deficit_kcal=500,
        deficit_unit="daily_kcal",
        protein_floor_g=180,
        fat_ceiling_g=60,
    )
    inp_weekly = MacrosInput(
        estimated_tdee_kcal=2400,
        target_deficit_kcal=3500,
        protein_floor_g=180,
        fat_ceiling_g=60,
    )
    r_daily = compute(inp_daily)
    r_weekly = compute(inp_weekly)
    assert r_daily["weekly_deficit_kcal"] == 3500
    assert r_daily["daily_deficit_kcal"] == 500
    assert r_daily["calories"] == r_weekly["calories"]
    assert r_daily["protein_g"] == r_weekly["protein_g"]
    assert r_daily["fat_g"] == r_weekly["fat_g"]
    assert r_daily["carbs_g"] == r_weekly["carbs_g"]


def test_compute_daily_unit_without_tdee_returns_deficit_only():
    inp = MacrosInput(target_deficit_kcal=264, deficit_unit="daily_kcal")
    result = compute(inp)
    assert result["weekly_deficit_kcal"] == 264 * 7
    assert result["daily_deficit_kcal"] == 264
    assert result["calories"] is None


def test_compute_weekly_unit_explicit():
    # Explicit weekly_kcal behaves identically to default
    inp = MacrosInput(
        estimated_tdee_kcal=2350,
        target_deficit_kcal=1850,
        deficit_unit="weekly_kcal",
        protein_floor_g=175,
        fat_ceiling_g=65,
    )
    result = compute(inp)
    assert result["weekly_deficit_kcal"] == 1850
    assert abs(result["calories"] - 2086) <= 1


# ── lock_mesocycle ────────────────────────────────────────────────────────────

def test_lock_first_cycle_id_is_one(tmp_path):
    inp = _lock_input()
    result = run_lock_mesocycle(inp, data_root=str(tmp_path))
    assert result["mesocycle_id"] == 1
    cycle_file = tmp_path / "1001" / "mesocycles" / "1.json"
    assert cycle_file.exists()


def test_lock_first_cycle_active_txt_points_to_it(tmp_path):
    inp = _lock_input()
    run_lock_mesocycle(inp, data_root=str(tmp_path))
    active_txt = tmp_path / "1001" / "mesocycles" / "active.txt"
    assert active_txt.read_text().strip() == "1"


def test_lock_second_cycle_ends_prior(tmp_path):
    run_lock_mesocycle(_lock_input(name="cycle 1"), data_root=str(tmp_path))
    result = run_lock_mesocycle(_lock_input(name="cycle 2"), data_root=str(tmp_path))
    assert result["mesocycle_id"] == 2

    cycle1 = json.loads((tmp_path / "1001" / "mesocycles" / "1.json").read_text())
    assert cycle1["status"] == "ended"
    assert cycle1["ended_at"] is not None

    active_txt = tmp_path / "1001" / "mesocycles" / "active.txt"
    assert active_txt.read_text().strip() == "2"


def test_lock_end_date_four_weeks(tmp_path):
    run_lock_mesocycle(_lock_input(weeks=4, start_date="2026-05-01"), data_root=str(tmp_path))
    data = json.loads((tmp_path / "1001" / "mesocycles" / "1.json").read_text())
    assert data["end_date"] == "2026-05-29"


def test_lock_end_date_six_weeks(tmp_path):
    run_lock_mesocycle(_lock_input(weeks=6, start_date="2026-05-01"), data_root=str(tmp_path))
    data = json.loads((tmp_path / "1001" / "mesocycles" / "1.json").read_text())
    assert data["end_date"] == "2026-06-12"


def test_lock_end_date_twelve_weeks_across_dst(tmp_path):
    # 2026-03-01 + 84 days crosses US spring DST; calendar math must be unaffected
    run_lock_mesocycle(_lock_input(weeks=12, start_date="2026-03-01"), data_root=str(tmp_path))
    data = json.loads((tmp_path / "1001" / "mesocycles" / "1.json").read_text())
    assert data["end_date"] == "2026-05-24"


def test_lock_atomic_failure_leaves_prior_readable(tmp_path):
    # Create cycle 1 successfully
    run_lock_mesocycle(_lock_input(name="cycle 1"), data_root=str(tmp_path))

    import lock_mesocycle as lm_mod

    call_count = {"n": 0}
    original_replace = os.replace

    def failing_replace(src: str, dst: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated crash on second os.replace")
        return original_replace(src, dst)

    with patch.object(lm_mod.os, "replace", failing_replace):
        with pytest.raises(OSError):
            run_lock_mesocycle(_lock_input(name="cycle 2"), data_root=str(tmp_path))

    # cycle 1 file must still be readable (may be ended due to step 1 succeeding)
    cycle1_path = tmp_path / "1001" / "mesocycles" / "1.json"
    assert cycle1_path.exists()
    data = json.loads(cycle1_path.read_text())
    assert data["mesocycle_id"] == 1

    # cycle 2 file must not exist
    cycle2_path = tmp_path / "1001" / "mesocycles" / "2.json"
    assert not cycle2_path.exists()


# ── get_active_mesocycle ──────────────────────────────────────────────────────

def test_get_active_returns_active_cycle(tmp_path):
    run_lock_mesocycle(_lock_input(name="my cycle"), data_root=str(tmp_path))
    result = run_get_active_mesocycle(1001, data_root=str(tmp_path))
    assert result is not None
    assert result["name"] == "my cycle"
    assert result["status"] == "active"


def test_get_active_returns_none_when_no_active_txt(tmp_path):
    result = run_get_active_mesocycle(1001, data_root=str(tmp_path))
    assert result is None


def test_get_active_returns_none_when_active_txt_empty(tmp_path):
    active_dir = tmp_path / "1001" / "mesocycles"
    active_dir.mkdir(parents=True)
    (active_dir / "active.txt").write_text("")
    result = run_get_active_mesocycle(1001, data_root=str(tmp_path))
    assert result is None


def test_recovery_active_txt_missing_but_files_exist(tmp_path):
    # Per spec: if active.txt missing, returns None — recovery is operator concern
    run_lock_mesocycle(_lock_input(), data_root=str(tmp_path))
    (tmp_path / "1001" / "mesocycles" / "active.txt").unlink()
    result = run_get_active_mesocycle(1001, data_root=str(tmp_path))
    assert result is None
