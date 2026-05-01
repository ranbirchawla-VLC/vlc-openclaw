"""Tests for context_builder.py."""

from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from context_builder import run_context_builder

# ── constants ─────────────────────────────────────────────────────────────────

_USER_ID = 99
_TZ = "America/Denver"
_TODAY = date(2026, 4, 29)  # Wednesday; weekday=2

_MESOCYCLE = {
    "mesocycle_id": 1,
    "user_id": _USER_ID,
    "name": "Spring Cut 2026",
    "weeks": 12,
    "start_date": "2026-04-15",  # 14 days before _TODAY → week 3
    "end_date": "2026-07-08",
    "dose_weekday": 2,  # Wednesday; offset for _TODAY = (2-2)%7 = 0
    "macro_table": [
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
        {"calories": 1850, "protein_g": 175, "fat_g": 65, "carbs_g": 141, "restrictions": []},
    ],
    "intent": {"target_deficit_kcal": 3500, "protein_floor_g": 175, "fat_ceiling_g": 65, "rationale": ""},
    "status": "active",
    "created_at": "2026-04-15T00:00:00Z",
    "ended_at": None,
}

# Timestamps that land on _TODAY (2026-04-29) in America/Denver (MDT = UTC-6)
_LOG_BANANA = {
    "log_id": 1, "user_id": _USER_ID,
    "timestamp_utc": "2026-04-29T14:00:00Z",  # 08:00 MDT → today
    "timezone_at_log": _TZ,
    "food_description": "banana",
    "macros": {"calories": 121, "protein_g": 2, "fat_g": 0, "carbs_g": 31},
    "source": "ad_hoc", "recipe_id": None, "recipe_name_snapshot": None, "supersedes": None,
}
_LOG_SHAKE = {
    "log_id": 2, "user_id": _USER_ID,
    "timestamp_utc": "2026-04-29T20:00:00Z",  # 14:00 MDT → today
    "timezone_at_log": _TZ,
    "food_description": "protein shake",
    "macros": {"calories": 322, "protein_g": 56, "fat_g": 16, "carbs_g": 4},
    "source": "recipe", "recipe_id": 1, "recipe_name_snapshot": "Full Protein Shake", "supersedes": None,
}
# Lands on 2026-04-28 22:00 MDT → yesterday
_LOG_YESTERDAY = {
    "log_id": 3, "user_id": _USER_ID,
    "timestamp_utc": "2026-04-29T04:00:00Z",
    "timezone_at_log": _TZ,
    "food_description": "oatmeal",
    "macros": {"calories": 350, "protein_g": 15, "fat_g": 6, "carbs_g": 55},
    "source": "ad_hoc", "recipe_id": None, "recipe_name_snapshot": None, "supersedes": None,
}
# Superseded entry: _LOG_CORRECTION (log_id=5) supersedes _LOG_ORIGINAL (log_id=4)
_LOG_ORIGINAL = {
    "log_id": 4, "user_id": _USER_ID,
    "timestamp_utc": "2026-04-29T15:00:00Z",
    "timezone_at_log": _TZ,
    "food_description": "wrong entry",
    "macros": {"calories": 100, "protein_g": 5, "fat_g": 2, "carbs_g": 10},
    "source": "ad_hoc", "recipe_id": None, "recipe_name_snapshot": None, "supersedes": None,
}
_LOG_CORRECTION = {
    "log_id": 5, "user_id": _USER_ID,
    "timestamp_utc": "2026-04-29T16:00:00Z",
    "timezone_at_log": _TZ,
    "food_description": "corrected entry",
    "macros": {"calories": 150, "protein_g": 8, "fat_g": 3, "carbs_g": 15},
    "source": "ad_hoc", "recipe_id": None, "recipe_name_snapshot": None, "supersedes": 4,
}

_RECIPES = [
    {
        "recipe_id": 1, "user_id": _USER_ID, "name": "Zebra Smoothie",
        "macros": {"calories": 200, "protein_g": 20, "fat_g": 5, "carbs_g": 25},
        "ingredients": [], "created_at": "2026-04-01T00:00:00Z",
    },
    {
        "recipe_id": 2, "user_id": _USER_ID, "name": "Apple Oats",
        "macros": {"calories": 350, "protein_g": 12, "fat_g": 6, "carbs_g": 60},
        "ingredients": [], "created_at": "2026-04-02T00:00:00Z",
    },
]


