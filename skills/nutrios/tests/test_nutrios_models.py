"""Tests for nutrios_models — Pydantic schema verification only.

TDD: models file doesn't exist yet when these are first run.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import date
from pydantic import ValidationError

import nutrios_models as m


# ---------------------------------------------------------------------------
# MacroRange
# ---------------------------------------------------------------------------

def test_macrorange_all_null():
    r = m.MacroRange()
    assert r.min is None
    assert r.max is None
    assert r.protected is False

def test_macrorange_min_only():
    r = m.MacroRange(min=175)
    assert r.min == 175
    assert r.max is None

def test_macrorange_max_only():
    r = m.MacroRange(max=65)
    assert r.max == 65
    assert r.min is None

def test_macrorange_both_ends():
    r = m.MacroRange(min=175, max=200)
    assert r.min == 175
    assert r.max == 200

def test_macrorange_rejects_unknown_field():
    with pytest.raises(ValidationError):
        m.MacroRange(bogus=1)


# ---------------------------------------------------------------------------
# Mesocycle — Tripwire 7: tdee_kcal may be None
# ---------------------------------------------------------------------------

def test_mesocycle_with_null_tdee():
    cyc = m.Mesocycle(cycle_id="cyc1", phase="cut", start_date=date(2026, 1, 1))
    assert cyc.tdee_kcal is None

def test_mesocycle_with_tdee_set():
    cyc = m.Mesocycle(cycle_id="cyc2", phase="lean_bulk", start_date=date(2026, 1, 1), tdee_kcal=2600)
    assert cyc.tdee_kcal == 2600

def test_mesocycle_rejects_unknown_phase():
    with pytest.raises(ValidationError):
        m.Mesocycle(cycle_id="x", phase="super_cut", start_date=date(2026, 1, 1))


# ---------------------------------------------------------------------------
# DayPattern — Tripwire 5: _pending_kcal must NOT be accepted
# ---------------------------------------------------------------------------

def test_daypattern_rejects_pending_kcal():
    with pytest.raises(ValidationError):
        m.DayPattern(day_type="rest", _pending_kcal=2000)

def test_daypattern_valid_minimal():
    dp = m.DayPattern(day_type="training")
    assert dp.day_type == "training"
    assert dp.deficit_kcal is None

def test_daypattern_with_deficit():
    dp = m.DayPattern(day_type="rest", deficit_kcal=600)
    assert dp.deficit_kcal == 600


# ---------------------------------------------------------------------------
# LogEntry discriminated union
# ---------------------------------------------------------------------------

def test_logentry_food_discriminator():
    from pydantic import TypeAdapter
    adapter = m.LogEntryAdapter
    entry = adapter.validate_python({
        "kind": "food",
        "id": 1,
        "ts_iso": "2026-04-24T12:00:00Z",
        "meal_slot": "lunch",
        "source": "manual",
        "name": "chicken breast",
        "qty": 150.0,
        "unit": "g",
        "kcal": 248,
        "protein_g": 46.5,
        "carbs_g": 0.0,
        "fat_g": 5.4,
    })
    assert isinstance(entry, m.FoodLogEntry)

def test_logentry_dose_discriminator():
    from pydantic import TypeAdapter
    adapter = m.LogEntryAdapter
    entry = adapter.validate_python({
        "kind": "dose",
        "id": 2,
        "ts_iso": "2026-04-24T08:00:00Z",
        "dose_mg": 112.5,
        "brand": "Synthroid",
    })
    assert isinstance(entry, m.DoseLogEntry)

def test_logentry_invalid_kind():
    from pydantic import TypeAdapter
    adapter = m.LogEntryAdapter
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "water", "id": 3})


# ---------------------------------------------------------------------------
# GateResult, SetupStatus, Flag, Proximity, WeightChange, WeighInRow
# ---------------------------------------------------------------------------

def test_gate_result_fields():
    gr = m.GateResult(ok=True, reason=None, applied=True)
    assert gr.ok is True
    assert gr.applied is True

def test_setup_status_fields():
    ss = m.SetupStatus(complete=False, next_marker="tdee", markers_remaining=["tdee", "carbs_shape"])
    assert ss.next_marker == "tdee"

def test_flag_severities():
    f = m.Flag(code="surgery_window", severity="warn", message="Surgery within 7 days.")
    assert f.severity == "warn"
    with pytest.raises(ValidationError):
        m.Flag(code="x", severity="critical", message="bad")

def test_proximity_fields():
    p = m.Proximity(macro="fat_g", end="max", distance_g=4.5)
    assert p.end == "max"

def test_weight_change_fields():
    wc = m.WeightChange(since_days=7, delta_lbs=-1.5, current_lbs=218.0, prior_lbs=219.5)
    assert wc.delta_lbs == -1.5

def test_weigh_in_row_fields():
    wr = m.WeighInRow(date=date(2026, 4, 24), weight_lbs=218.0)
    assert wr.weight_lbs == 218.0


# ---------------------------------------------------------------------------
# NeedsSetup — all fields default False
# ---------------------------------------------------------------------------

def test_needs_setup_defaults_all_false():
    ns = m.NeedsSetup()
    assert ns.gallbladder is False
    assert ns.tdee is False
    assert ns.carbs_shape is False
    assert ns.deficits is False
    assert ns.nominal_deficit is False


# ---------------------------------------------------------------------------
# Recipe + RecipeMacros — required per-serving macros, removed flag
# ---------------------------------------------------------------------------

def _macros() -> "m.RecipeMacros":
    return m.RecipeMacros(kcal=500, protein_g=40.0, carbs_g=50.0, fat_g=15.0)


def test_recipe_macros_all_fields_required():
    macros = m.RecipeMacros(kcal=300, protein_g=25.0, carbs_g=30.0, fat_g=8.0)
    assert macros.kcal == 300
    assert macros.fat_g == 8.0


def test_recipe_macros_rejects_unknown_field():
    with pytest.raises(ValidationError):
        m.RecipeMacros(kcal=300, protein_g=20, carbs_g=40, fat_g=10, fiber_g=5)


def test_recipe_macros_rejects_missing_field():
    with pytest.raises(ValidationError):
        m.RecipeMacros(kcal=300, protein_g=25.0, carbs_g=30.0)  # missing fat_g


def test_recipe_minimal_valid():
    r = m.Recipe(id=1, name="protein shake", servings=1, macros_per_serving=_macros())
    assert r.id == 1
    assert r.name == "protein shake"
    assert r.removed is False  # default
    assert r.ingredients == []  # default


def test_recipe_with_ingredients():
    r = m.Recipe(
        id=2, name="oats and berries", servings=1,
        macros_per_serving=_macros(),
        ingredients=["50g rolled oats", "100g blueberries", "200ml milk"],
    )
    assert len(r.ingredients) == 3


def test_recipe_macros_per_serving_required():
    with pytest.raises(ValidationError):
        m.Recipe(id=3, name="x", servings=1)  # missing macros_per_serving


def test_recipe_removed_flag_settable():
    r = m.Recipe(id=4, name="old recipe", servings=1, macros_per_serving=_macros(), removed=True)
    assert r.removed is True


def test_recipe_rejects_unknown_field():
    with pytest.raises(ValidationError):
        m.Recipe(id=5, name="x", servings=1, macros_per_serving=_macros(), bogus=1)


# ---------------------------------------------------------------------------
# Event.removed — soft-delete semantics
# ---------------------------------------------------------------------------

def test_event_removed_defaults_false():
    e = m.Event(id=1, date=date(2026, 5, 1), title="surgery", event_type="surgery")
    assert e.removed is False


def test_event_removed_settable():
    e = m.Event(
        id=2, date=date(2026, 5, 1), title="cancelled appt",
        event_type="appointment", removed=True,
    )
    assert e.removed is True


# ---------------------------------------------------------------------------
# State.last_recipe_id — new counter, backward-compat default
# ---------------------------------------------------------------------------

def test_state_default_includes_last_recipe_id():
    s = m.State()
    assert s.last_recipe_id == 0


def test_state_backward_compat_missing_last_recipe_id():
    """Old state.json files without last_recipe_id still parse; default to 0."""
    legacy_json = '{"last_entry_id": 5, "last_weigh_in_id": 2, "last_med_note_id": 1, "last_event_id": 0}'
    s = m.State.model_validate_json(legacy_json)
    assert s.last_entry_id == 5
    assert s.last_recipe_id == 0  # defaulted


def test_state_with_last_recipe_id_set():
    s = m.State(last_recipe_id=3)
    assert s.last_recipe_id == 3


# ---------------------------------------------------------------------------
# ToolResult — single output contract for all v2 tools
# ---------------------------------------------------------------------------

def test_tool_result_minimal():
    r = m.ToolResult(display_text="Logged.")
    assert r.display_text == "Logged."
    assert r.needs_followup is False
    assert r.state_delta is None
    assert r.marker_cleared is None
    assert r.next_marker is None


def test_tool_result_with_followup():
    r = m.ToolResult(
        display_text="What quantity?",
        needs_followup=True,
        state_delta={"awaiting": "qty"},
    )
    assert r.needs_followup is True
    assert r.state_delta == {"awaiting": "qty"}


def test_tool_result_setup_resume_fields():
    r = m.ToolResult(
        display_text="Got it. Next: TDEE.",
        marker_cleared="gallbladder",
        next_marker="tdee",
    )
    assert r.marker_cleared == "gallbladder"
    assert r.next_marker == "tdee"


def test_tool_result_rejects_unknown_field():
    with pytest.raises(ValidationError):
        m.ToolResult(display_text="x", bogus=1)


def test_tool_result_serializable_roundtrip():
    """Tools serialize via model_dump_json; assert roundtrip stability."""
    r = m.ToolResult(
        display_text="ok",
        needs_followup=False,
        state_delta={"k": 1},
        marker_cleared=None,
        next_marker=None,
    )
    parsed = m.ToolResult.model_validate_json(r.model_dump_json())
    assert parsed == r
