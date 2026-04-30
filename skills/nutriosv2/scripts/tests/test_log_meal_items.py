"""Tests for log_meal_items.py; spec §7 scenarios.

Inner skills are mocked at this layer; their behavior is tested in sub-steps 2
and 3. Patch targets are the names as imported in log_meal_items.py.

Scenarios not testable at this layer (inner-skill behavior mocked away):
- #12 retry-success: tested here by mocking SemanticMatchResult(retry_occurred=True)
  and asserting the warning propagates. The retry logic itself lives in the inner skill.
- #14 retry-success for batch estimation: same pattern.
- Inner-skill prompt correctness: out of scope for this layer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from inner_skills.batch_estimate import BaseMacroEstimate, BatchEstimateResult
from inner_skills.semantic_match import SemanticMatchResult
from log_meal_items import run_log_meal_items

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_USER = 99

_SHAKE_MACROS = {"calories": 300, "protein_g": 25, "fat_g": 10, "carbs_g": 30}
_EGG_MACROS   = {"calories": 70,  "protein_g": 6,  "fat_g": 5,  "carbs_g": 0}

_SHAKE_RECORD = {
    "recipe_id": 1, "user_id": _USER, "name": "Recovery Shake",
    "ingredients": [], "macros": _SHAKE_MACROS,
    "created_at": "2026-04-30T00:00:00Z",
}
_TIKKA_RECORD = {
    "recipe_id": 2, "user_id": _USER, "name": "Chicken Tikka Lunch Bowl",
    "ingredients": [], "macros": {"calories": 550, "protein_g": 45, "fat_g": 18, "carbs_g": 50},
    "created_at": "2026-04-30T00:00:00Z",
}
_MORNING_SHAKE_RECORD = {
    "recipe_id": 3, "user_id": _USER, "name": "Morning Shake",
    "ingredients": [], "macros": {"calories": 200, "protein_g": 20, "fat_g": 5, "carbs_g": 15},
    "created_at": "2026-04-30T00:00:00Z",
}
_EVENING_SHAKE_RECORD = {
    "recipe_id": 4, "user_id": _USER, "name": "Evening Shake",
    "ingredients": [], "macros": {"calories": 180, "protein_g": 18, "fat_g": 4, "carbs_g": 12},
    "created_at": "2026-04-30T00:00:00Z",
}


def _write_recipes(tmp_path: Path, user_id: int, records: list[dict]) -> None:
    d = tmp_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recipes.json").write_text(json.dumps(records))


def _est(calories: int, protein_g: int, fat_g: int, carbs_g: int, notes: str | None = None) -> BaseMacroEstimate:
    return BaseMacroEstimate(calories=calories, protein_g=protein_g, fat_g=fat_g, carbs_g=carbs_g, notes=notes)


def _sem(matches: list[str | None], retry: bool = False) -> SemanticMatchResult:
    return SemanticMatchResult(matches=matches, retry_occurred=retry)


def _bat(items: list[BaseMacroEstimate], retry: bool = False) -> BatchEstimateResult:
    return BatchEstimateResult(items=items, retry_occurred=retry)


# ---------------------------------------------------------------------------
# §7.1 Resolution path coverage
# ---------------------------------------------------------------------------

def test_all_exact_match_no_inner_calls(tmp_path):
    """Scenario 1: all items resolve at Step 1; no inner skill called."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    with patch("log_meal_items.match_recipes") as mock_sem, \
         patch("log_meal_items.estimate_macros") as mock_est:
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "Recovery Shake", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    mock_sem.assert_not_called()
    mock_est.assert_not_called()
    assert result["ok"] is True
    d = result["data"]
    assert len(d["items"]) == 1
    assert d["items"][0]["source"] == "recipe"
    assert d["items"][0]["recipe_match"] == "Recovery Shake"


