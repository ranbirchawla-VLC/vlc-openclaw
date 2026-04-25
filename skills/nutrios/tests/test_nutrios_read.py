"""Tests for nutrios_read — scope-routed read entrypoint.

Each scope gets a happy path + at least one edge case (empty data, missing
required field, isolation across users). main() is unit-tested directly;
the __main__ argv-parse branch is covered by a single subprocess-style test.
"""
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import (
    Event, FoodLogEntry, MedNote, Recipe, RecipeMacros, ToolResult, WeighIn,
)
import nutrios_store as store
import nutrios_read as tool


# Fixed Friday afternoon UTC; local Denver = same calendar day
_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"
_TODAY = _NOW.astimezone(__import__("zoneinfo").ZoneInfo(_TZ)).date()


def _argv(**kwargs) -> str:
    """Build a JSON argv string with the given fields, defaulting common ones."""
    payload = {
        "user_id": "alice",
        "now": _NOW.isoformat(),
        "tz": _TZ,
    }
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_read_rejects_unknown_scope(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValidationError):
        tool.main(_argv(scope="bogus"))


def test_read_rejects_missing_user_id(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(json.dumps({"scope": "weigh_ins", "now": _NOW.isoformat(), "tz": _TZ}))


def test_read_rejects_extra_field(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValidationError):
        tool.main(_argv(scope="weigh_ins", bogus="extra"))


def test_read_log_date_requires_target_date_field(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="target_date"):
        tool.main(_argv(scope="log_date"))


# ---------------------------------------------------------------------------
# log_today / log_date
# ---------------------------------------------------------------------------

def _food_entry(eid: int, kcal: int, p: float, c: float, f: float, slot="lunch", ts=None) -> FoodLogEntry:
    return FoodLogEntry(
        kind="food", id=eid, ts_iso=ts or _NOW.isoformat().replace("+00:00", "Z"),
        meal_slot=slot, source="manual",
        name=f"food-{eid}", qty=100.0, unit="g",
        kcal=kcal, protein_g=p, carbs_g=c, fat_g=f,
    )


def test_read_log_today_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="log_today"))
    assert isinstance(result, ToolResult)
    assert "Calories" in result.display_text
    # Friday is a "rest" day in the fixture
    assert "[rest]" in result.display_text


def test_read_log_today_with_food(tmp_data_root, setup_user):
    setup_user("alice")
    store.append_jsonl("alice", f"log/{_TODAY}.jsonl", _food_entry(1, 500, 40.0, 30.0, 20.0))
    store.append_jsonl("alice", f"log/{_TODAY}.jsonl", _food_entry(2, 300, 25.0, 20.0, 10.0))

    result = tool.main(_argv(scope="log_today"))
    # Macros sum to 65g protein, 50g carbs, 30g fat, 800 kcal
    assert "food-1" in result.display_text
    assert "food-2" in result.display_text
    assert result.state_delta["kcal_actual"] == 800


def test_read_log_today_protein_low_status(tmp_data_root, setup_user):
    """Default protein min is 175g; logging 40g should yield LOW status line."""
    setup_user("alice")
    store.append_jsonl("alice", f"log/{_TODAY}.jsonl", _food_entry(1, 500, 40.0, 30.0, 20.0))

    result = tool.main(_argv(scope="log_today"))
    # Macro line ends with status; "LOW" must appear somewhere on the protein line
    assert "Protein" in result.display_text
    assert "LOW" in result.display_text


