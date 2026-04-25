"""Tests for nutrios_protocol_edit — gated protocol writes."""
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nutrios_models import (
    BiometricSnapshot, Clinical, Protocol, ToolResult, Treatment,
)
import nutrios_store as store
import nutrios_protocol_edit as tool


_NOW = datetime(2026, 4, 24, 18, 0, 0, tzinfo=timezone.utc)
_TZ = "America/Denver"


def _payload(*, dose_mg=10.0, gallbladder="present") -> dict:
    return Protocol(
        user_id="alice",
        treatment=Treatment(
            medication="Tirzepatide", brand="Mounjaro",
            dose_mg=dose_mg, dose_day_of_week="thursday", dose_time="07:00",
        ),
        biometrics=BiometricSnapshot(
            start_date=date(2026, 1, 1), start_weight_lbs=220.0, target_weight_lbs=180.0,
        ),
        clinical=Clinical(gallbladder_status=gallbladder),
    ).model_dump(mode="json")


def _argv(**kwargs) -> str:
    payload = {"user_id": "alice", "now": _NOW.isoformat(), "tz": _TZ}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_protocol_edit_rejects_extra_field(tmp_data_root):
    with pytest.raises(ValidationError):
        tool.main(_argv(payload=_payload(), bogus=1))


def test_protocol_edit_invalid_payload_raises(tmp_data_root, setup_user):
    setup_user("alice")
    bad = {"user_id": "alice", "treatment": "not_a_dict"}  # garbage payload
    with pytest.raises(ValidationError):
        tool.main(_argv(payload=bad))


# ---------------------------------------------------------------------------
# Non-protected change (gallbladder_status)
# ---------------------------------------------------------------------------

def test_protocol_edit_gallbladder_no_confirm_succeeds(tmp_data_root, setup_user):
    """gallbladder_status is in clinical, not in protected — passes without phrase.
    This is the path setup_resume uses for the gallbladder marker."""
    setup_user("alice")
    result = tool.main(_argv(payload=_payload(gallbladder="removed")))
    assert "Protocol updated" in result.display_text
    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.clinical.gallbladder_status == "removed"


def test_protocol_edit_no_change_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(payload=_payload()))  # identical to fixture
    assert result.display_text == "Protocol updated."


# ---------------------------------------------------------------------------
# Protected change (dose_mg)
# ---------------------------------------------------------------------------

def test_protocol_edit_dose_mg_without_confirm_rejected(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(payload=_payload(dose_mg=12.5)))
    assert "Protected" in result.display_text or "protect" in result.display_text.lower()
    assert result.needs_followup is True

    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.treatment.dose_mg == 10.0  # unchanged


def test_protocol_edit_dose_mg_with_confirm_succeeds(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(
        payload=_payload(dose_mg=12.5),
        confirm="confirm protocol change",
    ))
    assert result.display_text == "Protocol updated."
    on_disk = store.read_json("alice", "protocol.json", Protocol)
    assert on_disk.treatment.dose_mg == 12.5


def test_protocol_edit_dose_mg_with_wrong_confirm_phrase_rejected(tmp_data_root, setup_user):
    setup_user("alice")
    result = tool.main(_argv(
        payload=_payload(dose_mg=12.5),
        confirm="confirm change please",  # wrong phrase
    ))
    assert "Protected" in result.display_text or "protect" in result.display_text.lower()


# ---------------------------------------------------------------------------
# First-time write (no current protocol)
# ---------------------------------------------------------------------------

def test_protocol_edit_first_time_no_gate(tmp_data_root):
    """Without an existing protocol.json, no gate runs."""
    result = tool.main(_argv(payload=_payload(dose_mg=15.0)))
    assert result.display_text == "Protocol updated."


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_protocol_edit_isolation(tmp_data_root, setup_user):
    setup_user("alice")
    setup_user("bob")
    tool.main(_argv(payload=_payload(gallbladder="removed")))

    bob_proto = store.read_json("bob", "protocol.json", Protocol)
    assert bob_proto.clinical.gallbladder_status == "present"  # untouched
