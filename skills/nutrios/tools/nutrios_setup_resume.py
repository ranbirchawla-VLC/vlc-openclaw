"""nutrios_setup_resume.py — guided setup-resume marker walker (10/10).

The most architecturally significant tool of step 6+6.6. Walks markers in
the engine's fixed order, one at a time, through the standard turn contract.

Empty user_answer → surface the next marker prompt with context, set
needs_followup=True. Non-empty user_answer → validate per marker, route
the write, clear the marker, return either the next marker prompt or
render_setup_complete.

Per-marker dispatch:
    gallbladder      → nutrios_protocol_edit.apply_protocol_edit
                       (ungated for clinical.gallbladder_status)
    tdee             → direct mesocycle write (TDEE not protected)
    carbs_shape      → goals.json raw-write so _pending_kcal survives
    deficits         → goals.json write applying _pending_kcal-derived
                       deficits per day_pattern; _pending_kcal cleared
                       (raw write that strips scratch fields)
    nominal_deficit  → mesocycle.deficit_kcal direct write

_pending_kcal handling: phase-2 only scratch field on day_patterns. Lives
on raw goals.json across phase-2 turns; the deficits step consumes it
and clears it. Other phase-2 writes (carbs_shape) preserve it via the
raw-write path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from collections import Counter
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from nutrios_models import Goals, Mesocycle, Protocol, ToolResult
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store

import nutrios_protocol_edit


class SetupResumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    user_answer: str = ""
    now: datetime
    tz: str


# ---------------------------------------------------------------------------
# Context builders for render_setup_resume_prompt
# ---------------------------------------------------------------------------

def _build_context(uid: str, marker: str) -> dict:
    """Per-marker context dict consumed by render_setup_resume_prompt."""
    match marker:
        case "gallbladder" | "tdee":
            return {}

        case "carbs_shape":
            goals = _read_goals_phase2(uid)
            if goals is None:
                return {"day_patterns": []}
            patterns = []
            for dp in goals.day_patterns:
                if dp.carbs_g.min is not None:
                    patterns.append((dp.day_type, dp.carbs_g.min))
            return {"day_patterns": patterns}

        case "deficits":
            raw = store.read_json_raw(uid, "goals.json")
            if raw is None:
                return {"tdee": "?", "suggestions": []}
            goals = Goals.model_validate(_strip_pending(raw))
            mesocycle = store.read_json(
                uid, f"mesocycles/{goals.active_cycle_id}.json", Mesocycle,
            )
            tdee = mesocycle.tdee_kcal if mesocycle is not None else None
            suggestions = []
            for dp_raw in raw.get("day_patterns", []):
                v1_kcal = dp_raw.get("_pending_kcal")
                if v1_kcal is None:
                    continue
                if tdee is None:
                    suggestions.append((dp_raw["day_type"], "?", v1_kcal))
                else:
                    suggestions.append((dp_raw["day_type"], tdee - v1_kcal, v1_kcal))
            return {"tdee": tdee if tdee is not None else "?", "suggestions": suggestions}

        case "nominal_deficit":
            goals = _read_goals_phase2(uid)
            if goals is None:
                return {"deficits": [], "most_common": "?"}
            deficits = [
                (dp.day_type, dp.deficit_kcal)
                for dp in goals.day_patterns
                if dp.deficit_kcal is not None
            ]
            most_common = "?"
            if deficits:
                counter = Counter(d for _, d in deficits)
                most_common = counter.most_common(1)[0][0]
            return {"deficits": deficits, "most_common": most_common}

        case _:
            return {}


def _strip_pending(raw_goals: dict) -> dict:
    """Strip _pending_kcal from a raw goals dict so Goals.model_validate accepts it."""
    cleaned = dict(raw_goals)
    cleaned["day_patterns"] = [
        {k: v for k, v in dp.items() if k != "_pending_kcal"}
        for dp in raw_goals.get("day_patterns", [])
    ]
    return cleaned


def _read_goals_phase2(uid: str) -> Goals | None:
    """Read goals.json, stripping _pending_kcal scratch fields.

    Phase 2 setup_resume cannot use store.read_json(uid, "goals.json", Goals)
    directly: when _pending_kcal is present on a day_pattern, Pydantic's
    extra='forbid' rejects it. This wrapper does a raw read, strips the
    scratch fields, and validates a cleaned dict against Goals.
    """
    raw = store.read_json_raw(uid, "goals.json")
    if raw is None:
        return None
    return Goals.model_validate(_strip_pending(raw))


# ---------------------------------------------------------------------------
# Reprompt / completion helpers
# ---------------------------------------------------------------------------

def _reprompt(uid: str, marker: str) -> ToolResult:
    """User's answer was invalid — re-render the same marker prompt."""
    return ToolResult(
        display_text=render.render_setup_resume_prompt(marker, _build_context(uid, marker)),
        needs_followup=True,
        next_marker=marker,
    )


