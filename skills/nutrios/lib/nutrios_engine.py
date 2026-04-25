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
    Recipe,
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


def _weekday_name(now: datetime, tz: str) -> str:
    """Return lowercase weekday name in the user's local TZ."""
    return now.astimezone(ZoneInfo(tz)).strftime("%A").lower()


def _find_pattern(patterns: list[DayPattern], day_type: str) -> DayPattern | None:
    for p in patterns:
        if p.day_type == day_type:
            return p
    return None


def resolve_day(now: datetime, tz: str, goals: Goals, mesocycle: Mesocycle) -> ResolvedDay:
    """Compute the resolved day from goals and mesocycle. Follows extension spec verbatim.

    Uses user's local TZ to determine weekday — critical for users east/west of UTC
    at day boundaries.
    """
    dow_key = _weekday_name(now, tz)
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
) -> WeightChange | None:
    """Return delta between current weight and the most recent entry older than since_days.

    Returns None when: weigh_ins is empty, or no entry exists older than since_days
    relative to now.
    """
    if not weigh_ins:
        return None
    superseded_ids = {w.supersedes for w in weigh_ins if w.supersedes is not None}
    active = sorted(
        [w for w in weigh_ins if w.id not in superseded_ids],
        key=lambda w: w.id,
    )
    if not active:
        return None
    current = active[-1].weight_lbs
    cutoff = now - timedelta(days=since_days)
    older = [w for w in active if datetime.fromisoformat(w.ts_iso.replace("Z", "+00:00")) < cutoff]
    if not older:
        return None
    prior = older[-1].weight_lbs
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


# ---------------------------------------------------------------------------
# Dose and events
# ---------------------------------------------------------------------------

def event_next(events: list[Event], now: datetime, tz: str, n: int = 2) -> list[Event]:
    """Return up to n strictly-future events (date > local today), sorted ascending by date.

    Events dated local-today belong to event_today, not event_next.
    Soft-deleted (removed=True) events are filtered out — engine is the single
    point of truth on the removed-event semantics.
    """
    today = now.astimezone(ZoneInfo(tz)).date()
    upcoming = sorted(
        [e for e in events if e.date > today and not e.removed],
        key=lambda e: e.date,
    )
    return upcoming[:n]


def event_today(events: list[Event], now: datetime, tz: str) -> Event | None:
    """Return the single event matching the user's local calendar date, or None.

    Soft-deleted (removed=True) events are skipped — a removed event on today
    must not surface as the day's event.
    """
    today = now.astimezone(ZoneInfo(tz)).date()
    for e in events:
        if e.date == today and not e.removed:
            return e
    return None


def is_dose_day(protocol: Protocol, now: datetime, tz: str) -> bool:
    """True when local today is the protocol's dose day of week.

    Pure weekday match — does not consider whether a dose was already
    logged. dose_reminder_due composes this with the not-yet-logged check;
    nutrios_dose calls this directly to disambiguate "wrong day" from
    "already logged" (both produce dose_reminder_due=False but need
    different rendered messages).
    """
    today_weekday = now.astimezone(ZoneInfo(tz)).strftime("%A").lower()
    return today_weekday == protocol.treatment.dose_day_of_week.lower()


def dose_reminder_due(
    protocol: Protocol, today_log_entries: list, now: datetime, tz: str
) -> bool:
    """True when local today is the dose day of week and no DoseLogEntry exists today."""
    if not is_dose_day(protocol, now, tz):
        return False
    return not any(isinstance(e, DoseLogEntry) for e in today_log_entries)


def dose_status(
    today_log_entries: list, is_dose_day: bool
) -> Literal["logged", "pending", "not_due"]:
    """Classify dose status from today's entries and whether today is the dose day.

    is_dose_day is computed by the caller (who has protocol + now) and passed in.
    This keeps the function pure without requiring protocol as a parameter.
    """
    has_dose = any(isinstance(e, DoseLogEntry) for e in today_log_entries)
    if has_dose:
        return "logged"
    if is_dose_day:
        return "pending"
    return "not_due"


# ---------------------------------------------------------------------------
# Advisory, protection, and setup
# ---------------------------------------------------------------------------

_SURGERY_WINDOW_DAYS = 7

