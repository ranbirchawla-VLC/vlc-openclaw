"""get_recipe; look up a saved recipe by name (case-insensitive exact) or recipe_id.

Usage: python3 get_recipe.py '<json_args>'

Args JSON schema:
  user_id:   int         ; required
  name:      str | null  ; case-insensitive exact match; omit when using recipe_id
  recipe_id: int | null  ; exact match; takes precedence over name when both provided

At least one of name or recipe_id required.

Returns the full recipe object on match, or null on miss (not an error).
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, err, ok
from models import Recipe

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    name: str | None = None
    recipe_id: int | None = None


def _to_output(recipe: Recipe) -> dict:
    return {
        "recipe_id": recipe.recipe_id,
        "name": recipe.name,
        "macros": recipe.macros.model_dump(),
        "ingredients": [i.model_dump() for i in recipe.ingredients],
        "created_at": recipe.created_at,
    }


def run_get_recipe(
    user_id: int,
    name: str | None,
    recipe_id: int | None,
    data_root: str = DATA_ROOT,
) -> dict | None:
    path = os.path.join(data_root, str(user_id), "recipes.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise CorruptStateError(path, e)
    for record in raw:
        try:
            recipe = Recipe(**record)
        except Exception as e:
            raise CorruptStateError(path, e)
        if recipe_id is not None:
            if recipe.recipe_id == recipe_id:
                return _to_output(recipe)
        else:
            if recipe.name.lower() == name.lower():
                return _to_output(recipe)
    return None


def main() -> None:
    if len(sys.argv) < 2:
        err("missing args: expected JSON string as sys.argv[1]")
        return
    try:
        raw = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        err(f"invalid JSON args: {e}")
        return
    try:
        inp = _Input(**raw)
    except Exception as e:
        err(f"invalid input: {e}")
        return
    if inp.name is None and inp.recipe_id is None:
        err("at least one of name or recipe_id is required")
        return
    print(
        json.dumps({"tool": "get_recipe", "phase": "input", "args": inp.model_dump()}),
        file=sys.stderr,
    )
    try:
        result = run_get_recipe(inp.user_id, inp.name, inp.recipe_id)
    except CorruptStateError as e:
        err(str(e))
        return
    ok(result)


if __name__ == "__main__":
    main()
