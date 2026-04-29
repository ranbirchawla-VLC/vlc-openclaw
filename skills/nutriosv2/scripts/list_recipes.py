"""list_recipes; return all saved recipes for a user.

Usage: python3 list_recipes.py '<json_args>'

Args JSON schema:
  user_id: int  ; Telegram user ID

Returns {"recipes": [{"recipe_id": int, "name": str, "macros": {...}}], "count": int}.
Sorted alphabetically by name (case-insensitive). File-not-found returns empty list.
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


def run_list_recipes(user_id: int, data_root: str = DATA_ROOT) -> dict:
    path = os.path.join(data_root, str(user_id), "recipes.json")
    if not os.path.exists(path):
        return {"recipes": [], "count": 0}
    with open(path) as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise CorruptStateError(path, e)
    recipes = []
    for record in raw:
        try:
            recipe = Recipe(**record)
        except Exception as e:
            raise CorruptStateError(path, e)
        recipes.append({
            "recipe_id": recipe.recipe_id,
            "name": recipe.name,
            "macros": recipe.macros.model_dump(),
        })
    recipes.sort(key=lambda r: r["name"].lower())
    return {"recipes": recipes, "count": len(recipes)}


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
    print(
        json.dumps({"tool": "list_recipes", "phase": "input", "args": inp.model_dump()}),
        file=sys.stderr,
    )
    try:
        result = run_list_recipes(inp.user_id)
    except CorruptStateError as e:
        err(str(e))
        return
    ok(result)


if __name__ == "__main__":
    main()
