"""write_recipe; save a new recipe for a user.

Usage: python3 write_recipe.py '<json_args>'

Args JSON schema:
  user_id:     int              ; required
  name:        str              ; required; non-empty
  macros:      object           ; required; calories, protein_g, fat_g, carbs_g (all int)
  ingredients: [{description}] ; optional; defaults to []

Returns {"recipe_id": int, "name": str} on success.
Returns {"ok": false, "error": "name_collision", "existing_recipe_id": int, "message": str}
  when a recipe with the same name (case-insensitive) already exists for this user.
  Exit code 0 on collision so the plugin passes the structured response to the LLM.
"""

from __future__ import annotations
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, err, now_utc, ok
from models import Ingredient, Macros, Recipe

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    name: str
    macros: Macros
    ingredients: list[Ingredient] = []


def _recipes_path(user_id: int, data_root: str) -> str:
    return os.path.join(data_root, str(user_id), "recipes.json")


def _load_recipes(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise CorruptStateError(path, e)


def _next_recipe_id(records: list) -> int:
    if not records:
        return 1
    return max((r.get("recipe_id", 0) for r in records), default=0) + 1


def _write_recipes_atomic(path: str, recipes: list) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    bak = path + ".bak"
    if os.path.exists(path):
        shutil.copy2(path, bak)
    with open(tmp, "w") as f:
        json.dump(recipes, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run_write_recipe(
    user_id: int,
    name: str,
    macros: Macros,
    ingredients: list[Ingredient],
    data_root: str = DATA_ROOT,
) -> dict:
    path = _recipes_path(user_id, data_root)
    records = _load_recipes(path)

    name_lower = name.lower()
    for record in records:
        if record.get("name", "").lower() == name_lower:
            return {
                "ok": False,
                "error": "name_collision",
                "existing_recipe_id": record["recipe_id"],
                "message": f"Recipe '{name}' already exists",
            }

    recipe_id = _next_recipe_id(records)
    new_record = Recipe(
        recipe_id=recipe_id,
        user_id=user_id,
        name=name,
        macros=macros,
        ingredients=ingredients,
        created_at=now_utc(),
    ).model_dump()
    records.append(new_record)
    _write_recipes_atomic(path, records)
    return {"ok": True, "data": {"recipe_id": recipe_id, "name": name}}


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
    if not inp.name.strip():
        err("name is required and must be non-empty")
        return
    print(
        json.dumps({"tool": "write_recipe", "phase": "input", "args": inp.model_dump()}),
        file=sys.stderr,
    )
    try:
        result = run_write_recipe(inp.user_id, inp.name, inp.macros, inp.ingredients)
    except CorruptStateError as e:
        err(str(e))
        return
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
