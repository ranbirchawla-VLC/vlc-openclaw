"""Tests for scripts/gtd/capture.py -- Z3 version.

capture() now returns {"captured": <read_projection>} per locked API.
Channel fields passed as args (source, telegram_chat_id). validate_submission
called before write(); submission_invalid raised on submission contract violation.
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from capture import capture, main
from common import GTDError


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_SOURCE = "telegram_text"
_CHAT_ID = "8712103657"


def _task(**overrides) -> dict:
    base = {"record_type": "task", "title": "Call the broker", "context": "@phone"}
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {"record_type": "idea", "title": "New feature idea",
            "content": "Build it with n8n"}
    return {**base, **overrides}


def _parking_lot(**overrides) -> dict:
    base = {"record_type": "parking_lot", "content": "Stray thought"}
    return {**base, **overrides}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Round-trip tests — assert 13/9/8 projection fields in capture response
# ---------------------------------------------------------------------------

def test_capture_round_trip_task(storage: Path) -> None:
    """capture() returns {"captured": {...}} with all 13 task projection fields."""
    result = capture(_task(), "user1", _SOURCE, _CHAT_ID)
    assert "captured" in result
    cap = result["captured"]
    expected = {
        "id", "title", "context", "project", "priority", "waiting_for",
        "due_date", "notes", "status", "created_at", "updated_at",
        "last_reviewed", "completed_at",
    }
    assert expected == cap.keys(), (
        f"Missing: {expected - cap.keys()}; Extra: {cap.keys() - expected}"
    )
    assert _UUID4_RE.match(cap["id"])
    # channel fields must NOT appear in projection
    assert "source" not in cap
    assert "telegram_chat_id" not in cap
    assert "record_type" not in cap


def test_capture_round_trip_idea(storage: Path) -> None:
    """capture() returns 9 idea projection fields."""
    result = capture(_idea(), "user1", _SOURCE, _CHAT_ID)
    cap = result["captured"]
    expected = {
        "id", "title", "topic", "content", "status",
        "created_at", "updated_at", "last_reviewed", "completed_at",
    }
    assert expected == cap.keys()
    assert "source" not in cap
    assert "telegram_chat_id" not in cap


def test_capture_round_trip_parking_lot(storage: Path) -> None:
    """capture() returns 8 parking_lot projection fields."""
    result = capture(_parking_lot(), "user1", _SOURCE, _CHAT_ID)
    cap = result["captured"]
    expected = {
        "id", "content", "reason", "status",
        "created_at", "updated_at", "last_reviewed", "completed_at",
    }
    assert expected == cap.keys()
    assert "source" not in cap
    assert "telegram_chat_id" not in cap


# ---------------------------------------------------------------------------
# System stamp tests
# ---------------------------------------------------------------------------

def test_capture_stamps_system_fields(storage: Path) -> None:
    """On-disk record has id, created_at==updated_at, status==open, nulls."""
    capture(_task(), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    stored = _read_jsonl(tasks_file)[0]
    assert _UUID4_RE.match(stored["id"])
    assert stored["created_at"] == stored["updated_at"]
    assert stored["status"] == "open"
    assert stored["completed_at"] is None
    assert stored["last_reviewed"] is None


def test_capture_persists_channel_fields(storage: Path, monkeypatch) -> None:
    """Channel fields from env (via main()) land in on-disk record."""
    monkeypatch.setenv("OPENCLAW_CHANNEL_TYPE", "telegram_text")
    monkeypatch.setenv("OPENCLAW_CHANNEL_PEER_ID", "8712103657")
    monkeypatch.setenv("OPENCLAW_USER_ID", "user1")

    inp = json.dumps({"record": _task()})
    with patch.object(sys, "argv", ["capture.py", inp]):
        with pytest.raises(SystemExit):
            main()

    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    stored = _read_jsonl(tasks_file)[0]
    assert stored["source"] == "telegram_text"
    assert stored["telegram_chat_id"] == "8712103657"


def test_capture_submission_invalid(storage: Path) -> None:
    """Missing required submission field raises GTDError('submission_invalid')
    before write() is called (no record stored on disk)."""
    with pytest.raises(GTDError) as exc_info:
        capture(_task(title=""), "user1", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "submission_invalid"
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert not tasks_file.exists()


# ---------------------------------------------------------------------------
# Existing behavioral tests — updated for new API
# ---------------------------------------------------------------------------

def test_capture_record_stored_in_jsonl(storage: Path) -> None:
    result = capture(_task(title="Buy watch parts", context="@errands"),
                     "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 1
    assert records[0]["id"] == result["captured"]["id"]
    assert records[0]["title"] == "Buy watch parts"


def test_capture_unknown_record_type_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        capture({"record_type": "widget", "title": "x"}, "user1", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "unknown_record_type"


def test_capture_empty_user_id_raises_internal_error(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        capture(_task(), "", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "internal_error"


def test_capture_storage_io_failure_raises(storage: Path) -> None:
    with patch("write._append_jsonl_fsync", side_effect=OSError("no space")):
        with pytest.raises(GTDError) as exc_info:
            capture(_task(), "user1", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "storage_io_failed"


def test_capture_task_with_waiting_for(storage: Path) -> None:
    result = capture(_task(waiting_for="Alex"), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert records[0]["waiting_for"] == "Alex"
    assert "captured" in result


def test_capture_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    result = capture(_task(), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    cap_span = next((s for s in spans if s.name == "gtd.capture"), None)
    assert cap_span is not None
    attrs = dict(cap_span.attributes)
    assert attrs.get("capture.record_type") == "task"
    assert attrs.get("capture.record_id") == result["captured"]["id"]


def test_capture_span_is_ancestor_of_write_and_validate(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    capture(_task(), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    cap_span   = next((s for s in spans if s.name == "gtd.capture"), None)
    write_span = next((s for s in spans if s.name == "gtd.write"), None)
    val_span   = next((s for s in spans
                       if s.name in ("gtd.validate_submission", "gtd.validate_storage")), None)

    assert cap_span is not None,   f"missing gtd.capture in {names}"
    assert write_span is not None, f"missing gtd.write in {names}"
    assert val_span is not None,   f"missing validate span in {names}"

    assert write_span.parent.span_id == cap_span.get_span_context().span_id


def test_capture_span_has_error_status_on_failure(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        capture(_task(title=""), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    cap_span = next((s for s in spans if s.name == "gtd.capture"), None)
    assert cap_span is not None
    assert cap_span.status.status_code == StatusCode.ERROR


def test_main_invalid_json_emits_err_envelope(
    storage: Path, capsys: pytest.CaptureFixture
) -> None:
    with patch.object(sys, "argv", ["capture.py", "{ not valid json }"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["error"]["code"] == "internal_error"


def test_two_captures_produce_distinct_ids(storage: Path) -> None:
    r1 = capture(_task(title="First"), "user1", _SOURCE, _CHAT_ID)
    r2 = capture(_task(title="Second"), "user1", _SOURCE, _CHAT_ID)
    assert r1["captured"]["id"] != r2["captured"]["id"]