def _post_write_response(uid: str, just_cleared: str) -> ToolResult:
    """After a successful marker write, recompute status; either next prompt
    or setup-complete."""
    new_status = engine.setup_status(store.read_needs_setup(uid))
    if new_status.complete:
        return ToolResult(
            display_text=render.render_setup_complete(),
            marker_cleared=just_cleared,
            next_marker=None,
        )
    return ToolResult(
        display_text=render.render_setup_resume_prompt(
            new_status.next_marker, _build_context(uid, new_status.next_marker),
        ),
        needs_followup=True,
        marker_cleared=just_cleared,
        next_marker=new_status.next_marker,
    )


# ---------------------------------------------------------------------------
# Per-marker processors
# ---------------------------------------------------------------------------

_GALLBLADDER_VALUES = {"removed", "present", "unknown"}


def _process_gallbladder(inp: SetupResumeInput) -> ToolResult:
    answer = inp.user_answer.strip().lower()
    if answer not in _GALLBLADDER_VALUES:
        return _reprompt(inp.user_id, "gallbladder")

    protocol = store.read_json(inp.user_id, "protocol.json", Protocol)
    if protocol is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    proposed = protocol.model_copy(update={
        "clinical": protocol.clinical.model_copy(update={"gallbladder_status": answer})
    })
    edit_result = nutrios_protocol_edit.apply_protocol_edit(
        inp.user_id, proposed, confirm=None,
    )
    if edit_result.display_text != "Protocol updated.":
        # Gate failure (defensive — gallbladder is non-protected so this
        # branch shouldn't fire in practice). Surface the error verbatim.
        return edit_result

    store.clear_needs_setup_marker(inp.user_id, "gallbladder")
    return _post_write_response(inp.user_id, "gallbladder")


def _process_tdee(inp: SetupResumeInput) -> ToolResult:
    try:
        tdee = int(inp.user_answer.strip())
    except ValueError:
        return _reprompt(inp.user_id, "tdee")
    if not (1000 <= tdee <= 5000):
        return _reprompt(inp.user_id, "tdee")

    goals = _read_goals_phase2(inp.user_id)
    if goals is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    cycle_path = f"mesocycles/{goals.active_cycle_id}.json"
    mesocycle = store.read_json(inp.user_id, cycle_path, Mesocycle)
    if mesocycle is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    proposed = mesocycle.model_copy(update={"tdee_kcal": tdee})
    store.write_json(inp.user_id, cycle_path, proposed)
    store.clear_needs_setup_marker(inp.user_id, "tdee")
    return _post_write_response(inp.user_id, "tdee")


_CARBS_SHAPE_VALUES = {"yes", "max", "both"}


def _process_carbs_shape(inp: SetupResumeInput) -> ToolResult:
    answer = inp.user_answer.strip().lower()
    if answer not in _CARBS_SHAPE_VALUES:
        return _reprompt(inp.user_id, "carbs_shape")

    raw = store.read_json_raw(inp.user_id, "goals.json")
    if raw is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    # Mutate carbs in-place on the raw dict so _pending_kcal survives
    for dp in raw.get("day_patterns", []):
        carbs = dp.setdefault("carbs_g", {"min": None, "max": None, "protected": False})
        existing_min = carbs.get("min")
        match answer:
            case "yes":
                pass  # keep current min-only shape
            case "max":
                if existing_min is not None:
                    carbs["min"] = None
                    carbs["max"] = existing_min
            case "both":
                if existing_min is not None:
                    carbs["max"] = existing_min

    store.write_json_raw(inp.user_id, "goals.json", raw)
    store.clear_needs_setup_marker(inp.user_id, "carbs_shape")
    return _post_write_response(inp.user_id, "carbs_shape")


