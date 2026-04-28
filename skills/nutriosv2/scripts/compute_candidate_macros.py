"""compute_candidate_macros; pure macro math from intent constraints.

Usage: python3 compute_candidate_macros.py '<json_args>'

Args JSON schema:
  target_deficit_kcal: int | null  ; deficit value; unit determined by deficit_unit
  deficit_unit: "weekly_kcal" | "daily_kcal"  ; default "weekly_kcal"
  protein_floor_g: int | null      ; minimum daily protein in grams
  fat_ceiling_g: int | null        ; maximum daily fat in grams
  estimated_tdee_kcal: int | null  ; estimated total daily energy expenditure

Returns {weekly_deficit_kcal, daily_deficit_kcal, calories, protein_g, fat_g, carbs_g}.
Any macro field may be null if the corresponding input is missing.
deficit fields are null when target_deficit_kcal is not provided.
"""


from __future__ import annotations
import json
import os
import sys
from typing import Literal

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    target_deficit_kcal: int | None = None
    deficit_unit: Literal["weekly_kcal", "daily_kcal"] = "weekly_kcal"
    protein_floor_g: int | None = None
    fat_ceiling_g: int | None = None
    estimated_tdee_kcal: int | None = None


def compute(inp: _Input) -> dict:
    # Normalize to weekly deficit regardless of unit supplied
    weekly_deficit: int | None = None
    daily_deficit: int | None = None
    if inp.target_deficit_kcal is not None:
        if inp.deficit_unit == "daily_kcal":
            weekly_deficit = inp.target_deficit_kcal * 7
        else:
            weekly_deficit = inp.target_deficit_kcal
        daily_deficit = round(weekly_deficit / 7)

    calories: int | None = None
    if inp.estimated_tdee_kcal is not None and weekly_deficit is not None:
        calories = round(inp.estimated_tdee_kcal - weekly_deficit / 7)

    protein_g: int | None = inp.protein_floor_g
    fat_g: int | None = inp.fat_ceiling_g

    carbs_g: int | None = None
    if calories is not None and protein_g is not None and fat_g is not None:
        carbs_kcal = calories - (protein_g * 4) - (fat_g * 9)
        carbs_g = carbs_kcal // 4 if carbs_kcal >= 0 else None

    return {
        "weekly_deficit_kcal": weekly_deficit,
        "daily_deficit_kcal": daily_deficit,
        "calories": calories,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
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
        inp = _Input(**raw)
    except Exception as e:
        err(f"invalid input: {e}")
        return

    print(json.dumps({"tool": "compute_candidate_macros", "phase": "input", "args": inp.model_dump()}), file=sys.stderr)
    result = compute(inp)
    print(json.dumps({"tool": "compute_candidate_macros", "phase": "output", "result": result}), file=sys.stderr)
    ok(result)


if __name__ == "__main__":
    main()
