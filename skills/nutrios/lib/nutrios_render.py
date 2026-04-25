"""NutriOS v2 render — Telegram plain-text formatters.

Pure functions. No I/O, no store, no engine calls, no datetime.now().
Inputs are Pydantic models and primitives. Outputs are str.
Empty string ("") means suppression; callers filter before joining.
Numbers are formatted here — LLM never formats numbers.

Tripwire 3: any UTC timestamp displayed must parse via nutrios_time.parse().
Tripwire 4: error strings use template branches keyed on exact reason codes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from nutrios_models import (
    MacroRange, ResolvedDay,
    Protocol, Mesocycle, Goals,
    WeighIn, WeighInRow, WeightChange,
    MedNote, Event, FoodLogEntry, DoseLogEntry,
    GateResult, Flag,
    Recipe,
)
import nutrios_time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EN_DASH = "–"   # –  (U+2013) used between range bounds
_MINUS   = "−"   # −  (U+2212) used for negative deltas and kcal derivation
_MACRO_LINE_WIDTH = 32   # total chars in a rendered macro line
_FIRST_COL_WIDTH  = 15   # "Name: actual g" portion

# Slot display order and labels for daily summary
_SLOT_ORDER = ("breakfast", "lunch", "dinner", "snack")
_SLOT_LABELS = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"}


# ---------------------------------------------------------------------------
# Macro and kcal
# ---------------------------------------------------------------------------

def render_macro_line(
    name: str,
    actual: float,
    r: MacroRange,
    status: Literal["LOW", "OK", "OVER", "UNSET"],
) -> str:
    """Render one macro line for the daily summary.

    Returns "" when both range ends are null (UNSET) — caller filters.
    All four branches produce a fixed-width line of _MACRO_LINE_WIDTH chars.
    En-dash (U+2013) separates range bounds when both ends are set.
    """
    if r.min is None and r.max is None:
        return ""

    actual_int = int(actual)
    val_width = _FIRST_COL_WIDTH - len(name) - 1 - 1   # subtract name, colon, g
    first_col = f"{name}:{actual_int:>{val_width}}g"    # always _FIRST_COL_WIDTH chars

    if r.min is not None and r.max is not None:
        range_str = f"{r.min}{_EN_DASH}{r.max}g"
    elif r.min is not None:
        range_str = f"min {r.min}g"
    else:
        range_str = f"max {r.max}g"

    prefix = f"{first_col} / {range_str}"
    status_width = _MACRO_LINE_WIDTH - len(prefix)
    return f"{prefix}{status:>{status_width}}"


def render_kcal_line(
    actual: int,
    target: int | None,
    tdee: int | None,
    deficit: int,
) -> str:
    """Render the calorie line for the daily summary.

    Three branches:
      - target is None            → "Calories: setup needed"
      - target set, no tdee       → "Calories: 1840 / 2000"
      - target set, tdee + deficit → "Calories: 1840 / 2000   (TDEE 2600 − 600)"
    Minus sign is U+2212 in the derivation suffix.
    """
    if target is None:
        return "Calories: setup needed"
    if tdee is not None and deficit:
        return f"Calories: {actual} / {target}   (TDEE {tdee} {_MINUS} {deficit})"
    return f"Calories: {actual} / {target}"


# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------

def render_weigh_in_confirm(
    weigh_in: WeighIn,
    change: WeightChange | None,
    progress: dict | None,
) -> str:
    """Confirm a weigh-in. Suppresses delta line when change is None."""
    lines = [f"Weigh-in logged: {weigh_in.weight_lbs} lbs"]
    if change is not None:
        sign = _MINUS if change.delta_lbs < 0 else "+"
        abs_delta = abs(change.delta_lbs)
        lines.append(f"  {sign}{abs_delta} lbs vs {change.since_days}d ago ({change.prior_lbs} lbs)")
    if progress is not None:
        target = progress.get("target_lbs")
        pct = progress.get("pct_to_goal")
        if target is not None and pct is not None:
            lines.append(f"  Goal: {target} lbs ({pct:.0f}% there)")
    return "\n".join(lines)


def render_weight_trend(
    rows: list[WeighInRow],
    rate_per_week: float | None,
) -> str:
    """Multi-line weight trend: header, one row per weigh-in, optional rate."""
    lines = [f"Weight trend (last {len(rows)} weigh-ins):"]
    prev_weight: float | None = None
    for row in rows:
        date_str = row.date.strftime("%Y-%m-%d")
        if prev_weight is not None:
            delta = row.weight_lbs - prev_weight
            sign = _MINUS if delta < 0 else "+"
            delta_str = f"  {sign}{abs(delta):.1f}"
        else:
            delta_str = ""
        lines.append(f"  {date_str}   {row.weight_lbs:.1f}{delta_str}")
        prev_weight = row.weight_lbs
    if rate_per_week is not None:
        sign = _MINUS if rate_per_week < 0 else "+"
        lines.append(f"Rate: {sign}{abs(rate_per_week):.1f} lbs/week")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dose
# ---------------------------------------------------------------------------

def render_dose_confirm(dose_entry: DoseLogEntry) -> str:
    """Confirm a dose was logged."""
    ts_date = nutrios_time.parse(dose_entry.ts_iso).date()
    return f"Dose logged: {dose_entry.dose_mg} mg {dose_entry.brand} ({ts_date})"


def render_dose_not_due(next_dose_day: str, next_dose_date: date) -> str:
    """Rejection when user attempts dose on a non-dose day."""
    return f"Not a dose day. Next dose: {next_dose_day.capitalize()} ({next_dose_date})"


# ---------------------------------------------------------------------------
# Notes and protocol
# ---------------------------------------------------------------------------

def render_med_note_confirm(note: MedNote) -> str:
    """Confirm a med note was saved."""
    return f"Note saved ({note.source}): {note.note}"


def render_protocol_view(protocol: Protocol, recent_notes: list[MedNote]) -> str:
    """Multi-line protocol view: treatment, biometrics, clinical, recent notes."""
    t = protocol.treatment
    b = protocol.biometrics
    c = protocol.clinical
    lines = [
        "Protocol",
        f"  {t.medication} ({t.brand})",
        f"  Dose: {t.dose_mg} mg — {t.dose_day_of_week.capitalize()} at {t.dose_time}",
    ]
    if t.titration_notes:
        lines.append(f"  Titration: {t.titration_notes}")
    if t.next_transition_plan:
        lines.append(f"  Next: {t.next_transition_plan}")
    lines += [
        "",
        "Biometrics",
        f"  Start: {b.start_weight_lbs} lbs ({b.start_date})",
        f"  Target: {b.target_weight_lbs} lbs",
    ]
    if b.lean_mass_lbs is not None:
        lines.append(f"  Lean mass: {b.lean_mass_lbs} lbs")
    lines += [
        "",
        "Clinical",
        f"  Gallbladder: {c.gallbladder_status}",
        f"  Thyroid medication: {'yes' if c.thyroid_medication else 'no'}",
        f"  CGM active: {'yes' if c.cgm_active else 'no'}",
    ]
    if recent_notes:
        lines += ["", "Recent notes"]
        for note in recent_notes[-3:]:
            note_date = nutrios_time.parse(note.ts_iso).date()
            lines.append(f"  {note_date}  {note.source}: {note.note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def render_event_added(event: Event) -> str:
    """Confirm an event was added."""
    return f"Event added: {event.title} ({event.date})"


def render_event_trigger(event: Event) -> str:
    """Prepended to a response when today matches an event date."""
    return f"Today: {event.title}"


# ---------------------------------------------------------------------------
# Advisory
# ---------------------------------------------------------------------------

def render_advisory(flags: list[Flag]) -> str:
    """Render advisory flags. Returns "" when flags is empty."""
    if not flags:
        return ""
    lines = []
    for f in flags:
        lines.append(f"[{f.severity}] {f.message}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gate errors — Tripwire 4
# ---------------------------------------------------------------------------

_GATE_ERROR_TEMPLATES: dict[str, str] = {
    "protected_field_change_requires_confirm_phrase": (
        'Protected field. To confirm this change, reply with the exact phrase: '
        '"confirm protocol change" or "confirm macro range change" as appropriate.'
    ),
}


def render_gate_error(result: GateResult) -> str:
    """Map a GateResult to a user-facing error string.

    Returns "" for ok=True results.
    Raises ValueError for None reason or unknown reason codes — spec drift must
    not produce generic fallback text.
    """
    if result.ok:
        return ""
    if result.reason is None:
        raise ValueError(
            "render_gate_error requires GateResult.reason to be set; "
            "ok=False but reason is None — malformed GateResult"
        )
    if result.reason not in _GATE_ERROR_TEMPLATES:
        raise ValueError(
            f"No render template for GateResult.reason={result.reason!r}. "
            "Add a template branch in nutrios_render._GATE_ERROR_TEMPLATES."
        )
    return _GATE_ERROR_TEMPLATES[result.reason]


# ---------------------------------------------------------------------------
# Setup resume
# ---------------------------------------------------------------------------

def render_setup_resume_prompt(marker: str, context: dict) -> str:
    """Return canonical setup prompt for a given marker.

    Uses literal text from Extension v3 Part 6.2. Context fields interpolated
    for carbs_shape, deficits, and nominal_deficit; gallbladder and tdee are fixed.
    Raises ValueError for any marker outside the canonical five.
    """
    match marker:
        case "gallbladder":
            return (
                "Quick setup question: has your gallbladder been removed?\n"
                "This affects fat-ceiling recommendations.\n"
                "Reply: removed / present / unknown"
            )

        case "tdee":
            return (
                "What's your TDEE (total daily energy expenditure) for this cycle?\n"
                "This is the kcal baseline before any deficit.\n"
                "Reply with a number, e.g. 2600."
            )

        case "carbs_shape":
            patterns = context.get("day_patterns", [])
            pattern_lines = "\n".join(
                f"- {name}: min {min_g}g" for name, min_g in patterns
            )
            return (
                "Your v1 carbs came over as a minimum. Is that right?\n"
                f"{pattern_lines}\n\n"
                "Reply: yes (keep as minimums), max (change to maximums), "
                "both (set both ends), or adjust each."
            )

        case "deficits":
            tdee = context.get("tdee", "?")
            suggestions = context.get("suggestions", [])
            suggestion_lines = "\n".join(
                f"- {day_type}: deficit {deficit} (v1 was {v1_kcal})"
                for day_type, deficit, v1_kcal in suggestions
            )
            return (
                f"With TDEE {tdee}, here are the deficits from your v1 kcal targets:\n"
                f"{suggestion_lines}\n\n"
                "Reply 'yes' to confirm all, or specify changes (e.g. \"rest 500\")."
            )

        case "nominal_deficit":
            deficits = context.get("deficits", [])
            most_common = context.get("most_common", "?")
            deficit_lines = "\n".join(
                f"- {day_type}: {deficit}" for day_type, deficit in deficits
            )
            return (
                "Which deficit should be the cycle nominal? "
                "Day types not matching it become overrides.\n"
                f"{deficit_lines}\n"
                f"Most common: {most_common} "
                f"({'confirmed deficits shown above'}).\n"
                f"Reply 'yes' for {most_common}, or specify (e.g. '500')."
            )

        case _:
            raise ValueError(
                f"Unknown setup marker: {marker!r}. "
                "Valid markers: gallbladder, tdee, carbs_shape, deficits, nominal_deficit."
            )


def render_setup_complete() -> str:
    """One-time confirmation when all setup markers are cleared."""
    return (
        "Setup complete. Your targets and protocol are now fully configured.\n"
        "Daily summaries will show kcal targets. Use 'goals' to review or adjust."
    )


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------

def render_daily_summary(
    resolved: ResolvedDay,
    meals: list[FoodLogEntry],
    dose_status: Literal["logged", "pending", "not_due"],
    upcoming_events: list[Event],
    advisory: list[Flag],
    weigh_in_today: WeighIn | None,
    weigh_in_change: WeightChange | None,
    protein_status: Literal["LOW", "OK", "OVER", "UNSET"],
    carbs_status: Literal["LOW", "OK", "OVER", "UNSET"],
    fat_status: Literal["LOW", "OK", "OVER", "UNSET"],
    protein_actual: float,
    carbs_actual: float,
    fat_actual: float,
    kcal_actual: int,
    now: datetime,
    tz: str,
) -> str:
    """Compose full daily summary top-to-bottom.

    Caller pre-computes macro totals and statuses via nutrios_engine; render
    consumes them. No engine import here.

    Layout: advisory, date header, weigh-in, kcal, macro lines, meal list,
    dose, events. Empty strings are filtered before joining. No trailing newline.
    """
    local_now = nutrios_time.to_local(now, tz)
    date_header = local_now.strftime("%a %b %d").lstrip("0")

    # Dose line
    match dose_status:
        case "logged":
            dose_line = "Dose: logged"
        case "pending":
            dose_line = "Dose: pending — log your dose"
        case "not_due":
            dose_line = ""

    # Upcoming events (≤14 days, compact)
    event_lines = [f"  {ev.date}  {ev.title}" for ev in upcoming_events]

    # Meal list grouped by slot
    by_slot: dict[str, list[FoodLogEntry]] = {s: [] for s in _SLOT_ORDER}
    for e in meals:
        by_slot[e.meal_slot].append(e)

    meal_block_lines = []
    for slot in _SLOT_ORDER:
        entries = by_slot[slot]
        if entries:
            meal_block_lines.append(_SLOT_LABELS[slot])
            for entry in entries:
                meal_block_lines.append(f"  {entry.name}   {entry.kcal} kcal")

    # Weigh-in line
    if weigh_in_today is not None:
        if weigh_in_change is not None:
            sign = _MINUS if weigh_in_change.delta_lbs < 0 else "+"
            abs_delta = abs(weigh_in_change.delta_lbs)
            weigh_line = f"Weighed in: {weigh_in_today.weight_lbs} lbs ({sign}{abs_delta} from last)"
        else:
            weigh_line = f"Weighed in: {weigh_in_today.weight_lbs} lbs"
    else:
        weigh_line = ""

    sections = []

    # 1. Advisory (if non-empty)
    adv = render_advisory(advisory)
    if adv:
        sections.append(adv)

    # 2. Date header and day type
    sections.append(f"{date_header}  [{resolved.day_type}]")

    # 3. Weigh-in (between date header and macro lines)
    if weigh_line:
        sections.append(weigh_line)

    # 4. Macro lines — kcal first, then protein, carbs, fat (suppress unset)
    sections.append(render_kcal_line(kcal_actual, resolved.kcal_target, resolved.tdee_kcal, resolved.deficit_kcal))

    for line in [
        render_macro_line("Protein", protein_actual, resolved.protein_g, protein_status),
        render_macro_line("Carbs",   carbs_actual,   resolved.carbs_g,   carbs_status),
        render_macro_line("Fat",     fat_actual,     resolved.fat_g,     fat_status),
    ]:
        if line:
            sections.append(line)

    # 5. Meal list
    if meal_block_lines:
        sections.append("\n".join(meal_block_lines))

    # 6. Dose status
    if dose_line:
        sections.append(dose_line)

    # 7. Upcoming events
    if event_lines:
        sections.append("Upcoming:\n" + "\n".join(event_lines))

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Tool-layer renderers — added in step 6+6.6 for the Python tool entrypoints
# ---------------------------------------------------------------------------

def _fmt_g(x: float) -> str:
    """Format a gram quantity: drop trailing zeros, no unit suffix."""
    return f"{x:g}"


def render_log_confirm(entry: FoodLogEntry) -> str:
    """Confirm a single food log entry. One-line, name + qty + macros."""
    return (
        f"Logged: {entry.name} {_fmt_g(entry.qty)}{entry.unit} — "
        f"{entry.kcal} kcal · "
        f"{_fmt_g(entry.protein_g)}g P / "
        f"{_fmt_g(entry.carbs_g)}g C / "
        f"{_fmt_g(entry.fat_g)}g F"
    )


def render_quantity_clarify(name: str) -> str:
    """Followup prompt when a food was logged without a quantity."""
    return f"How much {name}?"


def render_macros_required(name: str) -> str:
    """Followup prompt when an unknown food needs macros from the LLM/user.

    Tool layer cannot resolve foods → macros (D2 decision: macros always
    arrive on input). When the orchestrator's resolution step skips this,
    the tool surfaces this message so the next turn carries them.
    """
    return (
        f"I don't have macros for '{name}'. "
        f"Provide kcal, protein, carbs, and fat to log it."
    )


def render_dose_already_logged() -> str:
    """Rejection when a dose log is attempted but today already has one."""
    return "Dose already logged today. Edit via supersedes if you need to correct it."


def render_event_list(events: list[Event]) -> str:
    """Render a compact list of upcoming events. Suppresses removed entries."""
    active = [e for e in events if not e.removed]
    if not active:
        return "No upcoming events."
    lines = ["Upcoming events:"]
    for e in active:
        lines.append(f"  {e.date}  {e.event_type}: {e.title}")
    return "\n".join(lines)


def render_event_removed_confirm(event: Event) -> str:
    """Confirm an event was soft-deleted."""
    return f"Event removed: {event.title} ({event.date})"


def render_med_notes_list(notes: list[MedNote]) -> str:
    """Render a med-notes list with date, source, and note text per row."""
    if not notes:
        return "No notes."
    lines = ["Recent notes:"]
    for n in notes:
        note_date = nutrios_time.parse(n.ts_iso).date()
        lines.append(f"  {note_date}  {n.source}: {n.note}")
    return "\n".join(lines)


def render_goals_view(goals: Goals, mesocycle: Mesocycle) -> str:
    """Multi-section view of the goals state plus mesocycle TDEE/deficit context."""
    lines = ["Goals", f"  Cycle: {mesocycle.cycle_id} ({mesocycle.phase})"]

    if mesocycle.tdee_kcal is None:
        lines.append("  TDEE: setup needed")
    else:
        lines.append(f"  TDEE: {mesocycle.tdee_kcal} / Deficit: {mesocycle.deficit_kcal}")

    lines += ["", "Defaults"]
    for label, r in (
        ("Protein", goals.defaults.protein_g),
        ("Carbs",   goals.defaults.carbs_g),
        ("Fat",     goals.defaults.fat_g),
    ):
        if r.min is None and r.max is None:
            continue
        if r.min is not None and r.max is not None:
            shape = f"{r.min}{_EN_DASH}{r.max}g"
        elif r.min is not None:
            shape = f"min {r.min}g"
        else:
            shape = f"max {r.max}g"
        suffix = " (protected)" if r.protected else ""
        lines.append(f"  {label}: {shape}{suffix}")

    if goals.day_patterns:
        lines += ["", "Day patterns"]
        for dp in goals.day_patterns:
            parts = []
            for label, r in (
                ("protein", dp.protein_g),
                ("carbs",   dp.carbs_g),
                ("fat",     dp.fat_g),
            ):
                if r.min is None and r.max is None:
                    continue
                if r.min is not None and r.max is not None:
                    parts.append(f"{label} {r.min}{_EN_DASH}{r.max}g")
                elif r.min is not None:
                    parts.append(f"{label} min {r.min}g")
                else:
                    parts.append(f"{label} max {r.max}g")
            if dp.deficit_kcal is not None:
                parts.append(f"deficit {dp.deficit_kcal}")
            tail = ", ".join(parts) if parts else "(no overrides)"
            lines.append(f"  {dp.day_type}: {tail}")

    lines += ["", "Weekly schedule"]
    _DOW_SHORT = {
        "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed",
        "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
    }
    _DOW_ORDER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    for dow in _DOW_ORDER:
        if dow in goals.weekly_schedule:
            lines.append(f"  {_DOW_SHORT[dow]}: {goals.weekly_schedule[dow]}")

    return "\n".join(lines)


def render_mesocycle_view(mesocycle: Mesocycle) -> str:
    """Compact view of a single mesocycle."""
    lines = [
        "Mesocycle",
        f"  ID: {mesocycle.cycle_id}",
        f"  Phase: {mesocycle.phase}",
        f"  Started: {mesocycle.start_date}",
    ]
    if mesocycle.end_date is not None:
        lines.append(f"  Ended: {mesocycle.end_date}")
    if mesocycle.tdee_kcal is None:
        lines.append("  TDEE: setup needed")
    else:
        lines.append(f"  TDEE: {mesocycle.tdee_kcal}")
    lines.append(f"  Deficit: {mesocycle.deficit_kcal}")
    if mesocycle.label is not None:
        lines.append(f"  Label: {mesocycle.label}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Recipe renderers
# ---------------------------------------------------------------------------

def _recipe_macro_summary(r: Recipe) -> str:
    """Compact one-line macros summary for a single recipe row."""
    m = r.macros_per_serving
    return (
        f"{m.kcal} kcal, "
        f"{_fmt_g(m.protein_g)}g P / "
        f"{_fmt_g(m.carbs_g)}g C / "
        f"{_fmt_g(m.fat_g)}g F"
    )


def render_recipe_save_confirm(recipe: Recipe) -> str:
    """Confirm a new recipe was saved."""
    return f"Recipe saved: {recipe.name} ({recipe.macros_per_serving.kcal} kcal/serving)"


def render_recipe_update_confirm(recipe: Recipe) -> str:
    """Confirm an existing recipe was updated."""
    return f"Recipe updated: {recipe.name} ({recipe.macros_per_serving.kcal} kcal/serving)"


def render_recipe_delete_confirm(recipe: Recipe) -> str:
    """Confirm a recipe was soft-deleted."""
    return f"Recipe deleted: {recipe.name}"


def render_recipe_list(recipes: list[Recipe]) -> str:
    """Compact list of active recipes (filters out removed=True)."""
    active = [r for r in recipes if not r.removed]
    if not active:
        return "No recipes saved."
    lines = [f"Recipes ({len(active)}):"]
    for r in active:
        lines.append(f"  {r.name} — {_recipe_macro_summary(r)}")
    return "\n".join(lines)


def render_recipe_view(recipe: Recipe) -> str:
    """Full detail view of a single recipe."""
    lines = [
        f"{recipe.name} ({recipe.servings} serving{'' if recipe.servings == 1 else 's'})",
        f"  {_recipe_macro_summary(recipe)}",
    ]
    if recipe.ingredients:
        lines.append("Ingredients:")
        for ing in recipe.ingredients:
            lines.append(f"  - {ing}")
    return "\n".join(lines)


def render_recipe_duplicate_name_error(name: str) -> str:
    """Reject a save that would duplicate an existing recipe name."""
    return (
        f"Recipe '{name}' already exists. "
        f"Use update to change it, or save under a different name."
    )


# ---------------------------------------------------------------------------
# Operation errors — Tripwire 4 (no f-string error composition in tools)
# ---------------------------------------------------------------------------

def render_supersedes_not_found(target_id: int, kind: str) -> str:
    """Reject an edit whose supersedes target doesn't exist."""
    return f"Edit failed: {kind} #{target_id} doesn't exist."


def render_protocol_not_initialized() -> str:
    """Tool ran but no protocol exists for the user."""
    return "Protocol not set. Run setup before logging doses or editing protocol."


def render_write_confirm(scope: str) -> str:
    """Generic write-confirm rendered per scope. Single source of truth."""
    match scope:
        case "goals":
            return "Goals updated."
        case "protocol":
            return "Protocol updated."
        case "mesocycle":
            return "Mesocycle updated."
        case "recipes":
            return "Recipes updated."
        case _:
            raise ValueError(
                f"render_write_confirm: unknown scope {scope!r}. "
                "Add a branch when introducing a new write scope."
            )
