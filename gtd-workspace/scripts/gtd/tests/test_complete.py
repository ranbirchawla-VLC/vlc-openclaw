"""Tests for scripts/gtd/complete.py.

12 tests covering: happy path task, happy path idea, record_not_found,
already_completed, unsupported_record_type (parking_lot), storage_io_failed,
empty user_id, OTEL span attrs, OTEL error status on failure, atomic rewrite
integrity, main() CLI round-trip, projection contract.

Production failure modes each test guards against:
  - Silent non-completion: status field not updated on disk
  - Stale timestamps: updated_at/completed_at not stamped on completion
  - Double-complete: already-completed record silently re-stamped
  - Wrong type: parking_lot accepted without error
  - Corrupt state: crash during rewrite leaves partial file
  - Missing error span: GTDError not recorded in OTEL trace
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from complete import complete, main
from common import GTDError
import otel_common as _oc


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_USER = "user1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_task(storage: Path, **overrides) -> dict:
    """Write an open task record to storage and return it."""
    from write import write
    record = {"record_type": "task", "title": "Call the broker", **overrides}
    return write(record, _USER, "telegram", _USER)


def _seed_idea(storage: Path, **overrides) -> dict:
    """Write an open idea record to storage and return it."""
    from write import write
    record = {"record_type": "idea", "title": "New feature", "content": "Build it", **overrides}
    return write(record, _USER, "telegram", _USER)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _tasks_path(storage: Path) -> Path:
    return storage / "gtd-agent" / "users" / _USER / "tasks.jsonl"


def _ideas_path(storage: Path) -> Path:
    return storage / "gtd-agent" / "users" / _USER / "ideas.jsonl"


# ---------------------------------------------------------------------------
# Test 1: happy path — task
# ---------------------------------------------------------------------------

def test_complete_task_returns_projection(storage: Path) -> None:
    """complete() returns {"completed": <13-field task projection>} with status=completed.

    Production failure: no complete tool; Trina tells user she can't close items.
    Fails RED without complete.py present.
    """
    stored = _seed_task(storage)
    result = complete(stored["id"], "task", _USER)

    assert "completed" in result
    proj = result["completed"]
    expected_keys = {
        "id", "title", "context", "project", "priority", "waiting_for",
        "due_date", "notes", "status", "created_at", "updated_at",
        "last_reviewed", "completed_at",
    }
    assert expected_keys == proj.keys()
    assert proj["status"] == "completed"
    assert proj["completed_at"] is not None
    assert proj["updated_at"] >= stored["updated_at"]
    # channel fields must not appear in projection
    assert "source" not in proj
    assert "telegram_chat_id" not in proj
    assert "record_type" not in proj


# ---------------------------------------------------------------------------
# Test 2: happy path — idea
# ---------------------------------------------------------------------------

def test_complete_idea_returns_projection(storage: Path) -> None:
    """complete() returns {"completed": <9-field idea projection>} with status=completed."""
    stored = _seed_idea(storage)
    result = complete(stored["id"], "idea", _USER)

    proj = result["completed"]
    expected_keys = {
        "id", "title", "topic", "content", "status",
        "created_at", "updated_at", "last_reviewed", "completed_at",
    }
    assert expected_keys == proj.keys()
    assert proj["status"] == "completed"
    assert proj["completed_at"] is not None
    assert "source" not in proj
    assert "telegram_chat_id" not in proj


# ---------------------------------------------------------------------------
# Test 3: record written correctly to disk
# ---------------------------------------------------------------------------

def test_complete_stamps_disk(storage: Path) -> None:
    """On-disk record has status=completed, completed_at set, updated_at >= created_at.

    Production failure: in-memory update not persisted; reopening the list
    shows the task still open.
    """
    stored = _seed_task(storage)
    complete(stored["id"], "task", _USER)

    on_disk = _read_jsonl(_tasks_path(storage))
    assert len(on_disk) == 1
    rec = on_disk[0]
    assert rec["status"] == "completed"
    assert rec["completed_at"] is not None
    assert rec["updated_at"] >= rec["created_at"]


# ---------------------------------------------------------------------------
# Test 4: record_not_found
# ---------------------------------------------------------------------------

def test_complete_record_not_found(storage: Path) -> None:
    """GTDError('record_not_found') raised when record_id does not exist.

    Production failure: silent success on bad ID; user told task was closed
    but nothing changed.
    """
    _seed_task(storage)
    with pytest.raises(GTDError) as exc_info:
        complete("nonexistent-id", "task", _USER)
    assert exc_info.value.code == "record_not_found"


# ---------------------------------------------------------------------------
# Test 5: already_completed
# ---------------------------------------------------------------------------

def test_complete_already_completed(storage: Path) -> None:
    """GTDError('already_completed') raised when record is already done.

    Production failure: double-complete silently re-stamps timestamps;
    completed_at drifts from actual completion time.
    """
    stored = _seed_task(storage)
    complete(stored["id"], "task", _USER)

    with pytest.raises(GTDError) as exc_info:
        complete(stored["id"], "task", _USER)
    assert exc_info.value.code == "already_completed"


# ---------------------------------------------------------------------------
# Test 6: unsupported_record_type (parking_lot)
# ---------------------------------------------------------------------------

def test_complete_parking_lot_unsupported(storage: Path) -> None:
    """GTDError('unsupported_record_type') raised for parking_lot.

    Production failure: parking_lot accepted silently; schema violation written
    to disk (status field only allows 'open' in storage model until 2d).
    """
    with pytest.raises(GTDError) as exc_info:
        complete("any-id", "parking_lot", _USER)
    assert exc_info.value.code == "unsupported_record_type"


# ---------------------------------------------------------------------------
# Test 7: empty user_id
# ---------------------------------------------------------------------------

def test_complete_empty_user_id(storage: Path) -> None:
    """GTDError('internal_error') raised when requesting_user_id is empty."""
    _seed_task(storage)
    with pytest.raises(GTDError) as exc_info:
        complete("any-id", "task", "")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# Test 8: storage_io_failed
# ---------------------------------------------------------------------------

def test_complete_storage_io_failed(storage: Path) -> None:
    """GTDError('storage_io_failed') raised on OSError during rewrite.

    Production failure: disk full or permission error silently swallowed;
    task appears complete in response but unchanged on disk.
    """
    stored = _seed_task(storage)
    with patch("complete._rewrite_jsonl_atomic", side_effect=OSError("disk full")):
        with pytest.raises(GTDError) as exc_info:
            complete(stored["id"], "task", _USER)
    assert exc_info.value.code == "storage_io_failed"


# ---------------------------------------------------------------------------
# Test 9: OTEL span attributes
# ---------------------------------------------------------------------------

def test_complete_span_attributes(storage: Path) -> None:
    """Span 'gtd.complete' emits record_type and record_id attributes.

    Production failure: missing attributes; Honeycomb query for completed
    records by type or id returns no results.
    """
    exporter = InMemorySpanExporter()
    _oc.configure_tracer_provider(exporter)

    stored = _seed_task(storage)
    complete(stored["id"], "task", _USER)

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.complete")
    attrs = dict(span.attributes)
    assert attrs["complete.record_type"] == "task"
    assert attrs["complete.record_id"] == stored["id"]
    assert attrs["tool.name"] == "complete"


# ---------------------------------------------------------------------------
# Test 10: OTEL error status on failure
# ---------------------------------------------------------------------------

def test_complete_span_error_status_on_not_found(storage: Path) -> None:
    """Span status is ERROR and exception is recorded when record_not_found raised.

    Production failure: error path missing span.record_exception / set_status;
    Honeycomb shows successful span for a failed operation.
    """
    exporter = InMemorySpanExporter()
    _oc.configure_tracer_provider(exporter)

    _seed_task(storage)
    with pytest.raises(GTDError):
        complete("bad-id", "task", _USER)

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.complete")
    assert span.status.status_code == StatusCode.ERROR
    assert len(span.events) > 0  # record_exception emits a span event


# ---------------------------------------------------------------------------
# Test 11: atomic rewrite — other records preserved
# ---------------------------------------------------------------------------

def test_complete_atomic_rewrite_preserves_other_records(storage: Path) -> None:
    """Completing one record does not remove other records from the JSONL file.

    Production failure: full-file rewrite bug truncates unrelated records;
    user loses tasks not related to the completed one.
    """
    stored_a = _seed_task(storage, title="Task A")
    stored_b = _seed_task(storage, title="Task B")

    complete(stored_a["id"], "task", _USER)

    on_disk = _read_jsonl(_tasks_path(storage))
    assert len(on_disk) == 2
    ids_on_disk = {r["id"] for r in on_disk}
    assert stored_a["id"] in ids_on_disk
    assert stored_b["id"] in ids_on_disk
    completed = next(r for r in on_disk if r["id"] == stored_a["id"])
    assert completed["status"] == "completed"
    other = next(r for r in on_disk if r["id"] == stored_b["id"])
    assert other["status"] == "open"


# ---------------------------------------------------------------------------
# Test 12: main() CLI round-trip
# ---------------------------------------------------------------------------

def test_complete_main_cli_round_trip(storage: Path, capsys) -> None:
    """main() reads argv JSON, calls complete(), writes ok envelope to stdout.

    Production failure: main() missing ok() call; plugin sees empty stdout
    and treats completion as subprocess_nonzero_exit error.
    """
    stored = _seed_task(storage)
    args = json.dumps({"user_id": _USER, "record_id": stored["id"], "record_type": "task"})

    with patch.object(sys, "argv", ["complete.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["ok"] is True
    assert "completed" in output["data"]
    assert output["data"]["completed"]["status"] == "completed"
