"""Tests for nutrios_dose — dose-day awareness, snapshot from protocol."""
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from nutrios_models import DoseLogEntry, ToolResult
import nutrios_store as store
import nutrios_dose as tool


# Friday afternoon UTC; local Denver = same calendar Friday.
_FRIDAY = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
# Thursday afternoon UTC; local Denver = same calendar Thursday.
_THURSDAY = datetime(2026, 4, 23, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _argv(*, when: datetime = _THURSDAY, **kwargs) -> str:
    """Default to Thursday (the fixture user's dose day)."""
    payload = {"user_id": "alice", "now": when.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_dose_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(bogus=1))


def test_dose_rejects_missing_user_id(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(json.dumps({"now": _THURSDAY.isoformat(), "tz": _TZ}))


# ---------------------------------------------------------------------------
# Pre-conditions
# ---------------------------------------------------------------------------

def test_dose_no_protocol_returns_not_initialized(tmp_data_root):
    result = tool.main(_argv())
    assert "Protocol not set" in result.display_text


# ---------------------------------------------------------------------------
# Not dose day → render_dose_not_due
# ---------------------------------------------------------------------------

def test_dose_not_dose_day_friday_returns_not_due(tmp_data_root, setup_user):
    """Fixture user's dose day is Thursday; on Friday the call rejects."""
    setup_user("alice")
    result = tool.main(_argv(when=_FRIDAY))
    assert "Not a dose day" in result.display_text
    assert "Thursday" in result.display_text
    # No append happened
    local_friday = date(2026, 4, 24)
    assert store.tail_jsonl("alice", f"log/{local_friday}.jsonl", 10) == []


def test_dose_not_due_includes_next_thursday_date(tmp_data_root, setup_user):
    """Friday → next Thursday is 6 days later."""
    setup_user("alice")
    result = tool.main(_argv(when=_FRIDAY))
    # Local Friday is 2026-04-24; next Thursday is 2026-04-30
    assert "2026-04-30" in result.display_text


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_dose_thursday_no_prior_logs_dose(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(when=_THURSDAY))
    assert "Dose logged" in result.display_text
    # Dose entry snapshots dose_mg and brand from current protocol
    assert "10.0" in result.display_text
    assert "Mounjaro" in result.display_text
    assert result.state_delta["last_entry_id"] == 1

    # Appended to today's local-date file
    local_thursday = date(2026, 4, 23)
    raw = store.tail_jsonl("alice", f"log/{local_thursday}.jsonl", 10)
    assert len(raw) == 1
    assert raw[0]["kind"] == "dose"
    assert raw[0]["dose_mg"] == 10.0
    assert raw[0]["brand"] == "Mounjaro"


def test_dose_snapshot_independent_of_later_protocol_change(tmp_data_root, setup_user):
    """A logged dose stores dose_mg+brand at log time; later protocol edits don't rewrite history."""
    setup_user("alice")
    tool.main(_argv(when=_THURSDAY))

    # Mutate protocol on disk (simulating a subsequent protocol_edit)
    from nutrios_models import Protocol
    proto = store.read_json("alice", "protocol.json", Protocol)
    bumped = proto.model_copy(update={
        "treatment": proto.treatment.model_copy(update={"dose_mg": 12.5, "brand": "OtherBrand"})
    })
    store.write_json("alice", "protocol.json", bumped)

    # Dose entry must still show the original snapshot
    local_thursday = date(2026, 4, 23)
    raw = store.tail_jsonl("alice", f"log/{local_thursday}.jsonl", 10)
    assert raw[0]["dose_mg"] == 10.0
    assert raw[0]["brand"] == "Mounjaro"


# ---------------------------------------------------------------------------
# Already logged → render_dose_already_logged
# ---------------------------------------------------------------------------

def test_dose_already_logged_today_rejects(tmp_data_root, setup_user):
    setup_user("alice")
    tool.main(_argv(when=_THURSDAY))  # first log
    result = tool.main(_argv(when=_THURSDAY))  # second attempt
    assert "already logged" in result.display_text.lower()

    # Disk has only one dose entry
    local_thursday = date(2026, 4, 23)
    doses = [r for r in store.tail_jsonl("alice", f"log/{local_thursday}.jsonl", 10) if r["kind"] == "dose"]
    assert len(doses) == 1


# ---------------------------------------------------------------------------
# Counter shared with food entries
# ---------------------------------------------------------------------------

def test_dose_id_shares_last_entry_id_counter(tmp_data_root, setup_user):
    """LogEntry is a discriminated union; food and dose increment the same counter."""
    setup_user("alice")
    # Simulate a prior food log bumping the counter
    from nutrios_models import State
    store.write_json("alice", "state.json", State(last_entry_id=5))

    result = tool.main(_argv(when=_THURSDAY))
    assert result.state_delta["last_entry_id"] == 6


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_dose_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(when=_THURSDAY))  # alice
    local_thursday = date(2026, 4, 23)
    assert store.tail_jsonl("bob", f"log/{local_thursday}.jsonl", 10) == []
