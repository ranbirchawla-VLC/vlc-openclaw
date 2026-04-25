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


def macro_range_check(actual: float, r: MacroRange) -> Literal["LOW", "OK", "OVER", "UNSET"]:
    """Classify actual against a MacroRange. UNSET when both ends null."""
    if r.min is None and r.max is None:
        return "UNSET"
    if r.min is not None and actual < r.min:
        return "LOW"
    if r.max is not None and actual > r.max:
        return "OVER"
    return "OK"
