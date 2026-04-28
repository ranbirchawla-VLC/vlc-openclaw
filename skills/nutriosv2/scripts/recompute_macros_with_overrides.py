"""recompute_macros_with_overrides; redistribute weekly kcal budget with per-day overrides.

Usage: python3 recompute_macros_with_overrides.py '<json_args>'

Args JSON schema:
  estimated_tdee_kcal: int    ; user's estimated total daily energy expenditure
  target_deficit_kcal: int    ; WEEKLY deficit in kcal (same unit as compute_candidate_macros)
  dose_weekday: int           ; 0=Mon..6=Sun (context for LLM row-to-weekday mapping)
  protein_floor_g: int        ; minimum daily protein for all non-overridden rows
  fat_ceiling_g: int          ; maximum daily fat for all non-overridden rows
  overrides: object           ; map of offset string key "0".."6" to row overrides.
    Each override must include "calories" (int); "protein_g" and "fat_g" are optional
    and default to protein_floor_g / fat_ceiling_g when omitted.

Returns {"weekly_kcal_target": int, "rows": [7 MacroRow-shaped dicts]}.

Rounding: remaining kcal after overrides distributed by floor division.
  Example: 11,050 remaining for 6 days = 11,050 // 6 = 1,841 (4 kcal/week not distributed).

Raises ValueError (surfaced via err()) when:
  - total override calories exceed weekly_intake_kcal_target
  - remaining per-day kcal cannot cover protein_floor_g * 4 + fat_ceiling_g * 9
  - any override sets protein_g < protein_floor_g or fat_g > fat_ceiling_g
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok
from models import MacroRow

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    estimated_tdee_kcal: int
    target_deficit_kcal: int
    dose_weekday: int
    protein_floor_g: int
    fat_ceiling_g: int
    overrides: dict[str, dict[str, Any]]  # JSON string keys; converted to int in main()


def _build_row(
    calories: int,
    protein_g: int,
    fat_g: int,
    protein_floor_g: int,
    fat_ceiling_g: int,
    offset: int,
) -> MacroRow:
    if protein_g < protein_floor_g:
        raise ValueError(
            f"offset {offset}: protein_g {protein_g} is below protein_floor_g {protein_floor_g}"
        )
    if fat_g > fat_ceiling_g:
        raise ValueError(
            f"offset {offset}: fat_g {fat_g} exceeds fat_ceiling_g {fat_ceiling_g}"
        )
    carbs_kcal = calories - (protein_g * 4) - (fat_g * 9)
    if carbs_kcal < 0:
        raise ValueError(
            f"offset {offset}: calories {calories} cannot satisfy "
            f"protein_floor_g {protein_floor_g}g and fat_ceiling_g {fat_ceiling_g}g constraints"
        )
    return MacroRow(
        calories=calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_kcal // 4,
        restrictions=[],
    )


def recompute(
    estimated_tdee_kcal: int,
    target_deficit_kcal: int,
    protein_floor_g: int,
    fat_ceiling_g: int,
    overrides: dict[int, dict[str, Any]],
) -> list[MacroRow]:
    """Redistribute weekly kcal target across 7 rows, landing override rows verbatim.

    weekly_intake = estimated_tdee_kcal * 7 - target_deficit_kcal.
    Remaining budget after overrides distributed by floor division.
    """
    weekly_intake = estimated_tdee_kcal * 7 - target_deficit_kcal

    for offset in overrides:
        if not 0 <= offset <= 6:
            raise ValueError(f"invalid override offset {offset}: must be 0..6")
        if "calories" not in overrides[offset]:
            raise ValueError(f"override at offset {offset} must include 'calories'")

    override_calories_sum = sum(ov["calories"] for ov in overrides.values())
    remaining_kcal = weekly_intake - override_calories_sum
    if remaining_kcal < 0:
        raise ValueError(
            f"override calories {override_calories_sum} exceed "
            f"weekly_intake_kcal_target {weekly_intake}"
        )

    non_override_count = 7 - len(overrides)
    if non_override_count == 0 and remaining_kcal != 0:
        raise ValueError(
            f"all 7 rows overridden but override calories {override_calories_sum} "  
            f"do not equal weekly_intake_kcal_target {weekly_intake}"
        )
    # Floor division: e.g. 11,050 // 6 = 1,841 (4 kcal/week not distributed)
    per_day_kcal = remaining_kcal // non_override_count if non_override_count > 0 else 0

    rows: list[MacroRow] = []
    for offset in range(7):
        if offset in overrides:
            ov = overrides[offset]
            rows.append(_build_row(
                calories=ov["calories"],
                protein_g=ov.get("protein_g", protein_floor_g),
                fat_g=ov.get("fat_g", fat_ceiling_g),
                protein_floor_g=protein_floor_g,
                fat_ceiling_g=fat_ceiling_g,
                offset=offset,
            ))
        else:
            rows.append(_build_row(
                calories=per_day_kcal,
                protein_g=protein_floor_g,
                fat_g=fat_ceiling_g,
                protein_floor_g=protein_floor_g,
                fat_ceiling_g=fat_ceiling_g,
                offset=offset,
            ))
    return rows


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

    int_overrides = {int(k): v for k, v in inp.overrides.items()}

    print(
        json.dumps({
            "tool": "recompute_macros_with_overrides",
            "phase": "input",
            "args": inp.model_dump(),
        }),
        file=sys.stderr,
    )
    try:
        rows = recompute(
            estimated_tdee_kcal=inp.estimated_tdee_kcal,
            target_deficit_kcal=inp.target_deficit_kcal,
            protein_floor_g=inp.protein_floor_g,
            fat_ceiling_g=inp.fat_ceiling_g,
            overrides=int_overrides,
        )
    except ValueError as e:
        err(str(e))
        return

    weekly_intake = inp.estimated_tdee_kcal * 7 - inp.target_deficit_kcal
    result = {
        "weekly_kcal_target": weekly_intake,
        "rows": [row.model_dump() for row in rows],
    }
    print(
        json.dumps({
            "tool": "recompute_macros_with_overrides",
            "phase": "output",
            "result": result,
        }),
        file=sys.stderr,
    )
    ok(result)


if __name__ == "__main__":
    main()
