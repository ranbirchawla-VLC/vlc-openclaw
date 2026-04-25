"""NutriOS v2 engine — pure functions, no I/O, no datetime.now() calls.

Time is always passed as a parameter. All engine functions that can fail
return a structured GateResult, never a bare string (Tripwire 4).
No imports from nutrios_store. No user-personalized strings in return values (Tripwire 1).
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from nutrios_models import (
    MacroRange, DayMacros, DayPattern, Goals, Mesocycle, ResolvedDay,
    Protocol, Treatment,
    WeighIn, WeighInRow, WeightChange,
    Event, NeedsSetup,
    FoodLogEntry, DoseLogEntry,
    GateResult, SetupStatus, Flag, Proximity,
)


# ---------------------------------------------------------------------------
# Macro and kcal
# ---------------------------------------------------------------------------

def merge_range(default: MacroRange, override: MacroRange | None) -> MacroRange:
    """Sparse override: any non-null end on override wins; null end inherits default."""
    if override is None:
        return default
    merged_min = override.min if override.min is not None else default.min
    merged_max = override.max if override.max is not None else default.max
    return MacroRange(min=merged_min, max=merged_max, protected=default.protected)


def range_proximity(
    actual: float, r: MacroRange, threshold_pct: float = 0.2, macro: str = ""
) -> Proximity | None:
    """Return a proximity hint when actual is within threshold_pct of an active bound.

    Checks max first (closest-to-ceiling warning), then min.
    Returns None when: no active bounds, actual is already over/under the bound,
    or actual is farther than threshold_pct from both bounds.

    The `macro` parameter lets callers label the result (e.g. "fat_g").
    """
    if r.max is not None and actual <= r.max:
        distance = r.max - actual
        if r.max > 0 and distance / r.max <= threshold_pct:
            return Proximity(macro=macro, end="max", distance_g=round(distance, 4))
    if r.min is not None and actual >= r.min:
        distance = actual - r.min
        if r.min > 0 and distance / r.min <= threshold_pct:
            return Proximity(macro=macro, end="min", distance_g=round(distance, 4))
    return None


def _weekday_name(now: datetime) -> str:
    """Return lowercase weekday name matching Goals.weekly_schedule keys."""
    return now.strftime("%A").lower()


def _find_pattern(patterns: list[DayPattern], day_type: str) -> DayPattern | None:
    for p in patterns:
        if p.day_type == day_type:
            return p
    return None


def resolve_day(now: datetime, goals: Goals, mesocycle: Mesocycle) -> ResolvedDay:
    """Compute the resolved day from goals and mesocycle. Follows extension spec verbatim."""
    dow_key = _weekday_name(now)
    day_type = goals.weekly_schedule[dow_key]
    pattern = _find_pattern(goals.day_patterns, day_type)
    effective_deficit = (
        pattern.deficit_kcal
        if pattern and pattern.deficit_kcal is not None
        else mesocycle.deficit_kcal
    )
    kcal_target = (
        (mesocycle.tdee_kcal - effective_deficit)
        if mesocycle.tdee_kcal is not None
        else None
    )
    return ResolvedDay(
        day_type=day_type,
        kcal_target=kcal_target,
        protein_g=merge_range(goals.defaults.protein_g, pattern.protein_g if pattern else None),
        carbs_g=merge_range(goals.defaults.carbs_g, pattern.carbs_g if pattern else None),
        fat_g=merge_range(goals.defaults.fat_g, pattern.fat_g if pattern else None),
        tdee_kcal=mesocycle.tdee_kcal,
        deficit_kcal=effective_deficit,
    )


def macro_range_check(actual: float, r: MacroRange) -> Literal["LOW", "OK", "OVER", "UNSET"]:
    """Classify actual against a MacroRange. UNSET when both ends null."""
    if r.min is None and r.max is None:
        return "UNSET"
    if r.min is not None and actual < r.min:
        return "LOW"
    if r.max is not None and actual > r.max:
        return "OVER"
    return "OK"
