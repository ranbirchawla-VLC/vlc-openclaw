"""Tests for nutrios_engine — TDD, built function by function.

Engine is pure: no I/O, no datetime.now() calls, time always passed as param.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pytest
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import nutrios_engine as engine
from nutrios_models import (
    MacroRange, DayMacros, DayPattern, Goals, Mesocycle, ResolvedDay,
    Protocol, Treatment, BiometricSnapshot, Clinical,
    WeighIn, Event, NeedsSetup,
    FoodLogEntry, DoseLogEntry,
    GateResult, SetupStatus, Flag,
)


# ---------------------------------------------------------------------------
# merge_range()
# ---------------------------------------------------------------------------

def test_merge_range_null_override_returns_default():
    default = MacroRange(min=175)
    result = engine.merge_range(default, None)
    assert result.min == 175
    assert result.max is None

def test_merge_range_both_null_override_returns_default():
    default = MacroRange(min=175)
    override = MacroRange()  # both ends null
    result = engine.merge_range(default, override)
    assert result.min == 175
    assert result.max is None

def test_merge_range_override_max_only():
    default = MacroRange(min=175)
    override = MacroRange(max=200)
    result = engine.merge_range(default, override)
    assert result.min == 175  # inherited
    assert result.max == 200  # from override

def test_merge_range_override_both_ends():
    default = MacroRange(min=150, max=250)
    override = MacroRange(min=180, max=220)
    result = engine.merge_range(default, override)
    assert result.min == 180
    assert result.max == 220


# ---------------------------------------------------------------------------
# macro_range_check()
# ---------------------------------------------------------------------------

def test_macro_range_check_unset():
    assert engine.macro_range_check(180, MacroRange()) == "UNSET"

def test_macro_range_check_low():
    assert engine.macro_range_check(174, MacroRange(min=175)) == "LOW"

def test_macro_range_check_ok_at_min_boundary():
    assert engine.macro_range_check(175, MacroRange(min=175)) == "OK"

def test_macro_range_check_over():
    assert engine.macro_range_check(66, MacroRange(max=65)) == "OVER"

def test_macro_range_check_ok_at_max_boundary():
    assert engine.macro_range_check(65, MacroRange(max=65)) == "OK"

def test_macro_range_check_ok_within_range():
    assert engine.macro_range_check(180, MacroRange(min=150, max=200)) == "OK"


# ---------------------------------------------------------------------------
# range_proximity()
# ---------------------------------------------------------------------------

def test_range_proximity_none_when_no_active_bounds():
    assert engine.range_proximity(100, MacroRange()) is None

def test_range_proximity_near_max():
    r = MacroRange(max=65)
    # distance = 65 - 55 = 10; 10/65 = 15.4% → within 20% → hint
    p = engine.range_proximity(55, r)
    assert p is not None
    assert p.end == "max"
    assert abs(p.distance_g - 10.0) < 0.01

def test_range_proximity_near_min():
    r = MacroRange(min=175)
    # 175 * 1.2 = 210, so 180 is within 20% above min → hint
    p = engine.range_proximity(185, r)
    assert p is not None
    assert p.end == "min"

def test_range_proximity_none_when_far():
    r = MacroRange(max=65)
    # 20 is very far below 65, so NOT within 20% → None
    assert engine.range_proximity(20, r) is None

def test_range_proximity_none_when_over():
    # If already over max, proximity hint is not relevant
    r = MacroRange(max=65)
    assert engine.range_proximity(70, r) is None


# ---------------------------------------------------------------------------
# resolve_day()
# ---------------------------------------------------------------------------

def _make_goals(
    day_type: str = "rest",
    pattern_deficit: int | None = None,
    pattern_protein_min: int | None = None,
) -> Goals:
    defaults = DayMacros(
        protein_g=MacroRange(min=175),
        fat_g=MacroRange(max=65),
    )
    patterns = []
    if pattern_deficit is not None or pattern_protein_min is not None:
        p = DayPattern(
            day_type=day_type,
            deficit_kcal=pattern_deficit,
            protein_g=MacroRange(min=pattern_protein_min) if pattern_protein_min else MacroRange(),
        )
        patterns.append(p)
    return Goals(
        active_cycle_id="cyc1",
        weekly_schedule={"friday": day_type},
        defaults=defaults,
        day_patterns=patterns,
    )


def _make_mesocycle(tdee: int | None = 2600, deficit: int = 400) -> Mesocycle:
    return Mesocycle(
        cycle_id="cyc1",
        phase="cut",
        start_date=date(2026, 1, 1),
        tdee_kcal=tdee,
        deficit_kcal=deficit,
    )


# now = Friday 2026-04-24T12:00:00 UTC
_NOW = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)  # Friday


def test_resolve_day_kcal_from_tdee_deficit():
    goals = _make_goals("rest")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, "UTC", goals, meso)
    assert rd.kcal_target == 2200

def test_resolve_day_kcal_none_when_tdee_none():
    goals = _make_goals("rest")
    meso = _make_mesocycle(tdee=None, deficit=400)
    rd = engine.resolve_day(_NOW, "UTC", goals, meso)
    assert rd.kcal_target is None

def test_resolve_day_pattern_deficit_overrides_cycle():
    goals = _make_goals("rest", pattern_deficit=600)
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, "UTC", goals, meso)
    assert rd.kcal_target == 2000   # 2600 - 600

def test_resolve_day_pattern_protein_overrides_default():
    goals = _make_goals("rest", pattern_protein_min=200)
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(_NOW, "UTC", goals, meso)
    assert rd.protein_g.min == 200  # pattern override

def test_resolve_day_uses_local_weekday_not_utc():
    """UTC 2026-04-27T03:00Z = local Sunday 2026-04-26T21:00 MDT.
    Must return Sunday's day_type, not Monday's UTC day_type."""
    # 2026-04-27 is a Monday in UTC; local in Denver it is still Sunday
    now_utc = datetime(2026, 4, 27, 3, 0, 0, tzinfo=timezone.utc)
    goals = Goals(
        active_cycle_id="cyc1",
        weekly_schedule={"sunday": "rest", "monday": "training"},
        defaults=DayMacros(),
    )
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(now_utc, "America/Denver", goals, meso)
    assert rd.day_type == "rest"   # local Sunday, not UTC Monday

def test_resolve_day_utc_monday_is_monday_in_utc():
    """UTC 2026-04-27T07:00Z = local Monday 2026-04-27T01:00 MDT."""
    now_utc = datetime(2026, 4, 27, 7, 0, 0, tzinfo=timezone.utc)
    goals = Goals(
        active_cycle_id="cyc1",
        weekly_schedule={"sunday": "rest", "monday": "training"},
        defaults=DayMacros(),
    )
    meso = _make_mesocycle(tdee=2600, deficit=400)
    rd = engine.resolve_day(now_utc, "America/Denver", goals, meso)
    assert rd.day_type == "training"   # local Monday


# ---------------------------------------------------------------------------
# current_weight()
# ---------------------------------------------------------------------------

def _wi(id: int, weight: float, supersedes: int | None = None) -> WeighIn:
    return WeighIn(id=id, ts_iso="2026-04-24T12:00:00Z", weight_lbs=weight, supersedes=supersedes)


def test_current_weight_empty():
    assert engine.current_weight([]) is None

def test_current_weight_single():
    assert engine.current_weight([_wi(1, 218.0)]) == 218.0

def test_current_weight_supersedes_chain():
    """Entry 1 is superseded by entry 2. Entry 3 is independent. Most recent active = 3."""
    entries = [
        _wi(1, 220.0),
        _wi(2, 219.0, supersedes=1),  # supersedes 1 — entry 1 is now inactive
        _wi(3, 218.0),                # most recent active
    ]
    assert engine.current_weight(entries) == 218.0

def test_current_weight_all_active_returns_highest_id():
    entries = [_wi(1, 220.0), _wi(2, 219.0), _wi(3, 218.0)]
    assert engine.current_weight(entries) == 218.0


# ---------------------------------------------------------------------------
# weight_change()
# ---------------------------------------------------------------------------

def _wi_at(id: int, weight: float, days_ago: int) -> WeighIn:
    ts = (datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc) - timedelta(days=days_ago))
    return WeighIn(id=id, ts_iso=ts.isoformat(), weight_lbs=weight)


def test_weight_change_empty_list_returns_none():
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert engine.weight_change([], now) is None

def test_weight_change_no_entry_older_than_window_returns_none():
    """Single entry from yesterday; no entry older than 7 days → None."""
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert engine.weight_change([_wi_at(1, 218.0, 1)], now, since_days=7) is None

def test_weight_change_all_entries_recent_returns_none():
    """All entries within 3 days; since_days=7 → None."""
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    entries = [_wi_at(1, 220.0, 3), _wi_at(2, 219.0, 2), _wi_at(3, 218.0, 1)]
    assert engine.weight_change(entries, now, since_days=7) is None

def test_weight_change_two_entries_8_days_apart():
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    entries = [_wi_at(1, 220.0, 8), _wi_at(2, 218.0, 0)]
    wc = engine.weight_change(entries, now, since_days=7)
    assert wc is not None
    assert wc.current_lbs == 218.0
    assert wc.prior_lbs == 220.0
    assert abs(wc.delta_lbs - (-2.0)) < 0.01

def test_weight_change_since_7_days():
    """5 entries spanning 14 days; since_days=7 should use the most recent entry older than 7 days."""
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        _wi_at(1, 222.0, 14),
        _wi_at(2, 221.0, 10),
        _wi_at(3, 220.0, 8),   # most recent older than 7 days
        _wi_at(4, 219.0, 3),
        _wi_at(5, 218.0, 0),   # current
    ]
    wc = engine.weight_change(entries, now, since_days=7)
    assert wc.current_lbs == 218.0
    assert wc.prior_lbs == 220.0
    assert abs(wc.delta_lbs - (-2.0)) < 0.01
    assert wc.since_days == 7


# ---------------------------------------------------------------------------
# weight_trend()
# ---------------------------------------------------------------------------

def test_weight_trend_last_n():
    entries = [_wi_at(i, 220.0 - i, i) for i in range(10)]
    rows = engine.weight_trend(entries, last_n=5)
    assert len(rows) == 5
    # last_n=5 means the 5 entries with highest ids
    ids = [r.weight_lbs for r in rows]
    assert len(ids) == 5


# ---------------------------------------------------------------------------
# event_next() / event_today()
# ---------------------------------------------------------------------------

def _make_event(id: int, days_from_now: int, event_type: str = "appointment") -> Event:
    d = (datetime(2026, 4, 24, 0, 0, 0, tzinfo=timezone.utc) + timedelta(days=days_from_now)).date()
    return Event(id=id, date=d, title=f"event-{id}", event_type=event_type)


_NOW_EVENT = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)

def test_event_next_returns_upcoming_sorted():
    events = [_make_event(3, 10), _make_event(1, 2), _make_event(2, 5)]
    result = engine.event_next(events, _NOW_EVENT, "UTC", n=2)
    assert len(result) == 2
    assert result[0].id == 1
    assert result[1].id == 2

def test_event_next_excludes_past():
    events = [_make_event(1, -1), _make_event(2, 3)]
    result = engine.event_next(events, _NOW_EVENT, "UTC", n=5)
    assert len(result) == 1
    assert result[0].id == 2

def test_event_next_excludes_today():
    """Event dated local-today must not appear in event_next; it belongs to event_today."""
    events = [_make_event(1, 0, "appointment"), _make_event(2, 2)]
    result = engine.event_next(events, _NOW_EVENT, "UTC", n=5)
    assert len(result) == 1
    assert result[0].id == 2

def test_event_today_match():
    events = [_make_event(1, 0, "surgery")]
    result = engine.event_today(events, _NOW_EVENT, "UTC")
    assert result is not None
    assert result.id == 1

def test_event_today_none_when_no_match():
    events = [_make_event(1, 1)]
    assert engine.event_today(events, _NOW_EVENT, "UTC") is None

def test_event_today_uses_local_date_not_utc():
    """UTC 2026-04-27T03:00Z = local 2026-04-26T21:00 MDT.
    Surgery on 2026-04-26 (local date) must be returned."""
    now_utc = datetime(2026, 4, 27, 3, 0, 0, tzinfo=timezone.utc)
    surgery = Event(id=1, date=date(2026, 4, 26), title="surgery", event_type="surgery")
    result = engine.event_today([surgery], now_utc, "America/Denver")
    assert result is not None
    assert result.id == 1

def test_event_next_uses_local_date_boundary():
    """UTC 2026-04-27T03:00Z = local Sunday 2026-04-26T21:00 MDT.
    An event on 2026-04-27 (local Monday) is in the future relative to local today (Sunday)."""
    now_utc = datetime(2026, 4, 27, 3, 0, 0, tzinfo=timezone.utc)
    future_event = Event(id=1, date=date(2026, 4, 27), title="appt", event_type="appointment")
    result = engine.event_next([future_event], now_utc, "America/Denver", n=5)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# dose_reminder_due() / dose_status()
# ---------------------------------------------------------------------------

def _make_protocol(dose_day: str) -> Protocol:
    return Protocol(
        user_id="alice",
        treatment=Treatment(
            medication="Levothyroxine",
            brand="Synthroid",
            dose_mg=112.5,
            dose_day_of_week=dose_day,
            dose_time="08:00",
        ),
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1),
            start_weight_lbs=230.0,
            target_weight_lbs=195.0,
        ),
        clinical=Clinical(),
    )


def _make_dose_entry() -> DoseLogEntry:
    return DoseLogEntry(id=1, ts_iso="2026-04-24T08:00:00Z", dose_mg=112.5, brand="Synthroid")


# _NOW_EVENT is 2026-04-24 which is a Friday
_FRIDAY_PROTOCOL = _make_protocol("friday")
_TUESDAY_PROTOCOL = _make_protocol("tuesday")

def test_dose_reminder_due_true_when_dose_day_no_entry():
    assert engine.dose_reminder_due(_FRIDAY_PROTOCOL, [], _NOW_EVENT, "UTC") is True

def test_dose_reminder_due_false_when_dose_logged():
    assert engine.dose_reminder_due(_FRIDAY_PROTOCOL, [_make_dose_entry()], _NOW_EVENT, "UTC") is False

def test_dose_reminder_due_false_when_not_dose_day():
    assert engine.dose_reminder_due(_TUESDAY_PROTOCOL, [], _NOW_EVENT, "UTC") is False

def test_dose_reminder_due_tz_boundary_sunday_night():
    """UTC 2026-04-27T05:00Z = local Sunday 2026-04-26T23:00 MDT. Dose day=monday → False."""
    now_utc = datetime(2026, 4, 27, 5, 0, 0, tzinfo=timezone.utc)
    monday_protocol = _make_protocol("monday")
    assert engine.dose_reminder_due(monday_protocol, [], now_utc, "America/Denver") is False

def test_dose_reminder_due_tz_boundary_monday_morning():
    """UTC 2026-04-27T07:00Z = local Monday 2026-04-27T01:00 MDT. Dose day=monday → True."""
    now_utc = datetime(2026, 4, 27, 7, 0, 0, tzinfo=timezone.utc)
    monday_protocol = _make_protocol("monday")
    assert engine.dose_reminder_due(monday_protocol, [], now_utc, "America/Denver") is True

def test_dose_status_pending():
    # Friday protocol, no dose entries, is_dose_day=True
    assert engine.dose_status([], is_dose_day=True) == "pending"

def test_dose_status_logged():
    assert engine.dose_status([_make_dose_entry()], is_dose_day=True) == "logged"

def test_dose_status_not_due():
    assert engine.dose_status([], is_dose_day=False) == "not_due"


# ---------------------------------------------------------------------------
# advisory_flags()
# ---------------------------------------------------------------------------

def _make_surgery_event(days_from_now: int) -> Event:
    d = (_NOW_EVENT + timedelta(days=days_from_now)).date()
    return Event(id=99, date=d, title="surgery", event_type="surgery")


def test_advisory_flags_surgery_within_7_days():
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    events = [_make_surgery_event(5)]
    flags = engine.advisory_flags(protocol, events, meso, _NOW_EVENT, "UTC")
    assert len(flags) == 1
    assert flags[0].code == "surgery_window"
    assert flags[0].severity == "warn"

def test_advisory_flags_surgery_at_7_days():
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    events = [_make_surgery_event(7)]
    flags = engine.advisory_flags(protocol, events, meso, _NOW_EVENT, "UTC")
    assert len(flags) == 1

def test_advisory_flags_surgery_beyond_7_days():
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    events = [_make_surgery_event(10)]
    flags = engine.advisory_flags(protocol, events, meso, _NOW_EVENT, "UTC")
    assert flags == []

def test_advisory_flags_no_surgery_event():
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    events = [_make_event(1, 3, "appointment")]
    flags = engine.advisory_flags(protocol, events, meso, _NOW_EVENT, "UTC")
    assert flags == []

def test_advisory_flags_surgery_uses_local_date():
    """Surgery 5 local days out from a Denver user at UTC 2026-04-25T03:00 must fire flag."""
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)  # local 2026-04-24
    surgery_date = date(2026, 4, 29)  # 5 local days from 2026-04-24
    surgery = Event(id=99, date=surgery_date, title="surgery", event_type="surgery")
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    flags = engine.advisory_flags(protocol, [surgery], meso, now_utc, "America/Denver")
    assert len(flags) == 1
    assert flags[0].code == "surgery_window"

def test_advisory_flags_surgery_8_local_days_no_flag():
    now_utc = datetime(2026, 4, 25, 3, 0, 0, tzinfo=timezone.utc)  # local 2026-04-24
    surgery_date = date(2026, 5, 2)  # 8 local days from 2026-04-24
    surgery = Event(id=99, date=surgery_date, title="surgery", event_type="surgery")
    protocol = _make_protocol("friday")
    meso = _make_mesocycle(tdee=2600, deficit=400)
    flags = engine.advisory_flags(protocol, [surgery], meso, now_utc, "America/Denver")
    assert flags == []


# ---------------------------------------------------------------------------
# protected_gate_protocol()
# ---------------------------------------------------------------------------

def _make_protocol_pair(dose_mg_current=112.5, dose_mg_proposed=112.5,
                        dose_day_current="friday", dose_day_proposed="friday",
                        titration_current=None, titration_proposed="new notes"):
    current = _make_protocol(dose_day_current)
    # Build proposed by copy, then set different fields
    proposed_treatment = Treatment(
        medication="Levothyroxine",
        brand="Synthroid",
        dose_mg=dose_mg_proposed,
        dose_day_of_week=dose_day_proposed,
        dose_time="08:00",
        titration_notes=titration_proposed,
    )
    proposed = Protocol(
        user_id="alice",
        treatment=proposed_treatment,
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1),
            start_weight_lbs=230.0,
            target_weight_lbs=195.0,
        ),
        clinical=Clinical(),
    )
    current_treatment = Treatment(
        medication="Levothyroxine",
        brand="Synthroid",
        dose_mg=dose_mg_current,
        dose_day_of_week=dose_day_current,
        dose_time="08:00",
        titration_notes=titration_current,
    )
    current_full = Protocol(
        user_id="alice",
        treatment=current_treatment,
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1),
            start_weight_lbs=230.0,
            target_weight_lbs=195.0,
        ),
        clinical=Clinical(),
    )
    return current_full, proposed


def test_protected_gate_protocol_no_phrase_fails():
    current, proposed = _make_protocol_pair(dose_mg_current=112.5, dose_mg_proposed=125.0)
    result = engine.protected_gate_protocol(current, proposed, "")
    assert result.ok is False
    assert result.applied is False

def test_protected_gate_protocol_correct_phrase_passes():
    current, proposed = _make_protocol_pair(dose_mg_current=112.5, dose_mg_proposed=125.0)
    result = engine.protected_gate_protocol(current, proposed, "confirm protocol change")
    assert result.ok is True
    assert result.applied is True

def test_protected_gate_protocol_case_mismatch_fails():
    current, proposed = _make_protocol_pair(dose_mg_current=112.5, dose_mg_proposed=125.0)
    result = engine.protected_gate_protocol(current, proposed, "Confirm Protocol Change")
    assert result.ok is False

def test_protected_gate_protocol_non_protected_diff_passes():
    """Changing titration_notes (not in protected dict) should pass without phrase."""
    current, proposed = _make_protocol_pair(titration_current=None, titration_proposed="taper")
    result = engine.protected_gate_protocol(current, proposed, "")
    assert result.ok is True
    assert result.applied is True


# ---------------------------------------------------------------------------
# protected_gate_range()
# ---------------------------------------------------------------------------

def test_protected_gate_range_no_phrase_fails():
    current = MacroRange(min=175, protected=True)
    proposed = MacroRange(min=180, protected=True)
    result = engine.protected_gate_range(current, proposed, "")
    assert result.ok is False
    assert result.applied is False

def test_protected_gate_range_correct_phrase_passes():
    current = MacroRange(min=175, protected=True)
    proposed = MacroRange(min=180, protected=True)
    result = engine.protected_gate_range(current, proposed, "confirm macro range change")
    assert result.ok is True
    assert result.applied is True

def test_protected_gate_range_adding_max_triggers_gate():
    current = MacroRange(min=175, protected=True)
    proposed = MacroRange(min=175, max=200, protected=True)
    result = engine.protected_gate_range(current, proposed, "")
    assert result.ok is False

def test_protected_gate_range_unprotected_passes_without_phrase():
    current = MacroRange(min=175, protected=False)
    proposed = MacroRange(min=180, protected=False)
    result = engine.protected_gate_range(current, proposed, "")
    assert result.ok is True


# ---------------------------------------------------------------------------
# setup_status() — Tripwire 6: fixed order + dependency logic
# ---------------------------------------------------------------------------

def _ns(**kwargs) -> NeedsSetup:
    defaults = dict(gallbladder=False, tdee=False, carbs_shape=False, deficits=False, nominal_deficit=False)
    defaults.update(kwargs)
    return NeedsSetup(**defaults)


def test_setup_status_all_true_next_is_gallbladder():
    ns = _ns(gallbladder=True, tdee=True, carbs_shape=True, deficits=True, nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "gallbladder"

def test_setup_status_after_gallbladder_clears_next_is_tdee():
    ns = _ns(tdee=True, carbs_shape=True, deficits=True, nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "tdee"

def test_setup_status_after_gallbladder_tdee_next_is_carbs_shape():
    ns = _ns(carbs_shape=True, deficits=True, nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "carbs_shape"

def test_setup_status_deficits_blocked_by_tdee():
    """With tdee=True, deficits and nominal_deficit should NOT surface; next_marker stays tdee."""
    ns = _ns(gallbladder=False, tdee=True, carbs_shape=False, deficits=True, nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "tdee"

def test_setup_status_nominal_deficit_blocked_by_deficits():
    ns = _ns(deficits=True, nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "deficits"

def test_setup_status_only_nominal_deficit_remaining():
    ns = _ns(nominal_deficit=True)
    ss = engine.setup_status(ns)
    assert ss.next_marker == "nominal_deficit"

def test_setup_status_all_cleared_complete():
    ns = _ns()
    ss = engine.setup_status(ns)
    assert ss.complete is True
    assert ss.next_marker is None
    assert ss.markers_remaining == []