def advisory_flags(
    protocol: Protocol,
    events: list[Event],
    mesocycle: Mesocycle,
    now: datetime,
    tz: str,
) -> list[Flag]:
    """Compute advisory flags. For steps 1-3: surgery_window only.

    Returns pre-rendered structured Flags; the LLM never authors advisory content.
    """
    flags: list[Flag] = []
    today = now.astimezone(ZoneInfo(tz)).date()
    for event in events:
        if event.removed:
            continue
        if event.event_type == "surgery":
            delta = (event.date - today).days
            if 0 <= delta <= _SURGERY_WINDOW_DAYS:
                flags.append(Flag(
                    code="surgery_window",
                    severity="warn",
                    message="Surgery scheduled within 7 days.",
                ))
    return flags


_PROTOCOL_CONFIRM_PHRASE = "confirm protocol change"
_RANGE_CONFIRM_PHRASE = "confirm macro range change"


def protected_gate_protocol(
    current: Protocol, proposed: Protocol, confirm_phrase: str
) -> GateResult:
    """Gate changes to fields listed in current.protected.

    Requires exact lowercase phrase if any protected field differs.
    Non-protected diffs pass through with applied=True.
    """
    protected_fields = {k for k, v in current.protected.items() if v}
    needs_gate = False
    for field in protected_fields:
        if getattr(current.treatment, field, None) != getattr(proposed.treatment, field, None):
            needs_gate = True
            break

    if not needs_gate:
        return GateResult(ok=True, reason=None, applied=True)

    if confirm_phrase == _PROTOCOL_CONFIRM_PHRASE:
        return GateResult(ok=True, reason=None, applied=True)

    return GateResult(
        ok=False,
        reason="protected_field_change_requires_confirm_phrase",
        applied=False,
    )


def protected_gate_range(
    current: MacroRange, proposed: MacroRange, confirm_phrase: str
) -> GateResult:
    """Gate any change to either end of a protected MacroRange.

    If current.protected=False, all changes pass through.
    """
    if not current.protected:
        return GateResult(ok=True, reason=None, applied=True)

    ends_changed = (current.min != proposed.min) or (current.max != proposed.max)
    if not ends_changed:
        return GateResult(ok=True, reason=None, applied=True)

    if confirm_phrase == _RANGE_CONFIRM_PHRASE:
        return GateResult(ok=True, reason=None, applied=True)

    return GateResult(
        ok=False,
        reason="protected_field_change_requires_confirm_phrase",
        applied=False,
    )


# Fixed marker order per spec; dependency logic enforced in setup_status.
_MARKER_ORDER = ("gallbladder", "tdee", "carbs_shape", "deficits", "nominal_deficit")


def setup_status(needs_setup: NeedsSetup) -> SetupStatus:
    """Return setup status with fixed marker order and dependency logic.

    Dependency rules:
        - 'deficits' is not surfaced while 'tdee' is still True.
        - 'nominal_deficit' is not surfaced while 'deficits' is still True.
    """
    marker_values = {m: getattr(needs_setup, m) for m in _MARKER_ORDER}
    remaining: list[str] = []

    for marker in _MARKER_ORDER:
        if not marker_values[marker]:
            continue
        # Dependency gates
        if marker == "deficits" and marker_values["tdee"]:
            continue
        if marker == "nominal_deficit" and marker_values["deficits"]:
            continue
        remaining.append(marker)

    next_marker = remaining[0] if remaining else None
    complete = all(not marker_values[m] for m in _MARKER_ORDER)

    return SetupStatus(
        complete=complete,
        next_marker=next_marker,
        markers_remaining=remaining,
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


# ---------------------------------------------------------------------------
# Recipe expansion — multiply per-serving macros by qty (servings)
# ---------------------------------------------------------------------------

def expand_recipe(recipe: Recipe, qty: float) -> dict:
    """Expand a recipe to total macros for `qty` servings.

    qty is in servings. Fractional servings are allowed (0.5, 0.25, 1.5).
    Must be > 0 — zero and negative qty are rejected.

    Returns {kcal, protein_g, carbs_g, fat_g}. kcal is int (rounded via
    int(round(...))). The other macros are float.
    """
    if qty <= 0:
        raise ValueError(
            f"expand_recipe: qty must be > 0, got {qty!r}. "
            "Recipes are expanded by serving count; zero and negative are rejected."
        )

    m = recipe.macros_per_serving
    return {
        "kcal":      int(round(m.kcal * qty)),
        "protein_g": m.protein_g * qty,
        "carbs_g":   m.carbs_g * qty,
        "fat_g":     m.fat_g * qty,
    }