def test_read_log_today_with_dose_and_weigh_in(tmp_data_root, setup_user):
    """Mixed-kind JSONL plus today's weigh-in: dose status logged, weigh-in line present."""
    setup_user("alice")
    # Append a dose entry (kind=dose) to today's log
    today_log = f"log/{_TODAY}.jsonl"
    food = _food_entry(1, 500, 40.0, 30.0, 20.0)
    dose = {
        "kind": "dose", "id": 2,
        "ts_iso": _NOW.isoformat().replace("+00:00", "Z"),
        "dose_mg": 10.0, "brand": "Mounjaro",
    }
    store.append_jsonl("alice", today_log, food)
    # tail_jsonl helpers expect models, but we can write a dose dict via the
    # append path through an actual DoseLogEntry
    from nutrios_models import DoseLogEntry
    dose_entry = DoseLogEntry(id=2, ts_iso=_NOW.isoformat().replace("+00:00", "Z"),
                              dose_mg=10.0, brand="Mounjaro")
    store.append_jsonl("alice", today_log, dose_entry)

    # Today's weigh-in
    wi = WeighIn(id=1, ts_iso=_NOW.isoformat().replace("+00:00", "Z"), weight_lbs=218.0)
    store.append_jsonl("alice", "weigh_ins.jsonl", wi)

    result = tool.main(_argv(scope="log_today"))
    assert "Dose: logged" in result.display_text
    assert "Weighed in: 218.0" in result.display_text


def test_read_log_today_no_setup_returns_protocol_error(tmp_data_root):
    """Without a goals file, log_today returns the protocol-not-initialized message."""
    # No setup_user — empty data root
    result = tool.main(_argv(scope="log_today"))
    assert "Protocol not set" in result.display_text


def test_read_log_date_specific(tmp_data_root, setup_user):
    setup_user("alice")
    historical = date(2026, 4, 20)
    historical_log = f"log/{historical}.jsonl"
    entry = _food_entry(
        1, 600, 50.0, 60.0, 25.0,
        ts=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    store.append_jsonl("alice", historical_log, entry)

    result = tool.main(_argv(scope="log_date", target_date=str(historical)))
    assert result.state_delta["date"] == "2026-04-20"
    assert result.state_delta["kcal_actual"] == 600


# ---------------------------------------------------------------------------
# weigh_ins
# ---------------------------------------------------------------------------

def test_read_weigh_ins_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="weigh_ins"))
    assert result.display_text == "No weigh-ins yet."


def test_read_weigh_ins_trend(tmp_data_root, setup_user):
    setup_user("alice")
    for i, (day, w) in enumerate([
        ("2026-04-15T12:00:00Z", 220.0),
        ("2026-04-18T12:00:00Z", 219.0),
        ("2026-04-21T12:00:00Z", 218.5),
        ("2026-04-24T12:00:00Z", 218.0),
    ], start=1):
        store.append_jsonl("alice", "weigh_ins.jsonl",
                           WeighIn(id=i, ts_iso=day, weight_lbs=w))
    result = tool.main(_argv(scope="weigh_ins", n=4))
    assert "Weight trend" in result.display_text
    assert "220.0" in result.display_text
    assert "218.0" in result.display_text


# ---------------------------------------------------------------------------
# med_notes
# ---------------------------------------------------------------------------

def test_read_med_notes_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="med_notes"))
    assert result.display_text == "No notes."


def test_read_med_notes_returns_recent(tmp_data_root, setup_user):
    setup_user("alice")
    for i in range(1, 6):
        store.append_jsonl("alice", "med_notes.jsonl",
                           MedNote(id=i, ts_iso=f"2026-04-{20+i}T10:00:00Z",
                                   note=f"note {i}", source="self"))
    result = tool.main(_argv(scope="med_notes", n=3))
    # n=3 returns last 3
    assert "note 3" in result.display_text
    assert "note 4" in result.display_text
    assert "note 5" in result.display_text
    assert "note 1" not in result.display_text
    assert "note 2" not in result.display_text


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

def test_read_events_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="events"))
    assert result.display_text == "No upcoming events."


def test_read_events_upcoming(tmp_data_root, setup_user):
    setup_user("alice")
    events = [
        Event(id=1, date=date(2026, 5, 1), title="surgery", event_type="surgery"),
        Event(id=2, date=date(2026, 6, 1), title="follow-up", event_type="appointment"),
        Event(id=3, date=date(2026, 4, 20), title="past", event_type="other"),  # past
    ]
    store.write_events("alice", events)
    result = tool.main(_argv(scope="events", n=10))
    assert "surgery" in result.display_text
    assert "follow-up" in result.display_text
    assert "past" not in result.display_text


