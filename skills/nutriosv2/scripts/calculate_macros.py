"""calculate_macros — portion and serving math for a base macro set.

Usage: python3 calculate_macros.py '<json_args>'

Args JSON schema:
  base_macros: {calories: int, protein_g: int, fat_g: int, carbs_g: int}
  portion:     float >= 0   (fraction of one serving; 0.5 = half)
  servings:    float >= 0   (number of servings; defaults to 1.0)

Returns {calories, protein_g, fat_g, carbs_g} as integers.
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok

from pydantic import BaseModel, field_validator


class _BaseMacros(BaseModel):
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int

    @field_validator("calories", "protein_g", "fat_g", "carbs_g")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("macro values must be >= 0")
        return v


class _Input(BaseModel):
    base_macros: _BaseMacros
    portion: float
    servings: float = 1.0

    @field_validator("portion", "servings")
    @classmethod
    def non_negative_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


def run_calculate_macros(base_macros: dict, portion: float, servings: float = 1.0) -> dict:
    inp = _Input(base_macros=base_macros, portion=portion, servings=servings)
    factor = inp.portion * inp.servings
    bm = inp.base_macros
    return {
        "calories": round(bm.calories * factor),
        "protein_g": round(bm.protein_g * factor),
        "fat_g": round(bm.fat_g * factor),
        "carbs_g": round(bm.carbs_g * factor),
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
        result = run_calculate_macros(
            raw["base_macros"],
            raw["portion"],
            raw.get("servings", 1.0),
        )
    except Exception as e:
        err(f"invalid input: {e}")
        return
    ok(result)


if __name__ == "__main__":
    main()
