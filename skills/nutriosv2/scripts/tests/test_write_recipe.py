"""Tests for write_recipe.py."""

from __future__ import annotations
import json
import os
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from write_recipe import run_write_recipe
from common import CorruptStateError
from models import Macros, Ingredient


_MACROS = Macros(calories=300, protein_g=25, fat_g=8, carbs_g=35)

_SHAKE_RAW = {
    "recipe_id": 1,
    "user_id": 99,
    "name": "Ranbir's Full Protein Shake",
    "ingredients": [{"description": "50g protein powder"}],
    "macros": {"calories": 322, "protein_g": 56, "fat_g": 4, "carbs_g": 16},
    "created_at": "2026-04-27T01:16:05.000Z",
}


def _write_existing(tmp_path: Path, user_id: int, records: list[dict]) -> None:
    d = tmp_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "recipes.json").write_text(json.dumps(records))


def _read_recipes(tmp_path: Path, user_id: int) -> list:
    path = tmp_path / str(user_id) / "recipes.json"
    return json.loads(path.read_text())


def test_creates_file_when_absent(tmp_path):
    result = run_write_recipe(
        user_id=99, name="New Recipe", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    assert result["ok"] is True
    assert result["data"]["recipe_id"] == 1
    assert result["data"]["name"] == "New Recipe"
    assert (tmp_path / "99" / "recipes.json").exists()


def test_auto_increments_recipe_id(tmp_path):
    _write_existing(tmp_path, 99, [_SHAKE_RAW])
    result = run_write_recipe(
        user_id=99, name="New Recipe", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    assert result["ok"] is True
    assert result["data"]["recipe_id"] == 2


def test_output_shape(tmp_path):
    result = run_write_recipe(
        user_id=99, name="Test", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    assert result["ok"] is True
    assert set(result["data"].keys()) == {"recipe_id", "name"}
    assert result["data"]["name"] == "Test"


def test_persists_to_disk(tmp_path):
    run_write_recipe(
        user_id=99, name="My Recipe", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    records = _read_recipes(tmp_path, 99)
    assert len(records) == 1
    assert records[0]["name"] == "My Recipe"
    assert records[0]["macros"]["calories"] == 300


def test_persists_ingredients(tmp_path):
    ingredients = [Ingredient(description="oats"), Ingredient(description="milk")]
    run_write_recipe(
        user_id=99, name="Oatmeal", macros=_MACROS, ingredients=ingredients, data_root=str(tmp_path)
    )
    records = _read_recipes(tmp_path, 99)
    assert records[0]["ingredients"] == [{"description": "oats"}, {"description": "milk"}]


def test_empty_ingredients_default(tmp_path):
    run_write_recipe(
        user_id=99, name="Simple", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    records = _read_recipes(tmp_path, 99)
    assert records[0]["ingredients"] == []


def test_collision_same_name_rejected(tmp_path):
    _write_existing(tmp_path, 99, [_SHAKE_RAW])
    result = run_write_recipe(
        user_id=99, name="Ranbir's Full Protein Shake", macros=_MACROS, ingredients=[],
        data_root=str(tmp_path)
    )
    assert result["ok"] is False
    assert result["error"] == "name_collision"
    assert result["existing_recipe_id"] == 1
    assert "Ranbir's Full Protein Shake" in result["message"]


def test_collision_case_insensitive(tmp_path):
    _write_existing(tmp_path, 99, [_SHAKE_RAW])
    result = run_write_recipe(
        user_id=99, name="ranbir's full protein shake", macros=_MACROS, ingredients=[],
        data_root=str(tmp_path)
    )
    assert result["ok"] is False
    assert result["error"] == "name_collision"
    assert result["existing_recipe_id"] == 1


def test_collision_does_not_write(tmp_path):
    _write_existing(tmp_path, 99, [_SHAKE_RAW])
    before = (tmp_path / "99" / "recipes.json").stat().st_size
    run_write_recipe(
        user_id=99, name="Ranbir's Full Protein Shake", macros=_MACROS, ingredients=[],
        data_root=str(tmp_path)
    )
    after = (tmp_path / "99" / "recipes.json").stat().st_size
    assert before == after


def test_multiple_writes_increment_correctly(tmp_path):
    run_write_recipe(user_id=99, name="A", macros=_MACROS, ingredients=[], data_root=str(tmp_path))
    run_write_recipe(user_id=99, name="B", macros=_MACROS, ingredients=[], data_root=str(tmp_path))
    run_write_recipe(user_id=99, name="C", macros=_MACROS, ingredients=[], data_root=str(tmp_path))
    records = _read_recipes(tmp_path, 99)
    ids = [r["recipe_id"] for r in records]
    assert ids == [1, 2, 3]


def test_no_tmp_leftover_after_success(tmp_path):
    run_write_recipe(
        user_id=99, name="Clean", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
    )
    assert not (tmp_path / "99" / "recipes.json.tmp").exists()


def test_corrupt_file_raises(tmp_path):
    d = tmp_path / "99"
    d.mkdir()
    (d / "recipes.json").write_text("{not json")
    with pytest.raises(CorruptStateError):
        run_write_recipe(
            user_id=99, name="New", macros=_MACROS, ingredients=[], data_root=str(tmp_path)
        )


def test_does_not_cross_user_ids(tmp_path):
    _write_existing(tmp_path, 99, [_SHAKE_RAW])
    # user 55 reads a separate file path; no collision with user 99's recipes
    result = run_write_recipe(
        user_id=55, name="Ranbir's Full Protein Shake", macros=_MACROS, ingredients=[],
        data_root=str(tmp_path)
    )
    assert result["ok"] is True
    assert result["data"]["recipe_id"] == 1