def test_all_semantic_match_step3_not_called(tmp_path):
    """Scenario 2: Step 1 misses; semantic match resolves all; batch estimation not called."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    with patch("log_meal_items.match_recipes", return_value=_sem(["Recovery Shake"])) as mock_sem, \
         patch("log_meal_items.estimate_macros") as mock_est:
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "my shake", "portion": 0.5}],
            data_root=str(tmp_path),
        )
    mock_sem.assert_called_once()
    mock_est.assert_not_called()
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "recipe"
    assert result["data"]["items"][0]["recipe_match"] == "Recovery Shake"


def test_all_estimation_step1_and_step2_miss(tmp_path):
    """Scenario 3: Step 1 and Step 2 both miss; batch estimation resolves all."""
    _write_recipes(tmp_path, _USER, [])
    est_result = _bat([_est(90, 6, 5, 0)])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])) as mock_sem, \
         patch("log_meal_items.estimate_macros", return_value=est_result) as mock_est:
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 2.0}],
            data_root=str(tmp_path),
        )
    mock_sem.assert_called_once()
    mock_est.assert_called_once()
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "estimate"
    assert result["data"]["items"][0]["recipe_match"] is None
    assert result["data"]["items"][0]["scaled_macros"]["calories"] == round(90 * 2.0)


def test_mixed_resolution_paths(tmp_path):
    """Scenario 4: some Step 1, some Step 2, some Step 3; two inner calls made."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD, _TIKKA_RECORD])
    # Item 0 (shake): exact match at Step 1
    # Item 1 (tikka): semantic match
    # Item 2 (egg): estimation
    sem_result = _sem(["Chicken Tikka Lunch Bowl", None])
    est_result = _bat([_est(70, 6, 5, 0)])
    with patch("log_meal_items.match_recipes", return_value=sem_result), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "Recovery Shake", "portion": 1.0},
                {"description": "tikka lunch", "portion": 1.0},
                {"description": "egg", "portion": 1.0},
            ],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    items = result["data"]["items"]
    assert items[0]["source"] == "recipe"
    assert items[0]["recipe_match"] == "Recovery Shake"
    assert items[1]["source"] == "recipe"
    assert items[1]["recipe_match"] == "Chicken Tikka Lunch Bowl"
    assert items[2]["source"] == "estimate"


# ---------------------------------------------------------------------------
# §7.2 Input edge cases
# ---------------------------------------------------------------------------

def test_empty_input_list_returns_success(tmp_path):
    """Scenario 5: empty list is a no-op success; no inner skill calls."""
    _write_recipes(tmp_path, _USER, [])
    with patch("log_meal_items.match_recipes") as mock_sem, \
         patch("log_meal_items.estimate_macros") as mock_est:
        result = run_log_meal_items(user_id=_USER, items=[], data_root=str(tmp_path))
    mock_sem.assert_not_called()
    mock_est.assert_not_called()
    assert result["ok"] is True
    d = result["data"]
    assert d["items"] == []
    assert d["totals"] == {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}
    assert d["warnings"] == []


def test_single_item_produces_list_of_one(tmp_path):
    """Scenario 6: single item; cardinality discipline preserved; no inner-skill calls."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    with patch("log_meal_items.match_recipes") as mock_sem, \
         patch("log_meal_items.estimate_macros") as mock_est:
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "Recovery Shake", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    mock_sem.assert_not_called()
    mock_est.assert_not_called()
    assert result["ok"] is True
    assert isinstance(result["data"]["items"], list)
    assert len(result["data"]["items"]) == 1


def test_description_extra_whitespace_validates_and_strips(tmp_path):
    """Scenario 7: leading/trailing whitespace is stripped; stripped value flows through."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    # "  Recovery Shake  " strips to "Recovery Shake", which exactly matches the recipe.
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "  Recovery Shake  ", "portion": 1.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is True
    item = result["data"]["items"][0]
    assert item["source"] == "recipe"
    assert item["description"] == "Recovery Shake"


def test_whitespace_only_description_rejected(tmp_path):
    """Scenario 8: whitespace-only description rejects with validation_error."""
    _write_recipes(tmp_path, _USER, [])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "   ", "portion": 1.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is False
    assert result["err"]["code"] == "validation_error"


def test_portion_zero_rejected(tmp_path):
    """Scenario 9: portion=0 rejects with validation_error."""
    _write_recipes(tmp_path, _USER, [])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "egg", "portion": 0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is False
    assert result["err"]["code"] == "validation_error"


def test_portion_negative_rejected(tmp_path):
    """Scenario 9b: negative portion rejects with validation_error."""
    _write_recipes(tmp_path, _USER, [])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "egg", "portion": -1.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is False
    assert result["err"]["code"] == "validation_error"


def test_portion_small_positive_validates(tmp_path):
    """Scenario 10: portion=0.001 is valid."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "Recovery Shake", "portion": 0.001}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is True


def test_very_large_portion_validates(tmp_path):
    """Scenario 11: large portion is valid; no upper bound."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "Recovery Shake", "portion": 999.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# §7.3 Inner LLM failure modes
# ---------------------------------------------------------------------------