def test_read_events_filters_removed(tmp_data_root, setup_user):
    setup_user("alice")
    events = [
        Event(id=1, date=date(2026, 5, 1), title="kept", event_type="surgery"),
        Event(id=2, date=date(2026, 5, 5), title="hidden", event_type="other", removed=True),
    ]
    store.write_events("alice", events)
    result = tool.main(_argv(scope="events", n=10))
    assert "kept" in result.display_text
    assert "hidden" not in result.display_text


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------

def test_read_protocol_returns_view(tmp_data_root, setup_user):
    setup_user("alice")
    store.append_jsonl("alice", "med_notes.jsonl",
                       MedNote(id=1, ts_iso="2026-04-20T10:00:00Z", note="all good", source="doctor"))
    result = tool.main(_argv(scope="protocol"))
    assert "Tirzepatide" in result.display_text
    assert "Mounjaro" in result.display_text
    # Protocol view includes recent notes
    assert "all good" in result.display_text


def test_read_protocol_missing(tmp_data_root):
    """No setup → protocol-not-initialized."""
    result = tool.main(_argv(scope="protocol"))
    assert "Protocol not set" in result.display_text


# ---------------------------------------------------------------------------
# goals + mesocycle
# ---------------------------------------------------------------------------

def test_read_goals_view(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="goals"))
    assert "Goals" in result.display_text
    assert "cycle1" in result.display_text
    assert "2600" in result.display_text  # TDEE
    assert "(protected)" in result.display_text  # protein/fat are protected


def test_read_goals_missing(tmp_data_root):
    result = tool.main(_argv(scope="goals"))
    assert "Protocol not set" in result.display_text


def test_read_mesocycle_view(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="mesocycle"))
    assert "cycle1" in result.display_text
    assert "cut" in result.display_text
    assert "2600" in result.display_text


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------

def _r(rid: int, name: str, removed: bool = False) -> Recipe:
    return Recipe(
        id=rid, name=name, servings=1,
        macros_per_serving=RecipeMacros(kcal=400, protein_g=30.0, carbs_g=40.0, fat_g=12.0),
        removed=removed,
    )


def test_read_recipes_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="recipes"))
    assert result.display_text == "No recipes saved."


def test_read_recipes_lists_active(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_recipes("alice", [_r(1, "protein shake"), _r(2, "oats"),
                                  _r(3, "old", removed=True)])
    result = tool.main(_argv(scope="recipes"))
    assert "protein shake" in result.display_text
    assert "oats" in result.display_text
    assert "old" not in result.display_text


def test_read_recipes_query_filters_by_name(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_recipes("alice", [_r(1, "protein shake"), _r(2, "oats")])
    result = tool.main(_argv(scope="recipes", query="oat"))
    assert "oats" in result.display_text
    assert "protein shake" not in result.display_text


# ---------------------------------------------------------------------------
# Per-user isolation
# ---------------------------------------------------------------------------

def test_read_isolation_alice_does_not_see_bob(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    store.append_jsonl("bob", "weigh_ins.jsonl",
                       WeighIn(id=1, ts_iso="2026-04-24T12:00:00Z", weight_lbs=180.0))

    alice_result = tool.main(_argv(scope="weigh_ins"))
    assert alice_result.display_text == "No weigh-ins yet."

    bob_result = tool.main(_argv(scope="weigh_ins", user_id="bob"))
    assert "180.0" in bob_result.display_text


# ---------------------------------------------------------------------------
# Stdout contract — main() returns ToolResult; argv path produces JSON line
# ---------------------------------------------------------------------------

def test_read_main_returns_tool_result_instance(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(scope="weigh_ins"))
    assert isinstance(result, ToolResult)
    # The returned ToolResult must serialize cleanly to a single JSON line
    line = result.model_dump_json()
    assert "\n" not in line
    parsed = json.loads(line)
    assert "display_text" in parsed
