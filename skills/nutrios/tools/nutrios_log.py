"""nutrios_log.py — food log entrypoint (3/10).

Locked contract from Ranbir's brief:
1. Parse {user_id, name, qty, unit, kcal?, protein_g?, carbs_g?, fat_g?, now, tz}.
2. qty missing → ToolResult(needs_followup=True, render_quantity_clarify).
3. Resolve name through aliases.json (case-insensitive).
4. Recipe-first lookup. If hit:
   expand via engine.expand_recipe; build FoodLogEntry source="recipe";
   append; return confirm. state_delta does NOT include recipe_save_eligible.
5. No recipe hit:
   require kcal+protein_g+carbs_g+fat_g on input. Missing → followup
   render_macros_required. Otherwise build source="manual"; append;
   state_delta carries recipe_save_eligible=True for the orchestrator.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nutrios_models import FoodLogEntry, Recipe, ToolResult
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store
import nutrios_time


class LogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    name: str
    qty: float | None = None
    unit: str | None = None
    kcal: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    now: datetime
    tz: str


def _resolve_alias(name: str, aliases: dict[str, str]) -> str:
    """Case-insensitive alias lookup. Returns the resolved name (or original)."""
    target = name.lower()
    for alias, resolved in aliases.items():
        if alias.lower() == target:
            return resolved
    return name


def _find_recipe(name: str, recipes: list[Recipe]) -> Recipe | None:
    """Case-insensitive recipe-name lookup. Skips removed=True recipes."""
    target = name.lower()
    for r in recipes:
        if r.removed:
            continue
        if r.name.lower() == target:
            return r
    return None


def _utc_iso(now: datetime) -> str:
    """Canonical UTC ISO8601 with 'Z' suffix (matches existing JSONL convention)."""
    return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv_json: str) -> ToolResult:
    inp = LogInput.model_validate_json(argv_json)
    uid = inp.user_id

    # 1. Quantity required
    if inp.qty is None:
        return ToolResult(
            display_text=render.render_quantity_clarify(inp.name),
            needs_followup=True,
        )

    # 2. Alias resolution
    aliases = store.read_aliases(uid)
    resolved_name = _resolve_alias(inp.name, aliases)

    # 3. Recipe-first lookup
    recipes = store.read_recipes(uid)
    recipe = _find_recipe(resolved_name, recipes)

    target_date = inp.now.astimezone(ZoneInfo(inp.tz)).date()
    log_filename = f"log/{target_date}.jsonl"
    meal_slot = nutrios_time.meal_slot(inp.now, inp.tz)
    ts_iso = _utc_iso(inp.now)

    if recipe is not None:
        # 4. Recipe path
        macros = engine.expand_recipe(recipe, inp.qty)
        entry_id = store.next_id(uid, "last_entry_id")
        entry = FoodLogEntry(
            kind="food",
            id=entry_id,
            ts_iso=ts_iso,
            meal_slot=meal_slot,
            source="recipe",
            name=recipe.name,
            qty=inp.qty,
            unit=inp.unit or "serving",
            kcal=macros["kcal"],
            protein_g=macros["protein_g"],
            carbs_g=macros["carbs_g"],
            fat_g=macros["fat_g"],
            recipe_id=str(recipe.id),
        )
        store.append_jsonl(uid, log_filename, entry)
        return ToolResult(
            display_text=render.render_log_confirm(entry),
            state_delta={"last_entry_id": entry_id},
        )

    # 5. Manual path — require macros
    if (
        inp.kcal is None
        or inp.protein_g is None
        or inp.carbs_g is None
        or inp.fat_g is None
    ):
        return ToolResult(
            display_text=render.render_macros_required(resolved_name),
            needs_followup=True,
        )

    entry_id = store.next_id(uid, "last_entry_id")
    entry = FoodLogEntry(
        kind="food",
        id=entry_id,
        ts_iso=ts_iso,
        meal_slot=meal_slot,
        source="manual",
        name=resolved_name,
        qty=inp.qty,
        unit=inp.unit or "g",
        kcal=inp.kcal,
        protein_g=inp.protein_g,
        carbs_g=inp.carbs_g,
        fat_g=inp.fat_g,
    )
    store.append_jsonl(uid, log_filename, entry)
    return ToolResult(
        display_text=render.render_log_confirm(entry),
        state_delta={"recipe_save_eligible": True, "last_entry_id": entry_id},
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_log '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