def test_semantic_match_retry_success_adds_warning(tmp_path):
    """Scenario 12: semantic match succeeds on retry; warning appended."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    sem_result = _sem(["Recovery Shake"], retry=True)
    with patch("log_meal_items.match_recipes", return_value=sem_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "shake", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    assert any("retry" in w.lower() for w in result["data"]["warnings"])


def test_semantic_match_hard_fail_returns_error(tmp_path):
    """Scenario 13: semantic match raises; error envelope with semantic_match_failed."""
    _write_recipes(tmp_path, _USER, [])
    with patch("log_meal_items.match_recipes", side_effect=RuntimeError("API failed")):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is False
    assert result["err"]["code"] == "semantic_match_failed"


def test_batch_estimation_retry_success_adds_warning(tmp_path):
    """Scenario 14: batch estimation succeeds on retry; warning appended."""
    _write_recipes(tmp_path, _USER, [])
    est_result = _bat([_est(70, 6, 5, 0)], retry=True)
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    assert any("retry" in w.lower() for w in result["data"]["warnings"])


def test_batch_estimation_hard_fail_returns_error(tmp_path):
    """Scenario 15: batch estimation raises; error envelope with batch_estimation_failed."""
    _write_recipes(tmp_path, _USER, [])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros", side_effect=RuntimeError("API failed")):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is False
    assert result["err"]["code"] == "batch_estimation_failed"


# ---------------------------------------------------------------------------
# §7.4 Step 1 specifics
# ---------------------------------------------------------------------------

def test_article_variation_matches(tmp_path):
    """Scenario 16: 'my recovery shake' matches recipe 'Recovery Shake'."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "my recovery shake", "portion": 1.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "recipe"
    assert result["data"]["items"][0]["recipe_match"] == "Recovery Shake"


def test_multi_recipe_step1_zero_match_falls_through(tmp_path):
    """Scenario 17: two shakes; 'shake' description matches neither exactly;
    falls through to Step 2 (null) then Step 3."""
    _write_recipes(tmp_path, _USER, [_MORNING_SHAKE_RECORD, _EVENING_SHAKE_RECORD])
    est_result = _bat([_est(200, 20, 5, 15)])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "shake", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "estimate"


