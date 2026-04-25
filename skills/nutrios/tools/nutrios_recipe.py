"""nutrios_recipe.py — recipe lifecycle entrypoint (8/10).

Actions:
    save    — append a new Recipe, reject duplicate name (case-insensitive)
    update  — replace macros (and optionally ingredients) for an existing recipe
    list    — render_recipe_list, optional name-substring `query` filter
    get     — render_recipe_view for a single recipe by id or name
    delete  — soft-delete (removed=True) via full recipes.json rewrite

recipes.json is bulk-written via store.write_recipes (wrapped format
{"version": 1, "recipes": [...]}). Tripwire 2 doesn't apply (JSON, not
JSONL); the soft-delete pattern mirrors Event removal (D3).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nutrios_models import Recipe, RecipeMacros, ToolResult
import nutrios_render as render
import nutrios_store as store


class RecipeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    action: Literal["save", "update", "list", "get", "delete"]
    now: datetime
    tz: str
    # save / update
    name: str | None = None
    id: int | None = None
    macros_per_serving: RecipeMacros | None = None
    servings: int = 1
    ingredients: list[str] | None = None
    # list
    query: str | None = None


def _find_active_by_name(recipes: list[Recipe], name: str) -> Recipe | None:
    target = name.lower()
    for r in recipes:
        if not r.removed and r.name.lower() == target:
            return r
    return None


def _find_by_id_or_name(
    recipes: list[Recipe],
    rid: int | None,
    name: str | None,
    *,
    include_removed: bool = False,
) -> Recipe | None:
    """Prefer id; fall back to name. Active-only by default.

    include_removed=True is the restoration / idempotent-delete escape hatch:
    only _delete needs to see removed entries (so re-removing an already-
    removed recipe returns the same confirm). _get and _update must NOT
    see them — viewing or mutating a soft-deleted recipe through those
    surfaces would let the user resurrect a deleted recipe by id without
    a save action.
    """
    if rid is not None:
        for r in recipes:
            if r.id == rid and (include_removed or not r.removed):
                return r
    if name is not None:
        return _find_active_by_name(recipes, name)
    return None


def _save(inp: RecipeInput) -> ToolResult:
    if inp.name is None or inp.macros_per_serving is None:
        raise ValueError("action=save requires name and macros_per_serving")
    recipes = store.read_recipes(inp.user_id)
    if _find_active_by_name(recipes, inp.name) is not None:
        return ToolResult(display_text=render.render_recipe_duplicate_name_error(inp.name))

    new_id = store.next_id(inp.user_id, "last_recipe_id")
    recipe = Recipe(
        id=new_id,
        name=inp.name,
        servings=inp.servings,
        macros_per_serving=inp.macros_per_serving,
        ingredients=inp.ingredients or [],
    )
    recipes.append(recipe)
    store.write_recipes(inp.user_id, recipes)
    return ToolResult(
        display_text=render.render_recipe_save_confirm(recipe),
        state_delta={"last_recipe_id": new_id},
    )


def _update(inp: RecipeInput) -> ToolResult:
    if inp.macros_per_serving is None:
        raise ValueError("action=update requires macros_per_serving")
    if inp.id is None and inp.name is None:
        raise ValueError("action=update requires either id or name")

    recipes = store.read_recipes(inp.user_id)
    target = _find_by_id_or_name(recipes, inp.id, inp.name)
    if target is None:
        return ToolResult(
            display_text=render.render_supersedes_not_found(
                target_id=inp.id if inp.id is not None else 0,
                kind="recipe",
            )
        )

    update_fields = {
        "macros_per_serving": inp.macros_per_serving,
        "servings": inp.servings if inp.servings is not None else target.servings,
    }
    if inp.ingredients is not None:
        update_fields["ingredients"] = inp.ingredients
    new_recipe = target.model_copy(update=update_fields)

    idx = recipes.index(target)
    recipes[idx] = new_recipe
    store.write_recipes(inp.user_id, recipes)
    return ToolResult(display_text=render.render_recipe_update_confirm(new_recipe))


def _list(inp: RecipeInput) -> ToolResult:
    recipes = store.read_recipes(inp.user_id)
    if inp.query:
        q = inp.query.lower()
        recipes = [r for r in recipes if q in r.name.lower()]
    return ToolResult(display_text=render.render_recipe_list(recipes))


def _get(inp: RecipeInput) -> ToolResult:
    if inp.id is None and inp.name is None:
        raise ValueError("action=get requires either id or name")
    recipes = store.read_recipes(inp.user_id)
    target = _find_by_id_or_name(recipes, inp.id, inp.name)
    if target is None:
        return ToolResult(
            display_text=render.render_supersedes_not_found(
                target_id=inp.id if inp.id is not None else 0,
                kind="recipe",
            )
        )
    return ToolResult(display_text=render.render_recipe_view(target))


def _delete(inp: RecipeInput) -> ToolResult:
    if inp.id is None and inp.name is None:
        raise ValueError("action=delete requires either id or name")
    recipes = store.read_recipes(inp.user_id)
    # _delete is the one caller that legitimately needs to see removed recipes
    # (idempotent re-delete returns the same confirm)
    target = _find_by_id_or_name(recipes, inp.id, inp.name, include_removed=True)
    if target is None:
        return ToolResult(
            display_text=render.render_supersedes_not_found(
                target_id=inp.id if inp.id is not None else 0,
                kind="recipe",
            )
        )
    if target.removed:
        return ToolResult(display_text=render.render_recipe_delete_confirm(target))

    flipped = target.model_copy(update={"removed": True})
    idx = recipes.index(target)
    recipes[idx] = flipped
    store.write_recipes(inp.user_id, recipes)
    return ToolResult(display_text=render.render_recipe_delete_confirm(flipped))


def main(argv_json: str) -> ToolResult:
    inp = RecipeInput.model_validate_json(argv_json)
    match inp.action:
        case "save":
            return _save(inp)
        case "update":
            return _update(inp)
        case "list":
            return _list(inp)
        case "get":
            return _get(inp)
        case "delete":
            return _delete(inp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_recipe '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
