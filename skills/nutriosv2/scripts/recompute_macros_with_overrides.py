"""recompute_macros_with_overrides; redistribute weekly kcal budget with per-day overrides.

Usage: python3 recompute_macros_with_overrides.py '<json_args>'

Args JSON schema:
  estimated_tdee_kcal: int    ; user's estimated total daily energy expenditure
  target_deficit_kcal: int    ; WEEKLY deficit in kcal (same unit as compute_candidate_macros)
  protein_floor_g: int        ; minimum daily protein for all non-overridden rows
  fat_ceiling_g: int          ; maximum daily fat for all non-overridden rows
  overrides: object           ; map of weekday name ("sunday".."saturday") to row overrides.
    All fields optional; absent fields default to baseline. Per-day protein_floor_g /
    fat_ceiling_g override the baseline for that day only.

Returns {"weekly_kcal_target": int, "rows": [7 MacroRow-shaped dicts, ordered Sun→Sat]}.

Rounding: remaining kcal after calorie-overridden rows distributed by floor division.
  Example: 11,050 remaining for 6 days = 11,050 // 6 = 1,841 (4 kcal/week not distributed).

Raises ValueError (surfaced via err()) when:
  - total override calories exceed weekly_intake_kcal_target
  - remaining per-day kcal cannot cover effective protein_floor_g * 4 + fat_ceiling_g * 9
  - any override sets protein_g < effective protein_floor_g or fat_g > effective fat_ceiling_g
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok
from models import MacroRow

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


_WEEKDAY_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


class _OverrideEntry(BaseModel):
    model_config = ConfigDict(strict=True)
    calories: int | None = None
    protein_g: int | None = None
    fat_g: int | None = None
    carbs_g: int | None = None
    restrictions: list[str] | None = None
    protein_floor_g: int | None = None
    fat_ceiling_g: int | None = None


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    estimated_tdee_kcal: int
    target_deficit_kcal: int
    protein_floor_g: int
    fat_ceiling_g: int
    overrides: dict[str, _OverrideEntry]

    @field_validator("overrides")
    @classmethod
    def overrides_valid(cls, v: dict) -> dict:
        invalid = set(v.keys()) - set(_WEEKDAY_ORDER)
        if invalid:
            raise ValueError(f"invalid override keys (must be weekday names): {sorted(invalid)}")
        return v


def _build_row(
    weekday: str,
    calories: int,
    protein_g: int,
    fat_g: int,
    protein_floor_g: int,
    fat_ceiling_g: int,
) -> MacroRow:
    if protein_g < protein_floor_g:
        raise ValueError(
            f"{weekday}: protein_g {protein_g} is below protein_floor_g {protein_floor_g}"
        )
    if fat_g > fat_ceiling_g:
        raise ValueError(
            f"{weekday}: fat_g {fat_g} exceeds fat_ceiling_g {fat_ceiling_g}"
        )
    carbs_kcal = calories - (protein_g * 4) - (fat_g * 9)
    if carbs_kcal < 0:
        raise ValueError(
            f"{weekday}: calories {calories} cannot satisfy "
            f"protein_floor_g {protein_floor_g}g and fat_ceiling_g {fat_ceiling_g}g constraints"
        )
    return MacroRow(
        weekday=weekday,
        calories=calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_kcal // 4,
        restrictions=[],
        protein_floor_g=protein_floor_g,
        fat_ceiling_g=fat_ceiling_g,
    )


def recompute(
    estimated_tdee_kcal: int,
    target_deficit_kcal: int,
    protein_floor_g: int,
    fat_ceiling_g: int,
    overrides: dict[str, dict[str, Any]],
) -> list[MacroRow]:
    """Redistribute weekly kcal target across 7 rows, ordered Sun→Sat.

    weekly_intake = estimated_tdee_kcal * 7 - target_deficit_kcal.
    Override keys are weekday names. Rows with explicit calories reserve from the weekly
    budget; remaining budget distributed by floor division across all other rows.
    Rows with only per-day floor/ceiling (no calories key) participate in redistribution.
    Per-day protein_floor_g / fat_ceiling_g in an override apply to that day only.
    """
    weekly_intake = estimated_tdee_kcal * 7 - target_deficit_kcal

    for weekday in overrides:
        if weekday not in _WEEKDAY_ORDER:
            raise ValueError(f"invalid override key {weekday!r}: must be a weekday name")

    days_with_calorie_override = {w for w, ov in overrides.items() if ov.get("calories") is not None}
    override_calories_sum = sum(overrides[w]["calories"] for w in days_with_calorie_override)
    remaining_kcal = weekly_intake - override_calories_sum
    if remaining_kcal < 0:
        raise ValueError(
            f"override calories {override_calories_sum} exceed "
            f"weekly_intake_kcal_target {weekly_intake}"
        )

    non_override_count = 7 - len(days_with_calorie_override)
    if non_override_count == 0 and remaining_kcal != 0:
        raise ValueError(
            f"all 7 rows overridden but override calories {override_calories_sum} "
            f"do not equal weekly_intake_kcal_target {weekly_intake}"
        )
    # Floor division: e.g. 11,050 // 6 = 1,841 (4 kcal/week not distributed)
    per_day_kcal = remaining_kcal // non_override_count if non_override_count > 0 else 0

    rows: list[MacroRow] = []
    for weekday in _WEEKDAY_ORDER:
        ov = overrides.get(weekday) or {}
        pf = ov.get("protein_floor_g")
        day_protein_floor = pf if pf is not None else protein_floor_g
        fc = ov.get("fat_ceiling_g")
        day_fat_ceiling = fc if fc is not None else fat_ceiling_g
        if weekday in days_with_calorie_override:
            pg = ov.get("protein_g")
            fg = ov.get("fat_g")
            rows.append(_build_row(
                weekday=weekday,
                calories=ov["calories"],
                protein_g=pg if pg is not None else day_protein_floor,
                fat_g=fg if fg is not None else day_fat_ceiling,
                protein_floor_g=day_protein_floor,
                fat_ceiling_g=day_fat_ceiling,
            ))
        else:
            rows.append(_build_row(
                weekday=weekday,
                calories=per_day_kcal,
                protein_g=day_protein_floor,
                fat_g=day_fat_ceiling,
                protein_floor_g=day_protein_floor,
                fat_ceiling_g=day_fat_ceiling,
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

    str_overrides = {k: v.model_dump() for k, v in inp.overrides.items()}

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
            overrides=str_overrides,
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
