"""Tests for nutrios_med_note — add and view actions."""
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import MedNote, ToolResult
import nutrios_store as store
import nutrios_med_note as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice", "now": _NOW.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_med_note_rejects_unknown_action(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="bogus"))


def test_med_note_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="add", note_text="x", bogus=1))


def test_med_note_rejects_unknown_source(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(action="add", note_text="x", source="bogus"))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def test_med_note_add_happy_path(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="add", note_text="Felt tired today.", source="self"))
    assert "Felt tired today" in result.display_text
    assert result.state_delta["last_med_note_id"] == 1

    raw = store.tail_jsonl("alice", "med_notes.jsonl", 10)
    assert len(raw) == 1
    assert raw[0]["note"] == "Felt tired today."
    assert raw[0]["source"] == "self"


def test_med_note_add_default_source_self(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="add", note_text="Note from user."))
    raw = store.tail_jsonl("alice", "med_notes.jsonl", 10)
    assert raw[0]["source"] == "self"


def test_med_note_add_doctor_source(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="add", note_text="Increase to 12.5 next month.", source="doctor"))
    raw = store.tail_jsonl("alice", "med_notes.jsonl", 10)
    assert raw[0]["source"] == "doctor"


def test_med_note_add_strips_whitespace(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(action="add", note_text="  trimmed  "))
    raw = store.tail_jsonl("alice", "med_notes.jsonl", 10)
    assert raw[0]["note"] == "trimmed"


def test_med_note_add_empty_text_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="note_text"):
        tool.main(_argv(action="add", note_text=""))


def test_med_note_add_whitespace_only_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="note_text"):
        tool.main(_argv(action="add", note_text="   "))


def test_med_note_add_missing_text_raises(tmp_data_root, setup_user):
    setup_user("alice")
    with pytest.raises(ValueError, match="note_text"):
        tool.main(_argv(action="add"))


def test_med_note_add_consecutive_increments_counter(tmp_data_root, setup_user):
    setup_user("alice")
    r1 = tool.main(_argv(action="add", note_text="a"))
    r2 = tool.main(_argv(action="add", note_text="b"))
    assert r1.state_delta["last_med_note_id"] == 1
    assert r2.state_delta["last_med_note_id"] == 2


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------

def test_med_note_view_includes_protocol(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(action="view"))
    assert "Tirzepatide" in result.display_text
    assert "Mounjaro" in result.display_text


def test_med_note_view_includes_recent_notes(tmp_data_root, setup_user):
    setup_user("alice")
    # Seed five notes; view should return only last 3
    for i in range(1, 6):
        tool.main(_argv(action="add", note_text=f"note-{i}"))
    result = tool.main(_argv(action="view"))
    assert "note-3" in result.display_text
    assert "note-4" in result.display_text
    assert "note-5" in result.display_text
    assert "note-1" not in result.display_text
    assert "note-2" not in result.display_text


def test_med_note_view_no_protocol_returns_not_initialized(tmp_data_root):
    result = tool.main(_argv(action="view"))
    assert "Protocol not set" in result.display_text


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_med_note_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(action="add", note_text="alice note"))
    assert store.tail_jsonl("bob", "med_notes.jsonl", 10) == []
