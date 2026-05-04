"""Tests for scripts/gtd/write.py -- Z3 version.

write() now returns the full stamped storage dict (not just record_id).
New args: source and telegram_chat_id (channel fields). System stamping
covers id, created_at, updated_at, status, completed_at, last_reviewed.
Atomic write via _append_jsonl_fsync (not append_jsonl).
"""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from common import GTDError
from write import write


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_SOURCE = "telegram_text"
_CHAT_ID = "8712103657"


def _task(**overrides) -> dict:
    base = {
        "record_type": "task",
        "title":       "Submit the quarterly report",
        "context":     "@computer",
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {
        "record_type": "idea",
        "title":       "Automate the listing workflow",
        "content":     "Use n8n to pull invoice data automatically",
    }
    return {**base, **overrides}


def _parking_lot(**overrides) -> dict:
    base = {
        "record_type": "parking_lot",
        "content":     "Some parked item",
    }
    return {**base, **overrides}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Successful task write returns full dict with UUID id
# ---------------------------------------------------------------------------

def test_task_write_returns_full_dict(storage: Path) -> None:
    result = write(_task(), "user1", _SOURCE, _CHAT_ID)
    assert isinstance(result, dict)
    assert _UUID4_RE.match(result["id"])


# ---------------------------------------------------------------------------
# 2. Successful idea write returns full dict
# ---------------------------------------------------------------------------

def test_idea_write_returns_full_dict(storage: Path) -> None:
    result = write(_idea(), "user1", _SOURCE, _CHAT_ID)
    assert isinstance(result, dict)
    assert _UUID4_RE.match(result["id"])


# ---------------------------------------------------------------------------
# 3. Write generates id, created_at, updated_at (== created_at at create)
# ---------------------------------------------------------------------------

def test_write_generates_id_and_timestamps(storage: Path) -> None:
    result = write(_task(), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert tasks_file.exists()
    records = _read_jsonl(tasks_file)
    assert len(records) == 1
    stored = records[0]
    assert stored["id"] == result["id"]
    assert _UUID4_RE.match(stored["id"])
    assert stored["created_at"]
    assert stored["updated_at"] == stored["created_at"]


# ---------------------------------------------------------------------------
# 4. Write creates user directory if absent
# ---------------------------------------------------------------------------

def test_write_creates_user_directory(storage: Path) -> None:
    new_user = "brand-new-user"
    write(_task(), new_user, _SOURCE, _CHAT_ID)
    assert (storage / "gtd-agent" / "users" / new_user).is_dir()


# ---------------------------------------------------------------------------
# 5. Invalid record (empty title) raises GTDError(validation_failed)
# ---------------------------------------------------------------------------

def test_write_invalid_record_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(title=""), "user1", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "validation_failed"
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert not tasks_file.exists()


# ---------------------------------------------------------------------------
# 6. Written record round-trips; no user_id in storage (Q2)
# ---------------------------------------------------------------------------

def test_write_round_trip(storage: Path) -> None:
    result = write(_task(title="Call customs broker", context="@phone"),
                   "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    stored = records[0]
    assert stored["title"] == "Call customs broker"
    assert stored["context"] == "@phone"
    assert stored["record_type"] == "task"
    assert stored["id"] == result["id"]
    assert "user_id" not in stored


# ---------------------------------------------------------------------------
# 7. Two sequential writes append correctly
# ---------------------------------------------------------------------------

def test_two_sequential_writes(storage: Path) -> None:
    write(_task(title="Task one"), "user1", _SOURCE, _CHAT_ID)
    write(_task(title="Task two"), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 2
    assert records[0]["title"] == "Task one"
    assert records[1]["title"] == "Task two"


# ---------------------------------------------------------------------------
# 8. Empty requesting_user_id raises GTDError(internal_error)
# ---------------------------------------------------------------------------

def test_empty_requesting_user_id_raises_internal_error(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(), "", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 9. Parking lot write goes to parking-lot.jsonl
# ---------------------------------------------------------------------------

def test_parking_lot_write(storage: Path) -> None:
    result = write(_parking_lot(), "user1", _SOURCE, _CHAT_ID)
    pl_file = storage / "gtd-agent" / "users" / "user1" / "parking-lot.jsonl"
    assert pl_file.exists()
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 10. Unsupported record_type raises GTDError(unknown_record_type)
# ---------------------------------------------------------------------------

def test_unsupported_record_type_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write({"record_type": "profile"}, "user1", _SOURCE, _CHAT_ID)
    assert exc_info.value.code == "unknown_record_type"


# ---------------------------------------------------------------------------
# 11. GTDError(validation_failed) carries structured errors list
# ---------------------------------------------------------------------------

def test_validation_failed_carries_errors_field(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(title=""), "user1", _SOURCE, _CHAT_ID)
    exc = exc_info.value
    assert "errors" in exc.fields
    assert isinstance(exc.fields["errors"], list)
    assert len(exc.fields["errors"]) >= 1
    first = exc.fields["errors"][0]
    assert "field" in first
    assert "message" in first


# ---------------------------------------------------------------------------
# 12. GTDError(unknown_record_type) carries provided and allowed fields
# ---------------------------------------------------------------------------

def test_unknown_record_type_carries_details(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write({"record_type": "widget"}, "user1", _SOURCE, _CHAT_ID)
    exc = exc_info.value
    assert exc.fields.get("provided") == "widget"
    assert isinstance(exc.fields.get("allowed"), list)


# ---------------------------------------------------------------------------
# 13. OTEL span emitted on success with write.record_type and write.record_id
# ---------------------------------------------------------------------------

def test_write_emits_otel_span_on_success(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    result = write(_task(), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "write" in s.name), None)
    assert span is not None, f"no write span in {[s.name for s in spans]}"
    attrs = dict(span.attributes)
    assert attrs.get("write.record_type") == "task"
    assert attrs.get("write.record_id") == result["id"]


# ---------------------------------------------------------------------------
# 14. OTEL span has no write.record_id on failure
# ---------------------------------------------------------------------------

def test_write_span_no_record_id_on_failure(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        write(_task(title=""), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "gtd.write" in s.name), None)
    assert span is not None
    assert "write.record_id" not in dict(span.attributes)
    assert span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# 15 (new). write() returns full stamped storage dict with all 16 task fields
# ---------------------------------------------------------------------------

def test_write_returns_full_record(storage: Path) -> None:
    result = write(_task(), "user1", _SOURCE, _CHAT_ID)
    assert isinstance(result, dict)
    expected = {
        "id", "record_type", "title", "context", "project", "priority",
        "waiting_for", "due_date", "notes", "status", "created_at",
        "updated_at", "last_reviewed", "completed_at", "source", "telegram_chat_id",
    }
    assert expected == result.keys()


# ---------------------------------------------------------------------------
# 16. record_type is read from record dict
# ---------------------------------------------------------------------------

def test_record_type_from_record_dict(storage: Path) -> None:
    result = write(_task(), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert records[0]["record_type"] == "task"
    assert records[0]["id"] == result["id"]


# ---------------------------------------------------------------------------
# 17 (new). source and telegram_chat_id args persisted in JSONL record
# ---------------------------------------------------------------------------

def test_write_channel_fields_persisted(storage: Path) -> None:
    write(_task(), "user1", source="telegram_text", telegram_chat_id="8712103657")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    stored = records[0]
    assert stored["source"] == "telegram_text"
    assert stored["telegram_chat_id"] == "8712103657"


# ---------------------------------------------------------------------------
# 18 (new). System fields stamped correctly at create
# ---------------------------------------------------------------------------

def test_write_stamps_system_fields(storage: Path) -> None:
    result = write(_task(), "user1", _SOURCE, _CHAT_ID)
    assert _UUID4_RE.match(result["id"])
    assert result["created_at"] == result["updated_at"]
    assert result["status"] == "open"
    assert result["completed_at"] is None
    assert result["last_reviewed"] is None


# ---------------------------------------------------------------------------
# 19 (new). Two writes via append-with-fsync: both records preserved
# ---------------------------------------------------------------------------

def test_write_fsync_two_records(storage: Path) -> None:
    r1 = write(_task(title="First task"), "user1", _SOURCE, _CHAT_ID)
    r2 = write(_task(title="Second task"), "user1", _SOURCE, _CHAT_ID)
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 2
    ids = {r["id"] for r in records}
    assert r1["id"] in ids
    assert r2["id"] in ids


# ---------------------------------------------------------------------------
# 20. OSError from _append_jsonl_fsync raises GTDError(storage_io_failed)
# ---------------------------------------------------------------------------

def test_storage_io_failure_raises_gtd_error(storage: Path) -> None:
    with patch("write._append_jsonl_fsync", side_effect=OSError("disk full")):
        with pytest.raises(GTDError) as exc_info:
            write(_task(), "user1", _SOURCE, _CHAT_ID)
    exc = exc_info.value
    assert exc.code == "storage_io_failed"
    assert "path" in exc.fields
    assert exc.fields.get("error_type") == "OSError"


# ---------------------------------------------------------------------------
# 21. write span is a child when invoked inside an active span
# ---------------------------------------------------------------------------

def test_write_span_is_child_when_parent_active(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    tracer = otel_common.get_tracer("test.parent")
    with tracer.start_as_current_span("test.parent") as parent:
        parent_span_id = parent.get_span_context().span_id
        write(_task(), "user1", _SOURCE, _CHAT_ID)

    spans = exporter.get_finished_spans()
    write_span = next((s for s in spans if s.name == "gtd.write"), None)
    assert write_span is not None, f"no gtd.write span in {[s.name for s in spans]}"
    assert write_span.parent is not None
    assert write_span.parent.span_id == parent_span_id
