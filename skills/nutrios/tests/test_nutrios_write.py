"""Tests for nutrios_write — gate-before-write, atomic at the tool level."""
import json
from datetime import date

import pytest
from pydantic import ValidationError

from nutrios_models import (
    BiometricSnapshot, Clinical, DayMacros, DayPattern, Goals, MacroRange,
    Mesocycle, Protocol, Recipe, RecipeMacros, ToolResult, Treatment,
)
import nutrios_store as store
import nutrios_write as tool


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice"}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_write_rejects_unknown_scope(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(scope="bogus", payload={}))


def test_write_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(scope="goals", payload={}, bogus=1))


# ---------------------------------------------------------------------------
# goals — protected_gate_range walk
# ---------------------------------------------------------------------------

def _baseline_goals_payload(protein_min=175, fat_max=65) -> dict:
    """Goals payload matching the fixture user (protein/fat both protected)."""
    return Goals(
        active_cycle_id="cycle1",
        weekly_schedule={
            "monday": "rest", "tuesday": "training", "wednesday": "rest",
            "thursday": "training", "friday": "rest", "saturday": "training",
            "sunday": "rest",
        },
        defaults=DayMacros(
            protein_g=MacroRange(min=protein_min, protected=True),
            fat_g=MacroRange(max=fat_max, protected=True),
        ),
        day_patterns=[
            DayPattern(day_type="rest", carbs_g=MacroRange(min=180)),
            DayPattern(day_type="training", carbs_g=MacroRange(min=220)),
        ],
    ).model_dump(mode="json")


def test_write_goals_no_change_succeeds_without_confirm(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="goals", payload=_baseline_goals_payload()))
    assert isinstance(result, ToolResult)
    assert result.display_text == "Goals updated."


def test_write_goals_unprotected_change_succeeds_without_confirm(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_goals_payload()
    # Carbs is not protected; bumping its min must pass without confirm
    for dp in payload["day_patterns"]:
        if dp["day_type"] == "rest":
            dp["carbs_g"]["min"] = 200
    result = tool.main(_argv(scope="goals", payload=payload))
    assert result.display_text == "Goals updated."

    # Verify on disk
    written = store.read_json("alice", "goals.json", Goals)
    assert written is not None
    rest_pattern = next(dp for dp in written.day_patterns if dp.day_type == "rest")
    assert rest_pattern.carbs_g.min == 200


def test_write_goals_protected_change_without_confirm_rejected(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_goals_payload()
    # Bump protein min on a PROTECTED range with no confirm → must be rejected
    payload["defaults"]["protein_g"]["min"] = 200
    result = tool.main(_argv(scope="goals", payload=payload))
    assert "Protected" in result.display_text or "protect" in result.display_text.lower()

    # Disk state must be unchanged
    on_disk = store.read_json("alice", "goals.json", Goals)
    assert on_disk.defaults.protein_g.min == 175  # original


def test_write_goals_protected_change_with_confirm_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_goals_payload()
    payload["defaults"]["protein_g"]["min"] = 200
    result = tool.main(_argv(
        scope="goals",
        payload=payload,
        confirm="confirm macro range change",
    ))
    assert result.display_text == "Goals updated."

    on_disk = store.read_json("alice", "goals.json", Goals)
    assert on_disk.defaults.protein_g.min == 200


def test_write_goals_first_time_write_no_gate(tmp_data_root):
    """Without an existing goals.json, no gate runs (no current state to compare)."""
    payload = _baseline_goals_payload()
    payload["defaults"]["protein_g"]["min"] = 200
    result = tool.main(_argv(scope="goals", payload=payload))
    assert result.display_text == "Goals updated."


# ---------------------------------------------------------------------------
# protocol — protected_gate_protocol
# ---------------------------------------------------------------------------

def _baseline_protocol_payload(dose_mg=10.0) -> dict:
    return Protocol(
        user_id="alice",
        treatment=Treatment(
            medication="Tirzepatide", brand="Mounjaro",
            dose_mg=dose_mg, dose_day_of_week="thursday", dose_time="07:00",
        ),
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1), start_weight_lbs=220.0, target_weight_lbs=180.0,
        ),
        clinical=Clinical(gallbladder_status="present"),
    ).model_dump(mode="json")


def test_write_protocol_unprotected_change_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_protocol_payload()
    payload["clinical"]["gallbladder_status"] = "removed"  # not protected
    result = tool.main(_argv(scope="protocol", payload=payload))
    assert result.display_text == "Protocol updated."

    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.clinical.gallbladder_status == "removed"


