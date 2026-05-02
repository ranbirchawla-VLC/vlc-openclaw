"""build_macro_grid; assemble a full 7-row macro grid from cycle intent.

Usage: python3 build_macro_grid.py '<json_args>'

Returns {rows: [7 MacroRow dicts, Sun-Sat order], weekly_kcal_target: int}.
Raises ValueError (surfaced via err()) on per-day constraint violations.
"""

from __future__ import annotations
import json
import os
import sys
from typing import Any, Literal

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok
from models import MacroRow

from pydantic import BaseModel, ConfigDict, field_validator


_WEEKDAY_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


class _WeekdayTarget(BaseModel):
    model_config = ConfigDict(strict=True)
    calories: int | None = None
    protein_g: int | None = None
    fat_g: int | None = None
    protein_floor_g: int | None = None
    fat_ceiling_g: int | None = None


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    estimated_tdee_kcal: int
    target_deficit_kcal: int
    deficit_unit: Literal["weekly_kcal", "daily_kcal"] = "weekly_kcal"
    protein_floor_g: int
    fat_ceiling_g: int
    dose_weekday: Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    per_weekday_targets: dict[str, _WeekdayTarget] = {}

    @field_validator("per_weekday_targets")
    @classmethod
    def targets_keys_valid(cls, v: dict) -> dict:
        invalid = set(v.keys()) - set(_WEEKDAY_ORDER)
        if invalid:
            raise ValueError(
                f"invalid per_weekday_targets keys (must be weekday names): {sorted(invalid)}"
            )
        return v


def build_grid(
    estimated_tdee_kcal: int,
    target_deficit_kcal: int,
    protein_floor_g: int,
    fat_ceiling_g: int,
    dose_weekday: str,
    deficit_unit: str = "weekly_kcal",
    per_weekday_targets: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Build the full 7-row macro grid from cycle intent, ordered Sun-Sat.

    Non-overridden days use baseline computation: TDEE - weekly_deficit/7.
    Per-day targets are sparse; absent fields use the baseline.
    Per-day protein_floor_g/fat_ceiling_g override the cycle baseline for that day only.
    """
    if per_weekday_targets is None:
        per_weekday_targets = {}

    for key in per_weekday_targets:
        if key not in _WEEKDAY_ORDER:
            raise ValueError(
                f"invalid per_weekday_targets key {key!r}: must be a weekday name"
            )

    weekly_deficit = target_deficit_kcal * 7 if deficit_unit == "daily_kcal" else target_deficit_kcal
    weekly_kcal_target = estimated_tdee_kcal * 7 - weekly_deficit
    baseline_calories = round(estimated_tdee_kcal - weekly_deficit / 7)

    rows: list[MacroRow] = []
    for weekday in _WEEKDAY_ORDER:
        tgt = per_weekday_targets.get(weekday) or {}

        pf = tgt.get("protein_floor_g")
        effective_protein_floor = pf if pf is not None else protein_floor_g

        fc = tgt.get("fat_ceiling_g")
        effective_fat_ceiling = fc if fc is not None else fat_ceiling_g

        cal = tgt.get("calories")
        day_calories = cal if cal is not None else baseline_calories

        pg = tgt.get("protein_g")
        day_protein = pg if pg is not None else effective_protein_floor

        fg = tgt.get("fat_g")
        day_fat = fg if fg is not None else effective_fat_ceiling

        if day_protein < effective_protein_floor:
            raise ValueError(
                f"{weekday}: protein_g {day_protein} is below effective protein_floor_g "
                f"{effective_protein_floor}. To allow this: provide a per-day protein_floor_g "
                f"for {weekday}, raise protein_g, or change the cycle protein_floor_g."
            )
        if day_fat > effective_fat_ceiling:
            raise ValueError(
                f"{weekday}: fat_g {day_fat} exceeds effective fat_ceiling_g "
                f"{effective_fat_ceiling}. To allow this: provide a per-day fat_ceiling_g "
                f"for {weekday}, lower fat_g, or change the cycle fat_ceiling_g."
            )

        carbs_kcal = day_calories - (day_protein * 4) - (day_fat * 9)
        if carbs_kcal < 0:
            raise ValueError(
                f"{weekday}: calories {day_calories} cannot satisfy "
                f"protein_floor_g {effective_protein_floor}g and fat_ceiling_g "
                f"{effective_fat_ceiling}g constraints"
            )

        rows.append(MacroRow(
            weekday=weekday,
            calories=day_calories,
            protein_g=day_protein,
            fat_g=day_fat,
            carbs_g=carbs_kcal // 4,
            restrictions=[],
            protein_floor_g=effective_protein_floor,
            fat_ceiling_g=effective_fat_ceiling,
        ))

    return {
        "rows": [r.model_dump() for r in rows],
        "weekly_kcal_target": weekly_kcal_target,
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

    str_targets = {k: v.model_dump() for k, v in inp.per_weekday_targets.items()}

    print(
        json.dumps({
            "tool": "build_macro_grid",
            "phase": "input",
            "args": inp.model_dump(),
        }),
        file=sys.stderr,
    )
    try:
        result = build_grid(
            estimated_tdee_kcal=inp.estimated_tdee_kcal,
            target_deficit_kcal=inp.target_deficit_kcal,
            protein_floor_g=inp.protein_floor_g,
            fat_ceiling_g=inp.fat_ceiling_g,
            dose_weekday=inp.dose_weekday,
            deficit_unit=inp.deficit_unit,
            per_weekday_targets=str_targets,
        )
    except ValueError as e:
        err(str(e))
        return

    print(
        json.dumps({
            "tool": "build_macro_grid",
            "phase": "output",
            "result": result,
        }),
        file=sys.stderr,
    )
    ok(result)


if __name__ == "__main__":
    main()