def _process_deficits(inp: SetupResumeInput) -> ToolResult:
    answer = inp.user_answer.strip().lower()
    if answer != "yes":
        # Phase 2 MVP only supports 'yes' to apply all suggested deficits.
        # Per-day-type adjustments (e.g. "rest 500") are out of scope; the
        # render template still mentions them so future expansions can wire
        # the parsing here without changing the prompt.
        return _reprompt(inp.user_id, "deficits")

    raw = store.read_json_raw(inp.user_id, "goals.json")
    if raw is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    goals = Goals.model_validate(_strip_pending(raw))
    mesocycle = store.read_json(
        inp.user_id, f"mesocycles/{goals.active_cycle_id}.json", Mesocycle,
    )
    if mesocycle is None or mesocycle.tdee_kcal is None:
        # Should not happen — tdee marker must clear first per engine ordering.
        return ToolResult(display_text=render.render_protocol_not_initialized())
    tdee = mesocycle.tdee_kcal

    new_patterns = []
    for dp_raw, dp_val in zip(raw.get("day_patterns", []), goals.day_patterns):
        v1_kcal = dp_raw.get("_pending_kcal")
        if v1_kcal is not None:
            new_patterns.append(dp_val.model_copy(update={"deficit_kcal": tdee - v1_kcal}))
        else:
            new_patterns.append(dp_val)

    proposed_goals = goals.model_copy(update={"day_patterns": new_patterns})
    # Validated write — _pending_kcal is dropped by Pydantic, intentionally
    store.write_json(inp.user_id, "goals.json", proposed_goals)
    store.clear_needs_setup_marker(inp.user_id, "deficits")
    return _post_write_response(inp.user_id, "deficits")


def _process_nominal_deficit(inp: SetupResumeInput) -> ToolResult:
    answer = inp.user_answer.strip().lower()
    nominal: int | None = None

    if answer == "yes":
        ctx = _build_context(inp.user_id, "nominal_deficit")
        most_common = ctx.get("most_common", "?")
        if isinstance(most_common, int):
            nominal = most_common
    else:
        try:
            nominal = int(answer)
        except ValueError:
            nominal = None

    if nominal is None or not (0 <= nominal <= 2000):
        return _reprompt(inp.user_id, "nominal_deficit")

    goals = _read_goals_phase2(inp.user_id)
    if goals is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    cycle_path = f"mesocycles/{goals.active_cycle_id}.json"
    mesocycle = store.read_json(inp.user_id, cycle_path, Mesocycle)
    if mesocycle is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    proposed = mesocycle.model_copy(update={"deficit_kcal": nominal})
    store.write_json(inp.user_id, cycle_path, proposed)
    store.clear_needs_setup_marker(inp.user_id, "nominal_deficit")
    return _post_write_response(inp.user_id, "nominal_deficit")


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

def main(argv_json: str) -> ToolResult:
    inp = SetupResumeInput.model_validate_json(argv_json)

    needs_setup = store.read_needs_setup(inp.user_id)
    status = engine.setup_status(needs_setup)

    if status.complete:
        return ToolResult(
            display_text=render.render_setup_complete(),
            marker_cleared=None,
            next_marker=None,
        )

    if not inp.user_answer.strip():
        # Surface the next marker prompt; no write yet
        return ToolResult(
            display_text=render.render_setup_resume_prompt(
                status.next_marker, _build_context(inp.user_id, status.next_marker),
            ),
            needs_followup=True,
            next_marker=status.next_marker,
        )

    match status.next_marker:
        case "gallbladder":
            return _process_gallbladder(inp)
        case "tdee":
            return _process_tdee(inp)
        case "carbs_shape":
            return _process_carbs_shape(inp)
        case "deficits":
            return _process_deficits(inp)
        case "nominal_deficit":
            return _process_nominal_deficit(inp)
        case _:
            # Unreachable under engine.setup_status's fixed marker order, but
            # the function's return type is ToolResult and __main__ calls
            # model_dump_json on the result. Fail loud if engine ever surfaces
            # an unknown marker — silent None would crash downstream.
            raise ValueError(
                f"setup_resume: unknown next_marker {status.next_marker!r} from engine"
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_setup_resume '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
