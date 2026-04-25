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


# ---------------------------------------------------------------------------
# Protocol and weight
# ---------------------------------------------------------------------------

def current_weight(weigh_ins: list[WeighIn]) -> float | None:
    """Return the most recent active weigh-in weight. Honors the supersedes chain.

    An entry is inactive if another entry's supersedes field points at its id.
    """
    if not weigh_ins:
        return None
    superseded_ids = {w.supersedes for w in weigh_ins if w.supersedes is not None}
    active = [w for w in weigh_ins if w.id not in superseded_ids]
    if not active:
        return None
    return max(active, key=lambda w: w.id).weight_lbs


def weight_change(
    weigh_ins: list[WeighIn], now: datetime, since_days: int = 7
) -> WeightChange:
    """Return delta between current weight and the most recent entry older than since_days."""
    superseded_ids = {w.supersedes for w in weigh_ins if w.supersedes is not None}
    active = sorted(
        [w for w in weigh_ins if w.id not in superseded_ids],
        key=lambda w: w.id,
    )
    current = active[-1].weight_lbs
    cutoff = now - timedelta(days=since_days)
    older = [w for w in active if datetime.fromisoformat(w.ts_iso.replace("Z", "+00:00")) < cutoff]
    prior = older[-1].weight_lbs if older else current
    return WeightChange(
        since_days=since_days,
        delta_lbs=round(current - prior, 4),
        current_lbs=current,
        prior_lbs=prior,
    )


def weight_trend(weigh_ins: list[WeighIn], last_n: int = 5) -> list[WeighInRow]:
    """Return last n active weigh-ins as date+weight rows, oldest first."""
    superseded_ids = {w.supersedes for w in weigh_ins if w.supersedes is not None}
    active = sorted(
        [w for w in weigh_ins if w.id not in superseded_ids],
        key=lambda w: w.id,
    )
    selected = active[-last_n:]
    return [
        WeighInRow(
            date=datetime.fromisoformat(w.ts_iso.replace("Z", "+00:00")).date(),
            weight_lbs=w.weight_lbs,
        )
        for w in selected
    ]


def macro_range_check(actual: float, r: MacroRange) -> Literal["LOW", "OK", "OVER", "UNSET"]:
    """Classify actual against a MacroRange. UNSET when both ends null."""
    if r.min is None and r.max is None:
        return "UNSET"
    if r.min is not None and actual < r.min:
        return "LOW"
    if r.max is not None and actual > r.max:
        return "OVER"
    return "OK"