# ── fixture helpers ───────────────────────────────────────────────────────────

def _write_mesocycle(tmp_path: Path, cycle: dict) -> None:
    d = tmp_path / str(_USER_ID) / "mesocycles"
    d.mkdir(parents=True, exist_ok=True)
    (d / "active.txt").write_text(f"{cycle['mesocycle_id']}\n")
    (d / f"{cycle['mesocycle_id']}.json").write_text(json.dumps(cycle))


def _write_meal_logs(tmp_path: Path, entries: list[dict]) -> None:
    d = tmp_path / str(_USER_ID)
    d.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(e) for e in entries)
    (d / "meal_log.jsonl").write_text(lines + "\n")


def _write_recipes(tmp_path: Path, recipes: list[dict]) -> None:
    d = tmp_path / str(_USER_ID)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recipes.json").write_text(json.dumps(recipes))


def _write_user_profile(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "USER.md"
    p.write_text(content)
    return p


def _ctx(tmp_path: Path, today: date = _TODAY, user_profile_path: str = "") -> dict:
    return run_context_builder(
        user_id=_USER_ID,
        active_timezone=_TZ,
        data_root=str(tmp_path),
        user_profile_path=user_profile_path,
        today=today,
    )


# ── date injection ────────────────────────────────────────────────────────────

def test_date_iso_matches_injected_date(tmp_path):
    result = _ctx(tmp_path)
    assert result["date"]["iso"] == "2026-04-29"


def test_date_day_name_matches_injected_date(tmp_path):
    result = _ctx(tmp_path)
    assert result["date"]["day_name"] == "Wednesday"


def test_date_from_system_clock_when_today_none(tmp_path):
    from datetime import datetime
    import zoneinfo
    # Capture expected_iso BEFORE calling the function to avoid midnight-straddle flake
    tz = zoneinfo.ZoneInfo(_TZ)
    expected_iso = datetime.now(tz).date().isoformat()
    result = run_context_builder(
        user_id=_USER_ID,
        active_timezone=_TZ,
        data_root=str(tmp_path),
        user_profile_path="",
        today=None,
    )
    assert result["date"]["iso"] == expected_iso


def test_different_date_returns_correct_day_name(tmp_path):
    # 2026-01-15 is a Thursday
    result = _ctx(tmp_path, today=date(2026, 1, 15))
    assert result["date"]["iso"] == "2026-01-15"
    assert result["date"]["day_name"] == "Thursday"


# ── mesocycle ─────────────────────────────────────────────────────────────────

def test_no_mesocycle_returns_none(tmp_path):
    result = _ctx(tmp_path)
    assert result["mesocycle"] is None


def test_mesocycle_name(tmp_path):
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path)
    assert result["mesocycle"]["name"] == "Spring Cut 2026"


def test_mesocycle_week_3(tmp_path):
    # start_date=2026-04-15; today=2026-04-29 → 14 days → week 3
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path)
    assert result["mesocycle"]["week"] == 3


def test_mesocycle_week_1_on_start_date(tmp_path):
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path, today=date(2026, 4, 15))  # start_date itself
    assert result["mesocycle"]["week"] == 1


def test_mesocycle_targets(tmp_path):
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path)
    targets = result["mesocycle"]["targets"]
    assert targets["calories"] == 1850
    assert targets["protein_g"] == 175
    assert targets["fat_g"] == 65
    assert targets["carbs_g"] == 141


def test_mesocycle_not_expired_when_active(tmp_path):
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path)
    assert result["mesocycle"]["is_expired"] is False


def test_mesocycle_expired_when_past_end_date(tmp_path):
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path, today=date(2026, 7, 10))  # after 2026-07-08
    assert result["mesocycle"]["is_expired"] is True


def test_future_dated_cycle_week_clamped_to_one_and_warns(tmp_path, capsys):
    # today (2026-04-29) < start_date (2026-05-01); raw_week=0; clamp to 1
    future_cycle = {**_MESOCYCLE, "start_date": "2026-05-01", "end_date": "2026-08-01"}
    _write_mesocycle(tmp_path, future_cycle)
    result = _ctx(tmp_path)
    assert result["mesocycle"]["week"] == 1
    assert "future_dated_cycle" in capsys.readouterr().err


