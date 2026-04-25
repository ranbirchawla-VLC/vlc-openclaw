"""nutrios_read.py — read entrypoint for the v2 tool layer.

Invocation contract:
    python3.12 -m nutrios_read '<json_argv>'

JSON argv is a single sys.argv[1] string parsed into ReadInput. Output is one
JSON line on stdout — ToolResult.model_dump_json() — exit 0 on success.
True crashes (validation errors, file errors) propagate up and exit non-zero.

Tripwires honored:
    1. No orchestrator-prefix concatenation; ToolResult.display_text is rendered.
    2. JSONL files are read via tail_jsonl only — no direct file open.
    3. now and tz are inputs; never datetime.now() / date.today() in tool layer.
    4. Errors go through nutrios_render templates; no f-string error composition.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Tool layer imports its lib siblings via sys.path (matches test pattern;
# step 8 will replace with packaged invocation).
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nutrios_models import (
    ToolResult, FoodLogEntry, DoseLogEntry, LogEntryAdapter,
    WeighIn, MedNote, Event,
    Goals, Mesocycle, Protocol, Recipe,
)
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store


_VALID_SCOPES = (
    "log_today", "log_date",
    "weigh_ins", "med_notes",
    "events", "protocol", "goals",
    "mesocycle", "recipes",
)


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    scope: Literal[
        "log_today", "log_date",
        "weigh_ins", "med_notes",
        "events", "protocol", "goals",
        "mesocycle", "recipes",
    ]
    now: datetime
    tz: str
    target_date: date | None = None  # field for log_date scope; named target_date to avoid shadowing the date type
    n: int = 5
    query: str | None = None


# ---------------------------------------------------------------------------
# Per-scope helpers
# ---------------------------------------------------------------------------

def _local_today(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def _read_log_entries(uid: str, target_date: date) -> tuple[list[FoodLogEntry], list[DoseLogEntry]]:
    """Read the daily JSONL and partition by discriminator kind."""
    raw = store.read_jsonl_all(uid, f"log/{target_date}.jsonl")
    foods: list[FoodLogEntry] = []
    doses: list[DoseLogEntry] = []
    for row in raw:
        entry = LogEntryAdapter.validate_python(row)
        if isinstance(entry, FoodLogEntry):
            foods.append(entry)
        else:
            doses.append(entry)
    return foods, doses


def _all_weigh_ins(uid: str) -> list[WeighIn]:
    raw = store.read_jsonl_all(uid, "weigh_ins.jsonl")
    return [WeighIn.model_validate(r) for r in raw]


def _all_med_notes(uid: str) -> list[MedNote]:
    raw = store.read_jsonl_all(uid, "med_notes.jsonl")
    return [MedNote.model_validate(r) for r in raw]


# recipes are read through store.read_recipes (wrapped format)


# ---------------------------------------------------------------------------
# Daily summary composition (log_today / log_date)
# ---------------------------------------------------------------------------

def _read_daily(inp: ReadInput, target_date: date) -> ToolResult:
    """Compose the full daily summary for `target_date`."""
    uid = inp.user_id

    foods, today_doses = _read_log_entries(uid, target_date)

    goals = store.read_json(uid, "goals.json", Goals)
    if goals is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    mesocycle = store.read_json(uid, f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    if mesocycle is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    resolved = engine.resolve_day(inp.now, inp.tz, goals, mesocycle)

    protein_actual = sum(e.protein_g for e in foods)
    carbs_actual = sum(e.carbs_g for e in foods)
    fat_actual = sum(e.fat_g for e in foods)
    kcal_actual = int(round(sum(e.kcal for e in foods)))

    protein_status = engine.macro_range_check(protein_actual, resolved.protein_g)
    carbs_status = engine.macro_range_check(carbs_actual, resolved.carbs_g)
    fat_status = engine.macro_range_check(fat_actual, resolved.fat_g)

    protocol = store.read_json(uid, "protocol.json", Protocol)
    if protocol is not None:
        is_dose_day = engine.dose_reminder_due(protocol, today_doses, inp.now, inp.tz)
        dose_state = engine.dose_status(today_doses, is_dose_day=is_dose_day)
    else:
        dose_state = "not_due"

    weigh_ins = _all_weigh_ins(uid)
    weigh_in_today: WeighIn | None = None
    for w in weigh_ins:
        wi_date = datetime.fromisoformat(w.ts_iso.replace("Z", "+00:00")).astimezone(
            ZoneInfo(inp.tz)
        ).date()
        if wi_date == target_date:
            weigh_in_today = w  # last match wins (latest entry of the day)

    weigh_in_change = (
        engine.weight_change(weigh_ins, inp.now, since_days=7)
        if weigh_in_today is not None
        else None
    )

    events = store.read_events(uid)
    upcoming = engine.event_next(events, inp.now, inp.tz, n=2)
    advisory = (
        engine.advisory_flags(protocol, events, mesocycle, inp.now, inp.tz)
        if protocol is not None else []
    )

    text = render.render_daily_summary(
        resolved=resolved,
        meals=foods,
        dose_status=dose_state,
        upcoming_events=upcoming,
        advisory=advisory,
        weigh_in_today=weigh_in_today,
        weigh_in_change=weigh_in_change,
        protein_status=protein_status,
        carbs_status=carbs_status,
        fat_status=fat_status,
        protein_actual=protein_actual,
        carbs_actual=carbs_actual,
        fat_actual=fat_actual,
        kcal_actual=kcal_actual,
        now=inp.now,
        tz=inp.tz,
    )
    return ToolResult(
        display_text=text,
        state_delta={
            "date": str(target_date),
            "kcal_actual": kcal_actual,
            "kcal_target": resolved.kcal_target,
        },
    )


def _read_weigh_ins(inp: ReadInput) -> ToolResult:
    weigh_ins = _all_weigh_ins(inp.user_id)
    if not weigh_ins:
        return ToolResult(display_text="No weigh-ins yet.")
    rows = engine.weight_trend(weigh_ins, last_n=inp.n)
    change = engine.weight_change(weigh_ins, inp.now, since_days=7)
    rate = change.delta_lbs if change is not None else None
    return ToolResult(display_text=render.render_weight_trend(rows, rate))


def _read_med_notes(inp: ReadInput) -> ToolResult:
    notes = _all_med_notes(inp.user_id)
    recent = notes[-inp.n:] if notes else []
    return ToolResult(display_text=render.render_med_notes_list(recent))


def _read_events(inp: ReadInput) -> ToolResult:
    events = store.read_events(inp.user_id)
    upcoming = engine.event_next(events, inp.now, inp.tz, n=inp.n)
    return ToolResult(display_text=render.render_event_list(upcoming))


def _read_protocol(inp: ReadInput) -> ToolResult:
    protocol = store.read_json(inp.user_id, "protocol.json", Protocol)
    if protocol is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    notes = _all_med_notes(inp.user_id)
    recent = notes[-3:] if notes else []
    return ToolResult(display_text=render.render_protocol_view(protocol, recent))


def _read_goals(inp: ReadInput) -> ToolResult:
    goals = store.read_json(inp.user_id, "goals.json", Goals)
    if goals is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    mesocycle = store.read_json(inp.user_id, f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    if mesocycle is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    return ToolResult(display_text=render.render_goals_view(goals, mesocycle))


def _read_mesocycle(inp: ReadInput) -> ToolResult:
    goals = store.read_json(inp.user_id, "goals.json", Goals)
    if goals is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    mesocycle = store.read_json(inp.user_id, f"mesocycles/{goals.active_cycle_id}.json", Mesocycle)
    if mesocycle is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    return ToolResult(display_text=render.render_mesocycle_view(mesocycle))


def _read_recipes_scope(inp: ReadInput) -> ToolResult:
    recipes = store.read_recipes(inp.user_id)
    if inp.query:
        q = inp.query.lower()
        recipes = [r for r in recipes if q in r.name.lower()]
    return ToolResult(display_text=render.render_recipe_list(recipes))


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

def main(argv_json: str) -> ToolResult:
    """Parse the JSON argv, dispatch by scope, return ToolResult."""
    inp = ReadInput.model_validate_json(argv_json)

    match inp.scope:
        case "log_today":
            return _read_daily(inp, target_date=_local_today(inp.now, inp.tz))
        case "log_date":
            if inp.target_date is None:
                raise ValueError("log_date scope requires a 'target_date' field on input.")
            return _read_daily(inp, target_date=inp.target_date)
        case "weigh_ins":
            return _read_weigh_ins(inp)
        case "med_notes":
            return _read_med_notes(inp)
        case "events":
            return _read_events(inp)
        case "protocol":
            return _read_protocol(inp)
        case "goals":
            return _read_goals(inp)
        case "mesocycle":
            return _read_mesocycle(inp)
        case "recipes":
            return _read_recipes_scope(inp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_read '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