def test_internal_whitespace_collapses(tmp_path):
    """Scenario 18: double spaces in recipe name normalize correctly."""
    double_space = {
        "recipe_id": 1, "user_id": _USER, "name": "Chicken  Tikka  Bowl",
        "ingredients": [], "macros": {"calories": 500, "protein_g": 40, "fat_g": 15, "carbs_g": 45},
        "created_at": "2026-04-30T00:00:00Z",
    }
    _write_recipes(tmp_path, _USER, [double_space])
    result = run_log_meal_items(
        user_id=_USER,
        items=[{"description": "chicken tikka bowl", "portion": 1.0}],
        data_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "recipe"


# ---------------------------------------------------------------------------
# §7.5 Recipes folder edge cases
# ---------------------------------------------------------------------------

def test_empty_recipes_folder_all_proceed_to_estimation(tmp_path):
    """Scenario 19: no recipes; all items proceed to Step 2 then Step 3."""
    _write_recipes(tmp_path, _USER, [])
    est_result = _bat([_est(70, 6, 5, 0)])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "estimate"


def test_recipes_folder_unreadable_returns_error(tmp_path):
    """Scenario 20: recipes read raises OSError; returns recipes_folder_unreadable."""
    from common import CorruptStateError
    with patch("log_meal_items.run_list_recipes", side_effect=OSError("permission denied")):
        result = run_log_meal_items(
            user_id=_USER,
            items=[{"description": "egg", "portion": 1.0}],
            data_root=str(tmp_path),
        )
    assert result["ok"] is False
    assert result["err"]["code"] == "recipes_folder_unreadable"


# ---------------------------------------------------------------------------
# §7.6 Output assembly
# ---------------------------------------------------------------------------

def test_items_returned_in_input_order(tmp_path):
    """Scenario 21: output items align positionally with input."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    est_result = _bat([_est(70, 6, 5, 0), _est(50, 3, 2, 8)])
    with patch("log_meal_items.match_recipes", return_value=_sem([None, None])), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "egg", "portion": 1.0},
                {"description": "apple", "portion": 1.0},
                {"description": "Recovery Shake", "portion": 1.0},
            ],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    items = result["data"]["items"]
    assert items[0]["description"] == "egg"
    assert items[1]["description"] == "apple"
    assert items[2]["description"] == "Recovery Shake"
    assert items[2]["source"] == "recipe"


def test_totals_correctness(tmp_path):
    """Scenario 22: totals match sum of scaled macros for known inputs."""
    _write_recipes(tmp_path, _USER, [_SHAKE_RECORD])
    est_result = _bat([_est(70, 6, 5, 0)])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "Recovery Shake", "portion": 0.5},
                {"description": "egg", "portion": 2.0},
            ],
            data_root=str(tmp_path),
        )
    assert result["ok"] is True
    totals = result["data"]["totals"]
    assert totals["calories"] == round(300 * 0.5) + round(70 * 2.0)
    assert totals["protein_g"] == round(25 * 0.5) + round(6 * 2.0)


def test_notes_and_warnings_populate_correctly(tmp_path):
    """Scenario 23: notes bubble from estimation; warnings from retry and ambiguity.

    Two recipes normalize to the same name ('shake' and 'my shake' both normalize
    to 'shake'), creating multi-match at Step 1. Step 2 returns null for that item
    (ambiguity warning fires). A second item is estimated with notes. Semantic match
    also signals retry_occurred (retry warning fires).
    """
    shake_a = {
        "recipe_id": 1, "user_id": _USER, "name": "Shake",
        "ingredients": [], "macros": {"calories": 200, "protein_g": 20, "fat_g": 5, "carbs_g": 10},
        "created_at": "2026-04-30T00:00:00Z",
    }
    shake_b = {
        "recipe_id": 2, "user_id": _USER, "name": "My Shake",
        "ingredients": [], "macros": {"calories": 180, "protein_g": 18, "fat_g": 4, "carbs_g": 8},
        "created_at": "2026-04-30T00:00:00Z",
    }
    _write_recipes(tmp_path, _USER, [shake_a, shake_b])

    # "shake" normalizes to "shake"; "Shake" normalizes to "shake"; "My Shake" normalizes to "shake"
    # Both recipes match → Step 1 multi-match → ambiguous flag → Step 2 [null, null]
    # "rice" has no recipe match either → [null, null] from Step 2
    sem_result = _sem([None, None], retry=True)
    est_result = _bat([
        _est(200, 20, 5, 10),  # shake (estimated)
        _est(200, 4, 0, 44, notes="Assumed one cup of cooked rice"),  # rice with notes
    ])
    with patch("log_meal_items.match_recipes", return_value=sem_result), \
         patch("log_meal_items.estimate_macros", return_value=est_result):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "shake", "portion": 1.0},
                {"description": "rice", "portion": 1.0},
            ],
            data_root=str(tmp_path),
        )

    assert result["ok"] is True
    items = result["data"]["items"]
    warnings = result["data"]["warnings"]

    # notes bubble into per-item field
    assert items[1]["notes"] == "Assumed one cup of cooked rice"
    assert items[0]["notes"] is None

    # ambiguity warning: "shake" matched both recipes at Step 1
    assert any("multiple" in w.lower() or "ambig" in w.lower() or "plausibly" in w.lower()
               for w in warnings)
    # retry warning from semantic match
    assert any("retry" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# B-3: inner-skill contract length validation
# ---------------------------------------------------------------------------

def test_semantic_match_wrong_length_returns_error(tmp_path):
    """B-3: semantic match returns shorter list; semantic_match_failed with length details."""
    _write_recipes(tmp_path, _USER, [])
    with patch("log_meal_items.match_recipes", return_value=_sem([None])), \
         patch("log_meal_items.estimate_macros"):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "egg", "portion": 1.0},
                {"description": "toast", "portion": 1.0},
            ],
            data_root=str(tmp_path),
        )
    assert result["ok"] is False
    assert result["err"]["code"] == "semantic_match_failed"
    assert result["err"]["details"]["expected_length"] == 2
    assert result["err"]["details"]["actual_length"] == 1


def test_batch_estimate_wrong_length_returns_error(tmp_path):
    """B-3: batch estimation returns shorter list; batch_estimation_failed with length details."""
    _write_recipes(tmp_path, _USER, [])
    with patch("log_meal_items.match_recipes", return_value=_sem([None, None])), \
         patch("log_meal_items.estimate_macros", return_value=_bat([_est(70, 6, 5, 0)])):
        result = run_log_meal_items(
            user_id=_USER,
            items=[
                {"description": "egg", "portion": 1.0},
                {"description": "toast", "portion": 1.0},
            ],
            data_root=str(tmp_path),
        )
    assert result["ok"] is False
    assert result["err"]["code"] == "batch_estimation_failed"
    assert result["err"]["details"]["expected_length"] == 2
    assert result["err"]["details"]["actual_length"] == 1
