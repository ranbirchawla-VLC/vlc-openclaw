"""Pydantic models for NutriOS state entities."""

from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_WEEKDAY_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


class MacroRow(BaseModel):
    model_config = ConfigDict(strict=True)
    weekday: Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    restrictions: list[str]
    protein_floor_g: int
    fat_ceiling_g: int


class Intent(BaseModel):
    model_config = ConfigDict(strict=True)
    target_deficit_kcal: int | None = None
    protein_floor_g: int | None = None
    fat_ceiling_g: int | None = None
    rationale: str = ""


class Mesocycle(BaseModel):
    model_config = ConfigDict(strict=True)
    mesocycle_id: int
    user_id: int
    name: str
    weeks: int
    start_date: str
    end_date: str
    dose_weekday: int
    macro_table: list[MacroRow]
    intent: Intent
    status: Literal["active", "ended"]
    created_at: str
    ended_at: str | None = None

    @field_validator("weeks")
    @classmethod
    def weeks_gte_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("weeks must be >= 1")
        return v

    @field_validator("dose_weekday")
    @classmethod
    def dose_weekday_valid(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("dose_weekday must be 0..6")
        return v

    @field_validator("macro_table")
    @classmethod
    def macro_table_valid(cls, v: list) -> list:
        if len(v) != 7:
            raise ValueError(f"macro_table must have exactly 7 rows, got {len(v)}")
        weekdays = [r.weekday for r in v]
        if weekdays != _WEEKDAY_ORDER:
            raise ValueError(
                "macro_table rows must be in Sun→Sat order "
                "(sunday, monday, tuesday, wednesday, thursday, friday, saturday)"
            )
        return v


class Macros(BaseModel):
    model_config = ConfigDict(strict=True)
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int


class Ingredient(BaseModel):
    model_config = ConfigDict(strict=True)
    description: str


class Recipe(BaseModel):
    model_config = ConfigDict(strict=True)
    recipe_id: int
    user_id: int
    name: str
    macros: Macros
    ingredients: list[Ingredient] = []
    created_at: str


class MealLog(BaseModel):
    model_config = ConfigDict(strict=True)
    log_id: int
    user_id: int
    timestamp_utc: str
    timezone_at_log: str
    food_description: str
    macros: Macros
    source: Literal["recipe", "ad_hoc"]
    recipe_id: int | None
    recipe_name_snapshot: str | None
    supersedes: int | None

    @model_validator(mode="after")
    def recipe_id_consistency(self) -> "MealLog":
        match self.source:
            case "recipe":
                if self.recipe_id is None:
                    raise ValueError("recipe_id required when source is 'recipe'")
            case "ad_hoc":
                if self.recipe_id is not None:
                    raise ValueError("recipe_id forbidden when source is 'ad_hoc'")
            case _:
                raise ValueError(f"unknown source: {self.source}")
        return self
