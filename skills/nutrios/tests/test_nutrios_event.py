"""Tests for nutrios_event — add, list, remove with soft-delete."""
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import Event, ToolResult
import nutrios_store as store
import nutrios_event as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice", "now": _NOW.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_event_rejects_unknown_action(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="bogus"))


def test_event_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="list", bogus=1))


def test_event_add_unknown_event_type_pydantic_rejects(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValidationError):
        tool.main(_argv(
            action="add", event_date="2026-05-01",
            event_type="not_a_real_type", title="x",
        ))


def test_event_add_missing_required_fields_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="event_date"):
        tool.main(_argv(action="add"))


def test_event_remove_missing_id_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="id"):
        tool.main(_argv(action="remove"))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def test_event_add_happy_path(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(
        action="add",
        event_date="2026-05-15",
        event_type="surgery",
        title="gallbladder surgery",
        notes="prep starts day-3",
    ))
    assert "Event added" in result.display_text
    assert "gallbladder surgery" in result.display_text
    assert result.state_delta["last_event_id"] == 1

    events = store.read_events("alice")
    assert len(events) == 1
    assert events[0].title == "gallbladder surgery"
    assert events[0].notes == "prep starts day-3"
    assert events[0].removed is False


def test_event_add_consecutive_increments_id(tmp_data_root, setup_user):
    setup_user("alice")
    r1 = tool.main(_argv(
        action="add", event_date="2026-05-01", event_type="appointment", title="follow-up",
    ))
    r2 = tool.main(_argv(
        action="add", event_date="2026-06-01", event_type="appointment", title="follow-up 2",
    ))
    assert r1.state_delta["last_event_id"] == 1
    assert r2.state_delta["last_event_id"] == 2

    events = store.read_events("alice")
    assert len(events) == 2


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_event_list_empty(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="list"))
    assert result.display_text == "No upcoming events."


def test_event_list_returns_upcoming_only(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_events("alice", [
        Event(id=1, date=date(2026, 4, 20), title="past", event_type="other"),
        Event(id=2, date=date(2026, 5, 1), title="upcoming", event_type="surgery"),
        Event(id=3, date=date(2026, 6, 1), title="future", event_type="appointment"),
    ])
    result = tool.main(_argv(action="list", n=10))
    assert "past" not in result.display_text
    assert "upcoming" in result.display_text
    assert "future" in result.display_text


def test_event_list_filters_removed(tmp_data_root, setup_user):
    setup_user("alice")
    store.write_events("alice", [
        Event(id=1, date=date(2026, 5, 1), title="kept", event_type="surgery"),
        Event(id=2, date=date(2026, 5, 5), title="hidden", event_type="other", removed=True),
    ])
    result = tool.main(_argv(action="list", n=10))
    assert "kept" in result.display_text
    assert "hidden" not in result.display_text


# ---------------------------------------------------------------------------
# remove (soft delete via full rewrite)
# ---------------------------------------------------------------------------

def test_event_remove_flips_removed_flag(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        action="add", event_date="2026-05-01", event_type="surgery", title="cancellable",
    ))
    result = tool.main(_argv(action="remove", id=1))
    assert "removed" in result.display_text.lower()
    assert "cancellable" in result.display_text

    events = store.read_events("alice")
    assert len(events) == 1
    assert events[0].removed is True


def test_event_remove_hides_from_subsequent_list(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(
        action="add", event_date="2026-05-01", event_type="surgery", title="hidden",
    ))
    tool.main(_argv(
        action="add", event_date="2026-06-01", event_type="appointment", title="kept",
    ))
    tool.main(_argv(action="remove", id=1))

    listing = tool.main(_argv(action="list", n=10))
    assert "hidden" not in listing.display_text
    assert "kept" in listing.display_text


def test_event_remove_missing_id_returns_not_found(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="remove", id=999))
    assert "doesn't exist" in result.display_text or "does not exist" in result.display_text
    assert "event" in result.display_text


def test_event_remove_idempotent(tmp_data_root, setup_user):
    """Removing an already-removed event returns the same confirm; no error."""
    setup_user("alice")
    tool.main(_argv(
        action="add", event_date="2026-05-01", event_type="surgery", title="x",
    ))
    tool.main(_argv(action="remove", id=1))
    result = tool.main(_argv(action="remove", id=1))  # second remove
    assert "removed" in result.display_text.lower()


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_event_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(
        action="add", event_date="2026-05-01", event_type="surgery", title="alice-event",
    ))
    assert store.read_events("bob") == []
