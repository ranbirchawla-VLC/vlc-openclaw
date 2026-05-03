"""Tests for scripts/gtd/write.py.

10 behavioral tests ported from gtd-workspace/tests/test_write.py
(write() returns str id; errors raise GTDError).
7 new tests for the typed contract and OTEL span.
"""

import json
import re
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from write import write


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


# ---------------------------------------------------------------------------
# Fixtures — records without id/timestamps (write generates those)
# ---------------------------------------------------------------------------

def _task(**overrides) -> dict:
    base = {
        "record_type":      "task",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Submit the quarterly report",
        "context":          "@computer",
        "area":             "business",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {
        "record_type":      "idea",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Automate the listing workflow",
        "domain":           "ai-automation",
        "context":          "@computer",
        "review_cadence":   "monthly",
        "promotion_state":  "incubating",
        "status":           "active",
        "source":           "telegram_text",
        "spark_note":       None,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }
    return {**base, **overrides}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Successful task write returns UUID id
# ---------------------------------------------------------------------------

def test_task_write_returns_id(storage: Path) -> None:
    record_id = write(_task(), "user1")
    assert isinstance(record_id, str)
    assert _UUID4_RE.match(record_id)


# ---------------------------------------------------------------------------
# 2. Successful idea write returns UUID id
# ---------------------------------------------------------------------------

def test_idea_write_returns_id(storage: Path) -> None:
    record_id = write(_idea(), "user1")
    assert isinstance(record_id, str)
    assert _UUID4_RE.match(record_id)


# ---------------------------------------------------------------------------
# 3. Write generates id and timestamps in the stored record
# ---------------------------------------------------------------------------

def test_write_generates_id_and_timestamps(storage: Path) -> None:
    record_id = write(_task(), "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert tasks_file.exists()
    records = _read_jsonl(tasks_file)
    assert len(records) == 1
    stored = records[0]
    assert stored["id"] == record_id
    assert _UUID4_RE.match(stored["id"])
    assert stored["created_at"]
    assert stored["updated_at"]


# ---------------------------------------------------------------------------
# 4. Write creates user directory if absent
# ---------------------------------------------------------------------------

def test_write_creates_user_directory(storage: Path) -> None:
    new_user = "brand-new-user"
    write(_task(user_id=new_user), new_user)
    assert (storage / "gtd-agent" / "users" / new_user).is_dir()


# ---------------------------------------------------------------------------
# 5. Invalid record raises GTDError(validation_failed)
# ---------------------------------------------------------------------------

def test_write_invalid_record_raises(storage: Path) -> None:
    bad = _task(priority="galaxy-brain")
    with pytest.raises(GTDError) as exc_info:
        write(bad, "user1")
    assert exc_info.value.code == "validation_failed"
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert not tasks_file.exists()


# ---------------------------------------------------------------------------
# 6. Written record round-trips correctly
# ---------------------------------------------------------------------------

def test_write_round_trip(storage: Path) -> None:
    record_id = write(_task(title="Call the customs broker", context="@phone"), "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 1
    stored = records[0]
    assert stored["title"] == "Call the customs broker"
    assert stored["context"] == "@phone"
    assert stored["record_type"] == "task"
    assert stored["user_id"] == "user1"
    assert stored["id"] == record_id


# ---------------------------------------------------------------------------
# 7. Two sequential writes append correctly
# ---------------------------------------------------------------------------

def test_two_sequential_writes(storage: Path) -> None:
    write(_task(title="Task one"), "user1")
    write(_task(title="Task two"), "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 2
    assert records[0]["title"] == "Task one"
    assert records[1]["title"] == "Task two"


# ---------------------------------------------------------------------------
# 8. User isolation mismatch raises GTDError(isolation_violation)
# ---------------------------------------------------------------------------

def test_isolation_mismatch_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(user_id="user1"), "user2")
    assert exc_info.value.code == "isolation_violation"


# ---------------------------------------------------------------------------
# 9. Parking lot write goes to parking-lot.jsonl
# ---------------------------------------------------------------------------

def test_parking_lot_write(storage: Path) -> None:
    record = {
        "record_type":      "parking_lot",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "raw_text":         "some random thought I had",
        "source":           "telegram_text",
        "reason":           "ambiguous_capture",
        "status":           "active",
    }
    record_id = write(record, "user1")
    pl_file = storage / "gtd-agent" / "users" / "user1" / "parking-lot.jsonl"
    assert pl_file.exists()
    assert isinstance(record_id, str)


# ---------------------------------------------------------------------------
# 10. Unsupported record_type raises GTDError(unknown_record_type)
# ---------------------------------------------------------------------------

def test_unsupported_record_type_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write({"user_id": "user1", "record_type": "profile"}, "user1")
    assert exc_info.value.code == "unknown_record_type"


# ---------------------------------------------------------------------------
# 11 (new). GTDError(validation_failed) carries structured errors field
# ---------------------------------------------------------------------------

def test_validation_failed_carries_errors_field(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(priority="galaxy-brain"), "user1")
    exc = exc_info.value
    assert "errors" in exc.fields
    assert isinstance(exc.fields["errors"], list)
    assert len(exc.fields["errors"]) >= 1
    first = exc.fields["errors"][0]
    assert "field" in first
    assert "message" in first


# ---------------------------------------------------------------------------
# 12 (new). GTDError(isolation_violation) carries record_user_id field
# ---------------------------------------------------------------------------

def test_isolation_violation_carries_record_user_id(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(user_id="alice"), "bob")
    exc = exc_info.value
    assert exc.fields.get("record_user_id") == "alice"


# ---------------------------------------------------------------------------
# 13 (new). GTDError(unknown_record_type) carries provided and allowed fields
# ---------------------------------------------------------------------------

def test_unknown_record_type_carries_details(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write({"user_id": "user1", "record_type": "widget"}, "user1")
    exc = exc_info.value
    assert exc.fields.get("provided") == "widget"
    assert isinstance(exc.fields.get("allowed"), list)


# ---------------------------------------------------------------------------
# 14 (new). OTEL span emitted on successful write with write.record_type and write.record_id
# ---------------------------------------------------------------------------

def test_write_emits_otel_span_on_success(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    record_id = write(_task(), "user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "write" in s.name), None)
    assert span is not None, f"no write span in {[s.name for s in spans]}"
    attrs = dict(span.attributes)
    assert attrs.get("write.record_type") == "task"
    assert attrs.get("write.record_id") == record_id


# ---------------------------------------------------------------------------
# 15 (new). OTEL span has no write.record_id on failure
# ---------------------------------------------------------------------------

def test_write_span_no_record_id_on_failure(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        write(_task(priority="bad"), "user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "write" in s.name), None)
    assert span is not None
    assert "write.record_id" not in dict(span.attributes)


# ---------------------------------------------------------------------------
# 16 (new). write() result is a UUID4 string (not a dict)
# ---------------------------------------------------------------------------

def test_write_returns_str_not_dict(storage: Path) -> None:
    result = write(_task(), "user1")
    assert isinstance(result, str)
    assert not isinstance(result, dict)


# ---------------------------------------------------------------------------
# 17 (new). record_type is read from record dict (no separate parameter)
# ---------------------------------------------------------------------------

def test_record_type_from_record_dict(storage: Path) -> None:
    record = _task()
    record["record_type"] = "task"
    record_id = write(record, "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert records[0]["record_type"] == "task"
    assert records[0]["id"] == record_id
