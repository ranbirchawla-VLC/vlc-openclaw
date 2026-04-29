"""Tests for list_recipes.py."""

from __future__ import annotations
import json
import os
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from list_recipes import run_list_recipes
from common import CorruptStateError


def _write_recipes(tmp_path: Path, user_id: int, records: list[dict]) -> None:
    d = tmp_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recipes.json").write_text(json.dumps(records))


_SHAKE = {
    "recipe_id": 1,
    "user_id": 99,
    "name": "Ranbir's Full Protein Shake",
    "ingredients": [{"description": "50g protein powder"}],
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


def test_no_file_returns_empty(tmp_path):
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    assert result == {"recipes": [], "count": 0}


def test_empty_file_returns_empty(tmp_path):
    _write_recipes(tmp_path, 99, [])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    assert result == {"recipes": [], "count": 0}


def test_returns_both_recipes(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    assert result["count"] == 2
    assert len(result["recipes"]) == 2


def test_sorted_alphabetically(tmp_path):
    # Write in reverse alphabetical order; expect alphabetical in output.
    _write_recipes(tmp_path, 99, [_STRAWBERRY, _SHAKE])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    names = [r["name"] for r in result["recipes"]]
    assert names == sorted(names, key=str.lower)
    assert names[0] == "Ranbir's Full Protein Shake"
    assert names[1] == "Strawberries with Yogurt"


def test_output_shape_per_contract(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    recipe = result["recipes"][0]
    assert set(recipe.keys()) == {"recipe_id", "name", "macros"}
    assert set(recipe["macros"].keys()) == {"calories", "protein_g", "fat_g", "carbs_g"}
    # ingredients and created_at must NOT appear in list output
    assert "ingredients" not in recipe
    assert "created_at" not in recipe


def test_macros_verbatim(tmp_path):
    _write_recipes(tmp_path, 99, [_SHAKE])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    macros = result["recipes"][0]["macros"]
    assert macros["calories"] == 322
    assert macros["protein_g"] == 56
    assert macros["fat_g"] == 4
    assert macros["carbs_g"] == 16


def test_filters_by_user_id(tmp_path):
    # Isolation is by path: each user has their own recipes.json at data_root/<user_id>/.
    _write_recipes(tmp_path, 99, [_SHAKE, _STRAWBERRY])
    _write_recipes(tmp_path, 55, [{**_SHAKE, "recipe_id": 3, "user_id": 55, "name": "Other User Shake"}])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    assert result["count"] == 2
    names = {r["name"] for r in result["recipes"]}
    assert "Other User Shake" not in names


def test_corrupt_json_raises(tmp_path):
    d = tmp_path / "99"
    d.mkdir()
    (d / "recipes.json").write_text("{not valid json")
    with pytest.raises(CorruptStateError):
        run_list_recipes(user_id=99, data_root=str(tmp_path))


def test_case_insensitive_sort(tmp_path):
    # "apple" should sort before "Banana" (case-insensitive)
    r1 = {**_SHAKE, "recipe_id": 1, "name": "Banana Shake"}
    r2 = {**_STRAWBERRY, "recipe_id": 2, "name": "apple oats"}
    _write_recipes(tmp_path, 99, [r1, r2])
    result = run_list_recipes(user_id=99, data_root=str(tmp_path))
    names = [r["name"] for r in result["recipes"]]
    assert names == ["apple oats", "Banana Shake"]
