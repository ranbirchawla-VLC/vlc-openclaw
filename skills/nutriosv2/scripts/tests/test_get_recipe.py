"""Tests for get_recipe.py."""

from __future__ import annotations
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from get_recipe import run_get_recipe
from common import CorruptStateError


def _write_recipes(tmp_path: Path, user_id: int, records: list[dict]) -> None:
    d = tmp_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recipes.json").write_text(json.dumps(records))


_SHAKE = {
    "recipe_id": 1,
    "user_id": 99,
    "name": "Ranbir's Full Protein Shake",
    "ingredients": [{"description": "50g protein powder"}, {"description": "6oz 1% milk"}],
    "macros": {"calories": 322, "protein_g": 56, "fat_g": 4, "carbs_g": 16},
    "created_at": "2026-04-27T01:16:05.679983+00:00",
}

_STRAWBERRY = {
    "recipe_id": 2,
    "user_id": 99,
    "name": "Strawberries with Yogurt",
    "ingredients": [{"description": "6 oz strawberries"}],
    "macros": {"calories": 201, "protein_g": 12, "fat_g": 1, "carbs_g": 40},
    "created_at": "2026-04-27T18:08:30.778798+00:00",
}


def test_no_file_returns_none(tmp_path):
    result = run_get_recipe(user_id=99, name="anything", recipe_id=None, data_root=str(tmp_path))
    assert result is None


def test_lookup_by_recipe_id(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    result = run_get_recipe(user_id=99, name=None, recipe_id=1, data_root=str(tmp_path))
    assert result is not None
    assert result["recipe_id"] == 1
    assert result["name"] == "Ranbir's Full Protein Shake"


def test_lookup_by_name_exact(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    result = run_get_recipe(user_id=99, name="Ranbir's Full Protein Shake", recipe_id=None, data_root=str(tmp_path))
    assert result is not None
    assert result["recipe_id"] == 1


def test_lookup_by_name_case_insensitive(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    result = run_get_recipe(user_id=99, name="ranbir's full protein shake", recipe_id=None, data_root=str(tmp_path))
    assert result is not None
    assert result["recipe_id"] == 1


def test_name_no_match_returns_none(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    result = run_get_recipe(user_id=99, name="pancake", recipe_id=None, data_root=str(tmp_path))
    assert result is None


def test_name_does_not_substring_match(tmp_path):
    # "shake" is a substring of the recipe name but must NOT match (exact only).
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_get_recipe(user_id=99, name="shake", recipe_id=None, data_root=str(tmp_path))
    assert result is None


def test_recipe_id_takes_precedence_when_both_provided(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    # recipe_id=2 and name="Ranbir's Full Protein Shake" — recipe_id wins, returns Strawberry
    result = run_get_recipe(user_id=99, name="Ranbir's Full Protein Shake", recipe_id=2, data_root=str(tmp_path))
    assert result is not None
    assert result["recipe_id"] == 2
    assert result["name"] == "Strawberries with Yogurt"


def test_recipe_id_no_match_returns_none(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_get_recipe(user_id=99, name=None, recipe_id=99, data_root=str(tmp_path))
    assert result is None


def test_filters_by_user_id(tmp_path):
    # Each user has their own recipes.json at {data_root}/{user_id}/recipes.json.
    other = {**_SHAKE, "recipe_id": 3, "user_id": 55, "name": "Other User Shake"}
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    _write_recipes(tmp_path, 55, [other])
    # user 55's recipe is accessible at their own path
    result = run_get_recipe(user_id=55, name=None, recipe_id=3, data_root=str(tmp_path))
    assert result is not None
    assert result["recipe_id"] == 3
    # user 99 cannot reach recipe_id=3 (it lives in user 55's file, not user 99's)
    result2 = run_get_recipe(user_id=99, name=None, recipe_id=3, data_root=str(tmp_path))
    assert result2 is None


def test_output_shape_per_contract(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_get_recipe(user_id=99, name=None, recipe_id=1, data_root=str(tmp_path))
    assert result is not None
    assert set(result.keys()) == {"recipe_id", "name", "macros", "ingredients", "created_at"}
    # user_id must NOT appear in output
    assert "user_id" not in result
    assert set(result["macros"].keys()) == {"calories", "protein_g", "fat_g", "carbs_g"}
    assert isinstance(result["ingredients"], list)
    assert all("description" in i for i in result["ingredients"])


def test_macros_and_ingredients_verbatim(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_get_recipe(user_id=99, name=None, recipe_id=1, data_root=str(tmp_path))
    assert result["macros"]["calories"] == 322
    assert result["macros"]["protein_g"] == 56
    assert result["ingredients"][0]["description"] == "50g protein powder"
    assert result["created_at"] == "2026-04-27T01:16:05.679983+00:00"


def test_corrupt_json_raises(tmp_path):
    d = tmp_path / "99"
    d.mkdir()
    (d / "recipes.json").write_text("{not valid json")
    with pytest.raises(CorruptStateError):
        run_get_recipe(user_id=99, name="anything", recipe_id=None, data_root=str(tmp_path))
