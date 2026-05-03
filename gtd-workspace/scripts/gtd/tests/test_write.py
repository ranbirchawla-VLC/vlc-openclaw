"""Tests for scripts/gtd/write.py.

Fixtures updated to the simplified 2b.2 record shapes (no user_id, no updated_at,
no dropped fields). Tests 8 and 12 removed (isolation_mismatch / isolation_violation)
as assert_user_match is replaced by the empty-requesting_user_id guard. One new test
added for the empty-guard path.
Total: 18 tests.
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


# ---------------------------------------------------------------------------
# Fixtures — minimal records matching the simplified locked shapes.
# write() stamps id and created_at; tests do not supply them.
# ---------------------------------------------------------------------------

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
# 3. Write generates id and created_at in the stored record (no updated_at)
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
    assert "updated_at" not in stored


# ---------------------------------------------------------------------------
# 4. Write creates user directory if absent
# ---------------------------------------------------------------------------

def test_write_creates_user_directory(storage: Path) -> None:
    new_user = "brand-new-user"
    write(_task(), new_user)
    assert (storage / "gtd-agent" / "users" / new_user).is_dir()


# ---------------------------------------------------------------------------
# 5. Invalid record raises GTDError(validation_failed)
# ---------------------------------------------------------------------------

def test_write_invalid_record_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(title=""), "user1")
    assert exc_info.value.code == "validation_failed"
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert not tasks_file.exists()


# ---------------------------------------------------------------------------
# 6. Written record round-trips correctly (no user_id in storage per Q2)
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
    assert stored["id"] == record_id
    assert "user_id" not in stored


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
# 8 (new). Empty requesting_user_id raises GTDError(internal_error)
# ---------------------------------------------------------------------------

def test_empty_requesting_user_id_raises_internal_error(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(), "")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 9. Parking lot write goes to parking-lot.jsonl (title field, not raw_text)
# ---------------------------------------------------------------------------

def test_parking_lot_write(storage: Path) -> None:
    record = {
        "record_type": "parking_lot",
        "title":       "some random thought I had",
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
        write({"record_type": "profile"}, "user1")
    assert exc_info.value.code == "unknown_record_type"


# ---------------------------------------------------------------------------
# 11. GTDError(validation_failed) carries structured errors field
# ---------------------------------------------------------------------------

def test_validation_failed_carries_errors_field(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        write(_task(title=""), "user1")
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
        write({"record_type": "widget"}, "user1")
    exc = exc_info.value
    assert exc.fields.get("provided") == "widget"
    assert isinstance(exc.fields.get("allowed"), list)


# ---------------------------------------------------------------------------
# 13. OTEL span emitted on successful write with write.record_type and write.record_id
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
# 14. OTEL span has no write.record_id on failure
# ---------------------------------------------------------------------------

def test_write_span_no_record_id_on_failure(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        write(_task(title=""), "user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "gtd.write" in s.name), None)
    assert span is not None
    assert "write.record_id" not in dict(span.attributes)
    assert span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# 15. write() result is a UUID4 string (not a dict)
# ---------------------------------------------------------------------------

def test_write_returns_str_not_dict(storage: Path) -> None:
    result = write(_task(), "user1")
    assert isinstance(result, str)
    assert not isinstance(result, dict)


# ---------------------------------------------------------------------------
# 16. record_type is read from record dict (no separate parameter)
# ---------------------------------------------------------------------------

def test_record_type_from_record_dict(storage: Path) -> None:
    record = _task()
    record["record_type"] = "task"
    record_id = write(record, "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert records[0]["record_type"] == "task"
    assert records[0]["id"] == record_id


# ---------------------------------------------------------------------------
# 17. OSError from append_jsonl raises GTDError(storage_io_failed)
# ---------------------------------------------------------------------------

def test_storage_io_failure_raises_gtd_error(storage: Path) -> None:
    with patch("write.append_jsonl", side_effect=OSError("disk full")):
        with pytest.raises(GTDError) as exc_info:
            write(_task(), "user1")
    exc = exc_info.value
    assert exc.code == "storage_io_failed"
    assert "path" in exc.fields
    assert exc.fields.get("error_type") == "OSError"


# ---------------------------------------------------------------------------
# 18. write span is a child when invoked inside an active span
# ---------------------------------------------------------------------------

def test_write_span_is_child_when_parent_active(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    tracer = otel_common.get_tracer("test.parent")
    with tracer.start_as_current_span("test.parent") as parent:
        parent_span_id = parent.get_span_context().span_id
        write(_task(), "user1")

    spans = exporter.get_finished_spans()
    write_span = next((s for s in spans if s.name == "gtd.write"), None)
    assert write_span is not None, f"no gtd.write span in {[s.name for s in spans]}"
    assert write_span.parent is not None, "expected write span to be a child"
    assert write_span.parent.span_id == parent_span_id