def test_write_protocol_dose_mg_change_without_confirm_rejected(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_protocol_payload(dose_mg=12.5)
    result = tool.main(_argv(scope="protocol", payload=payload))
    assert "Protected" in result.display_text or "protect" in result.display_text.lower()

    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.treatment.dose_mg == 10.0  # unchanged


def test_write_protocol_dose_mg_change_with_confirm_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    payload = _baseline_protocol_payload(dose_mg=12.5)
    result = tool.main(_argv(
        scope="protocol", payload=payload, confirm="confirm protocol change",
    ))
    assert result.display_text == "Protocol updated."
    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.treatment.dose_mg == 12.5


# ---------------------------------------------------------------------------
# mesocycle — no gate
# ---------------------------------------------------------------------------

def test_write_mesocycle_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    payload = Mesocycle(
        cycle_id="cycle1", phase="lean_bulk",
        start_date=date(2026, 5, 1), tdee_kcal=2800, deficit_kcal=0,
    ).model_dump(mode="json")
    result = tool.main(_argv(scope="mesocycle", payload=payload))
    assert result.display_text == "Mesocycle updated."

    on_disk = store.read_json("alice", "mesocycles/cycle1.json", Mesocycle)
    assert on_disk.tdee_kcal == 2800
    assert on_disk.phase == "lean_bulk"


def test_write_mesocycle_new_cycle_id(tmp_data_root, setup_user):
    """Writing a different cycle_id creates a new mesocycle file."""
    setup_user("alice")
    payload = Mesocycle(
        cycle_id="cycle2", phase="recomp",
        start_date=date(2026, 6, 1), tdee_kcal=2700, deficit_kcal=200,
    ).model_dump(mode="json")
    tool.main(_argv(scope="mesocycle", payload=payload))
    on_disk = store.read_json("alice", "mesocycles/cycle2.json", Mesocycle)
    assert on_disk is not None
    # cycle1 must still exist
    assert store.read_json("alice", "mesocycles/cycle1.json", Mesocycle) is not None


# ---------------------------------------------------------------------------
# recipes — bulk replace
# ---------------------------------------------------------------------------

def test_write_recipes_bulk_replace(tmp_data_root, setup_user):
    setup_user("alice")
    recipes = [
        Recipe(id=1, name="shake", servings=1,
               macros_per_serving=RecipeMacros(kcal=400, protein_g=30.0, carbs_g=40.0, fat_g=12.0)),
        Recipe(id=2, name="oats", servings=1,
               macros_per_serving=RecipeMacros(kcal=350, protein_g=12.0, carbs_g=60.0, fat_g=6.0)),
    ]
    payload = {"recipes": [r.model_dump(mode="json") for r in recipes]}
    result = tool.main(_argv(scope="recipes", payload=payload))
    assert result.display_text == "Recipes updated."

    on_disk = store.read_recipes("alice")
    assert len(on_disk) == 2
    assert {r.name for r in on_disk} == {"shake", "oats"}


def test_write_recipes_payload_missing_recipes_key_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="recipes"):
        tool.main(_argv(scope="recipes", payload={"bogus": 1}))


# ---------------------------------------------------------------------------
# Atomicity — gate rejection produces zero disk mutation
# ---------------------------------------------------------------------------

def test_write_goals_protected_rejection_leaves_disk_untouched(tmp_data_root, setup_user):
    setup_user("alice")
    original = store.read_json("alice", "goals.json", Goals)

    # Multi-change payload: bump protein min (protected) AND carbs min (not protected)
    payload = _baseline_goals_payload()
    payload["defaults"]["protein_g"]["min"] = 200
    for dp in payload["day_patterns"]:
        if dp["day_type"] == "rest":
            dp["carbs_g"]["min"] = 199

    result = tool.main(_argv(scope="goals", payload=payload))
    assert "Protected" in result.display_text or "protect" in result.display_text.lower()

    # Both changes blocked; disk unchanged
    on_disk = store.read_json("alice", "goals.json", Goals)
    assert on_disk.defaults.protein_g.min == 175
    rest_pattern = next(dp for dp in on_disk.day_patterns if dp.day_type == "rest")
    assert rest_pattern.carbs_g.min == 180  # original


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_write_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    payload = _baseline_goals_payload()
    for dp in payload["day_patterns"]:
        if dp["day_type"] == "rest":
            dp["carbs_g"]["min"] = 999

    tool.main(_argv(scope="goals", payload=payload))

    # Alice's write must not touch Bob's tree
    bob_goals = store.read_json("bob", "goals.json", Goals)
    bob_rest = next(dp for dp in bob_goals.day_patterns if dp.day_type == "rest")
    assert bob_rest.carbs_g.min == 180
