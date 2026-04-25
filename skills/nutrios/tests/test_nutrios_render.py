"""Tests for nutrios_render — exact string assertions, one per branch.

All functions produce str. Empty string for suppression, never None.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import date, datetime, timezone

from nutrios_models import (
    MacroRange, DayMacros, DayPattern, Goals, Mesocycle, ResolvedDay,
    Protocol, Treatment, BiometricSnapshot, Clinical,
    WeighIn, WeighInRow, WeightChange,
    MedNote, Event, FoodLogEntry, DoseLogEntry,
    GateResult, Flag,
)
import nutrios_render as render


# ---------------------------------------------------------------------------
# render_macro_line — four branches + suppression
# ---------------------------------------------------------------------------

def test_render_macro_line_min_only_low():
    r = MacroRange(min=175)
    assert render.render_macro_line("Protein", 148, r, "LOW") == "Protein:   148g / min 175g   LOW"

def test_render_macro_line_min_only_ok():
    r = MacroRange(min=175)
    assert render.render_macro_line("Protein", 200, r, "OK") == "Protein:   200g / min 175g    OK"

def test_render_macro_line_max_only_ok():
    r = MacroRange(max=65)
    assert render.render_macro_line("Fat", 42, r, "OK") == "Fat:        42g / max 65g     OK"

def test_render_macro_line_max_only_over():
    r = MacroRange(max=65)
    assert render.render_macro_line("Fat", 70, r, "OVER") == "Fat:        70g / max 65g   OVER"

def test_render_macro_line_both_set_ok():
    r = MacroRange(min=150, max=200)
    assert render.render_macro_line("Carbs", 180, r, "OK") == "Carbs:     180g / 150–200g    OK"

def test_render_macro_line_both_set_low():
    r = MacroRange(min=150, max=200)
    assert render.render_macro_line("Carbs", 100, r, "LOW") == "Carbs:     100g / 150–200g   LOW"

def test_render_macro_line_unset_returns_empty():
    r = MacroRange()
    assert render.render_macro_line("Carbs", 180, r, "UNSET") == ""


# ---------------------------------------------------------------------------
# render_kcal_line — three branches
# ---------------------------------------------------------------------------

def test_render_kcal_line_setup_needed():
    assert render.render_kcal_line(0, None, None, 0) == "Calories: setup needed"

def test_render_kcal_line_with_derivation():
    result = render.render_kcal_line(1840, 2000, 2600, 600)
    assert result == "Calories: 1840 / 2000   (TDEE 2600 − 600)"

def test_render_kcal_line_terse_no_tdee():
    result = render.render_kcal_line(1840, 2000, None, 0)
    assert result == "Calories: 1840 / 2000"


# ---------------------------------------------------------------------------
# render_weigh_in_confirm
# ---------------------------------------------------------------------------

def _wi(weight: float = 218.5, id: int = 1) -> WeighIn:
    return WeighIn(id=id, ts_iso="2026-04-24T12:00:00Z", weight_lbs=weight)

def _wc(delta: float = -1.5, current: float = 218.5, prior: float = 220.0) -> WeightChange:
    return WeightChange(since_days=7, delta_lbs=delta, current_lbs=current, prior_lbs=prior)

def test_render_weigh_in_confirm_with_change_and_progress():
    result = render.render_weigh_in_confirm(
        _wi(218.5),
        _wc(-1.5, 218.5, 220.0),
        {"target_lbs": 195.0, "pct_to_goal": 40.0},
    )
    assert "218.5 lbs" in result
    assert "−1.5" in result or "-1.5" in result
    assert "195.0" in result

def test_render_weigh_in_confirm_no_change():
    result = render.render_weigh_in_confirm(_wi(218.5), None, None)
    assert "218.5 lbs" in result
    # No delta line when change is None
    assert "lbs / 7d" not in result

def test_render_weigh_in_confirm_no_progress():
    result = render.render_weigh_in_confirm(_wi(218.5), _wc(-1.5, 218.5, 220.0), None)
    assert "218.5 lbs" in result
    assert "195" not in result


# ---------------------------------------------------------------------------
# render_weight_trend
# ---------------------------------------------------------------------------

def _rows() -> list[WeighInRow]:
    return [
        WeighInRow(date=date(2026, 4, 18), weight_lbs=220.0),
        WeighInRow(date=date(2026, 4, 21), weight_lbs=219.0),
        WeighInRow(date=date(2026, 4, 24), weight_lbs=218.5),
    ]

def test_render_weight_trend_with_rate():
    result = render.render_weight_trend(_rows(), -0.5)
    assert "Weight trend" in result
    assert "220.0" in result
    assert "218.5" in result
    assert "-0.5" in result or "−0.5" in result

def test_render_weight_trend_no_rate():
    result = render.render_weight_trend(_rows(), None)
    assert "Weight trend" in result
    assert "rate" not in result.lower()


# ---------------------------------------------------------------------------
# render_dose_confirm / render_dose_not_due
# ---------------------------------------------------------------------------

def _dose_entry() -> DoseLogEntry:
    return DoseLogEntry(id=1, ts_iso="2026-04-24T08:00:00Z", dose_mg=112.5, brand="Synthroid")

def test_render_dose_confirm():
    result = render.render_dose_confirm(_dose_entry())
    assert "112.5" in result
    assert "Synthroid" in result

def test_render_dose_not_due():
    result = render.render_dose_not_due("friday", date(2026, 4, 25))
    assert "friday" in result.lower() or "Friday" in result
    assert "2026-04-25" in result


# ---------------------------------------------------------------------------
# render_med_note_confirm
# ---------------------------------------------------------------------------

def _note() -> MedNote:
    return MedNote(id=1, ts_iso="2026-04-24T12:00:00Z", note="Felt tired after dose.", source="self")

def test_render_med_note_confirm():
    result = render.render_med_note_confirm(_note())
    assert "Felt tired after dose." in result


# ---------------------------------------------------------------------------
# render_protocol_view
# ---------------------------------------------------------------------------

def _protocol() -> Protocol:
    return Protocol(
        user_id="alice",
        treatment=Treatment(
            medication="Levothyroxine",
            brand="Synthroid",
            dose_mg=112.5,
            dose_day_of_week="friday",
            dose_time="08:00",
            titration_notes="Increase to 125 next month",
        ),
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1),
            start_weight_lbs=230.0,
            target_weight_lbs=195.0,
        ),
        clinical=Clinical(gallbladder_status="removed"),
    )

def test_render_protocol_view():
    result = render.render_protocol_view(_protocol(), [_note()])
    assert "Levothyroxine" in result
    assert "Synthroid" in result
    assert "112.5" in result
    assert "friday" in result.lower() or "Friday" in result
    assert "230.0" in result
    assert "195.0" in result
    assert "removed" in result
    assert "Felt tired after dose." in result

def test_render_protocol_view_no_notes():
    result = render.render_protocol_view(_protocol(), [])
    assert "Levothyroxine" in result


# ---------------------------------------------------------------------------
# render_event_added / render_event_trigger
# ---------------------------------------------------------------------------

def _event(event_type: str = "surgery") -> Event:
    return Event(id=1, date=date(2026, 5, 15), title="Surgery consultation", event_type=event_type)

def test_render_event_added():
    result = render.render_event_added(_event())
    assert "Surgery consultation" in result
    assert "2026-05-15" in result

def test_render_event_trigger():
    result = render.render_event_trigger(_event("appointment"))
    assert "Surgery consultation" in result


# ---------------------------------------------------------------------------
# render_advisory — empty and populated
# ---------------------------------------------------------------------------

def test_render_advisory_empty():
    assert render.render_advisory([]) == ""

def test_render_advisory_single_warn():
    flags = [Flag(code="surgery_window", severity="warn", message="Surgery scheduled within 7 days.")]
    result = render.render_advisory(flags)
    assert "[warn]" in result
    assert "Surgery scheduled within 7 days." in result

def test_render_advisory_multiple():
    flags = [
        Flag(code="surgery_window", severity="warn", message="Surgery scheduled within 7 days."),
        Flag(code="range_proximity", severity="info", message="Fat approaching ceiling."),
    ]
    result = render.render_advisory(flags)
    assert "[warn]" in result
    assert "[info]" in result


# ---------------------------------------------------------------------------
# render_gate_error — Tripwire 4: every reason code has a template branch
# ---------------------------------------------------------------------------

def test_render_gate_error_known_code():
    result = GateResult(ok=False, reason="protected_field_change_requires_confirm_phrase", applied=False)
    out = render.render_gate_error(result)
    assert "confirm" in out.lower()
    # Must not be a raw reason code
    assert "protected_field_change_requires_confirm_phrase" not in out

def test_render_gate_error_unknown_code_raises():
    result = GateResult(ok=False, reason="invented_code_not_in_spec", applied=False)
    with pytest.raises(ValueError, match="invented_code_not_in_spec"):
        render.render_gate_error(result)

def test_render_gate_error_ok_result_returns_empty():
    result = GateResult(ok=True, reason=None, applied=True)
    assert render.render_gate_error(result) == ""

def test_render_gate_error_raises_on_none_reason():
    result = GateResult(ok=False, reason=None, applied=False)
    with pytest.raises(ValueError, match="reason is None"):
        render.render_gate_error(result)

def test_render_gate_error_raises_on_unknown_reason():
    result = GateResult(ok=False, reason="bogus_code", applied=False)
    with pytest.raises(ValueError, match="bogus_code"):
        render.render_gate_error(result)


# ---------------------------------------------------------------------------
# render_setup_resume_prompt — one test per marker + unknown raises
# ---------------------------------------------------------------------------

def test_render_setup_gallbladder():
    result = render.render_setup_resume_prompt("gallbladder", {})
    assert "gallbladder" in result.lower()
    assert "removed" in result.lower()

def test_render_setup_tdee():
    result = render.render_setup_resume_prompt("tdee", {})
    assert "TDEE" in result or "tdee" in result.lower()

def test_render_setup_carbs_shape():
    ctx = {"day_patterns": [("Training", 220), ("Rest", 180)]}
    result = render.render_setup_resume_prompt("carbs_shape", ctx)
    assert "220" in result
    assert "180" in result

def test_render_setup_deficits():
    ctx = {
        "tdee": 2600,
        "suggestions": [("Rest", 600, 2000), ("Training", 200, 2400)],
    }
    result = render.render_setup_resume_prompt("deficits", ctx)
    assert "2600" in result
    assert "600" in result

def test_render_setup_nominal_deficit():
    ctx = {"deficits": [("Rest", 600), ("Training", 200)], "most_common": 600}
    result = render.render_setup_resume_prompt("nominal_deficit", ctx)
    assert "600" in result

def test_render_setup_unknown_marker_raises():
    with pytest.raises(ValueError, match="unknown_marker"):
        render.render_setup_resume_prompt("unknown_marker", {})


# ---------------------------------------------------------------------------
# render_setup_complete
# ---------------------------------------------------------------------------

def test_render_setup_complete():
    result = render.render_setup_complete()
    assert isinstance(result, str)
    assert len(result) > 0
    assert "setup" in result.lower() or "complete" in result.lower()


# ---------------------------------------------------------------------------
# render_daily_summary — structure and weigh-in tests
# ---------------------------------------------------------------------------

def _resolved() -> ResolvedDay:
    return ResolvedDay(
        day_type="rest",
        kcal_target=2200,
        protein_g=MacroRange(min=175),
        carbs_g=MacroRange(min=150, max=220),
        fat_g=MacroRange(max=65),
        tdee_kcal=2600,
        deficit_kcal=400,
    )

def _resolved_unset() -> ResolvedDay:
    return ResolvedDay(
        day_type="rest",
        kcal_target=None,
        protein_g=MacroRange(),
        carbs_g=MacroRange(),
        fat_g=MacroRange(),
        tdee_kcal=None,
        deficit_kcal=0,
    )

def _food_entry(slot: str = "lunch", name: str = "Chicken breast", kcal: int = 250,
                protein: float = 46.5, carbs: float = 0.0, fat: float = 5.4) -> FoodLogEntry:
    return FoodLogEntry(
        id=1, ts_iso="2026-04-24T12:00:00Z",
        meal_slot=slot, source="manual",
        name=name, qty=150.0, unit="g",
        kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat,
    )

_NOW = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)

def test_render_daily_summary_basic():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[_food_entry()],
        dose_status="pending",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=None,
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=46.5,
        carbs_actual=0.0,
        fat_actual=5.4,
        kcal_actual=250,
        now=_NOW,
        tz="UTC",
    )
    assert "rest" in result.lower() or "Rest" in result
    assert "Calories" in result
    assert "Protein" in result
    assert "Chicken breast" in result
    assert not result.endswith("\n")

def test_render_daily_summary_advisory_first():
    flags = [Flag(code="surgery_window", severity="warn", message="Surgery scheduled within 7 days.")]
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=flags,
        weigh_in_today=None,
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    adv_pos = result.find("[warn]")
    date_pos = result.find("Apr")
    assert adv_pos < date_pos

def test_render_daily_summary_no_trailing_newline():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=None,
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    assert not result.endswith("\n")

def test_render_daily_summary_all_unset_suppresses_macro_lines():
    result = render.render_daily_summary(
        resolved=_resolved_unset(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=None,
        weigh_in_change=None,
        protein_status="UNSET",
        carbs_status="UNSET",
        fat_status="UNSET",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    assert "Protein" not in result
    assert "Carbs" not in result
    assert "Fat" not in result

def test_render_daily_summary_weigh_in_with_delta():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=_wi(184.2),
        weigh_in_change=_wc(-0.3, 184.2, 184.5),
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    assert "Weighed in: 184.2 lbs" in result
    assert "0.3" in result
    assert "from last" in result

def test_render_daily_summary_weigh_in_no_delta():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=_wi(184.2),
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    assert "Weighed in: 184.2 lbs" in result
    assert "from last" not in result

def test_render_daily_summary_no_weigh_in():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=None,
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    assert "Weighed in" not in result

def test_render_daily_summary_weigh_in_position():
    result = render.render_daily_summary(
        resolved=_resolved(),
        meals=[],
        dose_status="not_due",
        upcoming_events=[],
        advisory=[],
        weigh_in_today=_wi(184.2),
        weigh_in_change=None,
        protein_status="LOW",
        carbs_status="LOW",
        fat_status="OK",
        protein_actual=0.0,
        carbs_actual=0.0,
        fat_actual=0.0,
        kcal_actual=0,
        now=_NOW,
        tz="UTC",
    )
    date_pos = result.find("Apr")
    weigh_pos = result.find("Weighed in")
    calories_pos = result.find("Calories")
    assert date_pos < weigh_pos < calories_pos