def test_future_dated_cycle_deeply_negative_raw_week_clamped(tmp_path, capsys):
    # today (2026-04-29) < start_date (2026-05-10); raw_week = (-11//7)+1 = -1; clamp to 1
    future_cycle = {**_MESOCYCLE, "start_date": "2026-05-10", "end_date": "2026-08-01"}
    _write_mesocycle(tmp_path, future_cycle)
    result = _ctx(tmp_path)
    assert result["mesocycle"]["week"] == 1
    assert "future_dated_cycle" in capsys.readouterr().err


def test_mesocycle_not_expired_on_last_active_day(tmp_path):
    # end_date=2026-07-08 is exclusive; 2026-07-07 is the last active day
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path, today=date(2026, 7, 7))
    assert result["mesocycle"]["is_expired"] is False


def test_mesocycle_expired_on_end_date(tmp_path):
    # end_date itself is the first expired day (exclusive upper bound)
    _write_mesocycle(tmp_path, _MESOCYCLE)
    result = _ctx(tmp_path, today=date(2026, 7, 8))
    assert result["mesocycle"]["is_expired"] is True


# ── recipes ───────────────────────────────────────────────────────────────────

def test_recipes_empty_when_no_file(tmp_path):
    result = _ctx(tmp_path)
    assert result["recipes"] == []


def test_recipes_populated(tmp_path):
    _write_recipes(tmp_path, _RECIPES)
    result = _ctx(tmp_path)
    assert len(result["recipes"]) == 2


def test_recipes_are_name_strings_alphabetically_sorted(tmp_path):
    """Injected recipes are plain name strings, alphabetical order from source."""
    _write_recipes(tmp_path, _RECIPES)
    result = _ctx(tmp_path)
    # _RECIPES: "Zebra Smoothie" (id=1), "Apple Oats" (id=2); source sorts alpha
    assert result["recipes"] == ["Apple Oats", "Zebra Smoothie"]


def test_recipes_names_only_no_ids_or_macros(tmp_path):
    """Injected recipes contain only name strings; recipe_id and macro values absent."""
    _write_recipes(tmp_path, _RECIPES)
    result = _ctx(tmp_path)
    assert all(isinstance(r, str) for r in result["recipes"])


def test_recipes_names_present_in_output(tmp_path):
    """Each recipe name from the fixture appears verbatim in the injected list."""
    _write_recipes(tmp_path, _RECIPES)
    result = _ctx(tmp_path)
    assert "Zebra Smoothie" in result["recipes"]
    assert "Apple Oats" in result["recipes"]


# ── totals ────────────────────────────────────────────────────────────────────

def test_totals_all_zero_when_no_log(tmp_path):
    result = _ctx(tmp_path)
    assert result["totals"] == {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}


def test_totals_sum_todays_entries(tmp_path):
    _write_meal_logs(tmp_path, [_LOG_BANANA, _LOG_SHAKE])
    result = _ctx(tmp_path)
    totals = result["totals"]
    assert totals["calories"] == 121 + 322
    assert totals["protein_g"] == 2 + 56
    assert totals["fat_g"] == 0 + 16
    assert totals["carbs_g"] == 31 + 4


def test_totals_excludes_yesterdays_entries(tmp_path):
    _write_meal_logs(tmp_path, [_LOG_BANANA, _LOG_YESTERDAY])
    result = _ctx(tmp_path)
    assert result["totals"]["calories"] == 121  # only banana; not oatmeal (yesterday)


def test_totals_reconciles_superseded_entries(tmp_path):
    # _LOG_ORIGINAL (id=4) superseded by _LOG_CORRECTION (id=5)
    _write_meal_logs(tmp_path, [_LOG_ORIGINAL, _LOG_CORRECTION])
    result = _ctx(tmp_path)
    # Only correction survives; original excluded
    assert result["totals"]["calories"] == 150
    assert result["totals"]["protein_g"] == 8


# ── user profile ──────────────────────────────────────────────────────────────

def test_user_profile_reads_file(tmp_path):
    p = _write_user_profile(tmp_path, "# Users\nRanbir\n")
    result = run_context_builder(
        user_id=_USER_ID,
        active_timezone=_TZ,
        data_root=str(tmp_path),
        user_profile_path=str(p),
        today=_TODAY,
    )
    assert result["user_profile"] == "# Users\nRanbir\n"


def test_user_profile_empty_string_when_file_missing(tmp_path):
    result = _ctx(tmp_path, user_profile_path="/nonexistent/USER.md")
    assert result["user_profile"] == ""
