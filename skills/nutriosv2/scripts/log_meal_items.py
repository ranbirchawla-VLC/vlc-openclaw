"""log_meal_items; orchestrates meal-item resolution and macro assembly.

Usage: python3 log_meal_items.py '<json_args>'

Args JSON schema (note: user_id is required; spec §2.1 omitted it but every
disk-reading tool requires it; added per codebase convention):
  user_id: int
  items: list[{description: str, portion: float}]

Returns per spec §3.1. Error envelope per spec §3.5: {"ok": false, "err":
{code, message, details}}. This differs from common.err's wire format ("error":
string); the function returns the rich dict; main() emits it directly.

Internal flow (arch doc §4.2):
  Step 1: exact match against recipes.json (Python only)
  Step 2: semantic match inner skill (one LLM call for all unmatched)
  Step 3: batch estimation inner skill (one LLM call for remaining)
  Step 4: portion math via calculate_macros.run_calculate_macros; sum totals
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import CorruptStateError, DATA_ROOT, err, ok
from calculate_macros import run_calculate_macros
from inner_skills.semantic_match import SemanticMatchResult, match_recipes
from inner_skills.batch_estimate import BatchEstimateResult, BaseMacroEstimate, estimate_macros
from list_recipes import run_list_recipes

from pydantic import BaseModel, field_validator


_LEADING_ARTICLES: frozenset[str] = frozenset({"a", "an", "the", "my"})


class _Item(BaseModel):
    description: str
    portion: float

    @field_validator("description")
    @classmethod
    def non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("description must be non-empty")
        return stripped

    @field_validator("portion")
    @classmethod
    def strictly_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("portion must be > 0")
        return v


def _normalize(text: str) -> str:
    """Lowercase, strip leading articles, collapse whitespace."""
    text = text.lower().strip()
    words = text.split()
    if words and words[0] in _LEADING_ARTICLES:
        words = words[1:]
    return " ".join(words)


def _zero_totals() -> dict:
    return {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}


def _error(code: str, message: str, details: dict | None = None) -> dict:
    return {"ok": False, "err": {"code": code, "message": message, "details": details}}


def run_log_meal_items(
    user_id: int,
    items: list[dict],
    data_root: str = DATA_ROOT,
) -> dict:
    # --- Input validation ---
    validated: list[_Item] = []
    for i, raw_item in enumerate(items):
        try:
            validated.append(_Item(**raw_item))
        except Exception as e:
            return _error("validation_error", f"items[{i}]: {e}")

    if not validated:
        return {"ok": True, "data": {"items": [], "totals": _zero_totals(), "warnings": []}}

    # --- Step 1: read recipes and exact-match ---
    try:
        recipe_data = run_list_recipes(user_id=user_id, data_root=data_root)
    except (CorruptStateError, OSError) as e:
        return _error("recipes_folder_unreadable", str(e))

    recipes: list[dict] = recipe_data["recipes"]
    recipe_names: list[str] = [r["name"] for r in recipes]
    recipe_by_name: dict[str, dict] = {r["name"]: r for r in recipes}

    recipe_by_norm: dict[str, list[dict]] = {}
    for r in recipes:
        norm = _normalize(r["name"])
        recipe_by_norm.setdefault(norm, []).append(r)

    resolved: list[dict | None] = [None] * len(validated)
    unmatched_indices: list[int] = []
    ambiguous_at_step1: set[int] = set()

    for i, item in enumerate(validated):
        norm_desc = _normalize(item.description)
        matches = recipe_by_norm.get(norm_desc, [])
        if len(matches) == 1:
            r = matches[0]
            resolved[i] = {
                "description": item.description,
                "source": "recipe",
                "recipe_match": r["name"],
                "base_macros": r["macros"],
                "portion": item.portion,
                "scaled_macros": run_calculate_macros(r["macros"], item.portion),
                "notes": None,
            }
        else:
            unmatched_indices.append(i)
            if len(matches) > 1:
                ambiguous_at_step1.add(i)

    warnings: list[str] = []

    # --- Step 2: semantic match for unmatched items ---
    if unmatched_indices:
        unmatched_descs = [validated[i].description for i in unmatched_indices]
        try:
            sem_result: SemanticMatchResult = match_recipes(unmatched_descs, recipe_names)
        except Exception as e:
            return _error("semantic_match_failed", str(e))

        if len(sem_result.matches) != len(unmatched_descs):
            return _error(
                "semantic_match_failed",
                "inner skill returned wrong number of matches",
                {"expected_length": len(unmatched_descs), "actual_length": len(sem_result.matches)},
            )

        if sem_result.retry_occurred:
            warnings.append("Semantic match inner skill succeeded on retry.")

        still_unmatched: list[int] = []
        for j, idx in enumerate(unmatched_indices):
            match_name = sem_result.matches[j]
            if match_name is not None:
                r = recipe_by_name[match_name]
                resolved[idx] = {
                    "description": validated[idx].description,
                    "source": "recipe",
                    "recipe_match": r["name"],
                    "base_macros": r["macros"],
                    "portion": validated[idx].portion,
                    "scaled_macros": run_calculate_macros(r["macros"], validated[idx].portion),
                    "notes": None,
                }
            else:
                if idx in ambiguous_at_step1:
                    desc = validated[idx].description
                    warnings.append(
                        f"Multiple recipes plausibly matched '{desc}'; "
                        "routed to estimation. Consider renaming for distinct match."
                    )
                still_unmatched.append(idx)
        unmatched_indices = still_unmatched

    # --- Step 3: batch estimation for still-unmatched items ---
    if unmatched_indices:
        est_descs = [validated[i].description for i in unmatched_indices]
        try:
            est_result: BatchEstimateResult = estimate_macros(est_descs)
        except Exception as e:
            return _error("batch_estimation_failed", str(e))

        if len(est_result.items) != len(est_descs):
            return _error(
                "batch_estimation_failed",
                "inner skill returned wrong number of items",
                {"expected_length": len(est_descs), "actual_length": len(est_result.items)},
            )

        if est_result.retry_occurred:
            warnings.append("Batch estimation inner skill succeeded on retry.")

        for j, idx in enumerate(unmatched_indices):
            est = est_result.items[j]
            base = {
                "calories": est.calories,
                "protein_g": est.protein_g,
                "fat_g": est.fat_g,
                "carbs_g": est.carbs_g,
            }
            resolved[idx] = {
                "description": validated[idx].description,
                "source": "estimate",
                "recipe_match": None,
                "base_macros": base,
                "portion": validated[idx].portion,
                "scaled_macros": run_calculate_macros(base, validated[idx].portion),
                "notes": est.notes,
            }

    # --- Step 4: sum totals ---
    totals = _zero_totals()
    for i, item_result in enumerate(resolved):
        assert item_result is not None, f"resolved[{i}] is None after all resolution steps"
        for field in totals:
            totals[field] += item_result["scaled_macros"][field]

    return {
        "ok": True,
        "data": {"items": resolved, "totals": totals, "warnings": warnings},
    }


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
        result = run_log_meal_items(
            user_id=raw["user_id"],
            items=raw.get("items", []),
        )
    except KeyError as e:
        err(f"missing required field: {e}")
        return
    if result["ok"]:
        ok(result["data"])
    else:
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
