"""Tests for scripts/gtd/capture.py."""

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from capture import capture
from common import GTDError


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _task(**overrides) -> dict:
    base = {"record_type": "task", "title": "Call the broker", "context": "@phone"}
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {"record_type": "idea", "title": "New feature idea"}
    return {**base, **overrides}


def _parking_lot(**overrides) -> dict:
    base = {"record_type": "parking_lot", "title": "Stray thought"}
    return {**base, **overrides}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Happy path — task capture returns {id, record_type}
# ---------------------------------------------------------------------------

def test_capture_task_returns_id_and_record_type(storage: Path) -> None:
    result = capture(_task(), "user1")
    assert "id" in result
    assert result["record_type"] == "task"
    assert _UUID4_RE.match(result["id"])


# ---------------------------------------------------------------------------
# 2. Happy path — idea capture
# ---------------------------------------------------------------------------

def test_capture_idea_returns_ok_shape(storage: Path) -> None:
    result = capture(_idea(), "user1")
    assert result["record_type"] == "idea"
    assert _UUID4_RE.match(result["id"])


# ---------------------------------------------------------------------------
# 3. Happy path — parking_lot capture (title field, not raw_text)
# ---------------------------------------------------------------------------

def test_capture_parking_lot_returns_ok_shape(storage: Path) -> None:
    result = capture(_parking_lot(), "user1")
    assert result["record_type"] == "parking_lot"
    assert _UUID4_RE.match(result["id"])


# ---------------------------------------------------------------------------
# 4. Record is actually written to JSONL
# ---------------------------------------------------------------------------

def test_capture_record_stored_in_jsonl(storage: Path) -> None:
    result = capture(_task(title="Buy watch parts", context="@errands"), "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert len(records) == 1
    assert records[0]["id"] == result["id"]
    assert records[0]["title"] == "Buy watch parts"


# ---------------------------------------------------------------------------
# 5. Validation failure raises GTDError(validation_failed)
# ---------------------------------------------------------------------------

def test_capture_validation_failure_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        capture(_task(title=""), "user1")
    assert exc_info.value.code == "validation_failed"


# ---------------------------------------------------------------------------
# 6. Unknown record_type raises GTDError(unknown_record_type)
# ---------------------------------------------------------------------------

def test_capture_unknown_record_type_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        capture({"record_type": "widget", "title": "x"}, "user1")
    assert exc_info.value.code == "unknown_record_type"


# ---------------------------------------------------------------------------
# 7. Empty requesting_user_id raises GTDError(internal_error)
# ---------------------------------------------------------------------------

def test_capture_empty_user_id_raises_internal_error(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        capture(_task(), "")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 8. Storage IO failure raises GTDError(storage_io_failed)
# ---------------------------------------------------------------------------

def test_capture_storage_io_failure_raises(storage: Path) -> None:
    with patch("write.append_jsonl", side_effect=OSError("no space")):
        with pytest.raises(GTDError) as exc_info:
            capture(_task(), "user1")
    assert exc_info.value.code == "storage_io_failed"


# ---------------------------------------------------------------------------
# 9. Task with waiting_for captures correctly
# ---------------------------------------------------------------------------

def test_capture_task_with_waiting_for(storage: Path) -> None:
    result = capture(_task(waiting_for="Alex"), "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    records = _read_jsonl(tasks_file)
    assert records[0]["waiting_for"] == "Alex"
    assert result["record_type"] == "task"


# ---------------------------------------------------------------------------
# 10. OTEL span emitted with capture.record_type and capture.record_id
# ---------------------------------------------------------------------------

def test_capture_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    result = capture(_task(), "user1")

    spans = exporter.get_finished_spans()
    cap_span = next((s for s in spans if s.name == "gtd.capture"), None)
    assert cap_span is not None, f"no gtd.capture span in {[s.name for s in spans]}"
    attrs = dict(cap_span.attributes)
    assert attrs.get("capture.record_type") == "task"
    assert attrs.get("capture.record_id") == result["id"]


# ---------------------------------------------------------------------------
# 11. capture span is ancestor of write and validate spans
# ---------------------------------------------------------------------------

def test_capture_span_is_ancestor_of_write_and_validate(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    capture(_task(), "user1")

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    cap_span = next((s for s in spans if s.name == "gtd.capture"), None)
    write_span = next((s for s in spans if s.name == "gtd.write"), None)
    validate_span = next((s for s in spans if s.name == "gtd.validate"), None)

    assert cap_span is not None, f"missing gtd.capture in {names}"
    assert write_span is not None, f"missing gtd.write in {names}"
    assert validate_span is not None, f"missing gtd.validate in {names}"

    assert write_span.parent.span_id == cap_span.get_span_context().span_id
    assert validate_span.parent.span_id == write_span.get_span_context().span_id


# ---------------------------------------------------------------------------
# 12. OTEL span has ERROR status on failure
# ---------------------------------------------------------------------------

def test_capture_span_has_error_status_on_failure(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        capture(_task(title=""), "user1")

    spans = exporter.get_finished_spans()
    cap_span = next((s for s in spans if s.name == "gtd.capture"), None)
    assert cap_span is not None
    assert cap_span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# 13. main() with invalid JSON emits internal_error envelope
# ---------------------------------------------------------------------------

def test_main_invalid_json_emits_err_envelope(
    storage: Path, capsys: pytest.CaptureFixture
) -> None:
    from capture import main

    with patch.object(sys, "argv", ["capture.py", "{ not valid json }"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["error"]["code"] == "internal_error"


# ---------------------------------------------------------------------------
# 14. capture returns record_type even on a minimal record
# ---------------------------------------------------------------------------

def test_capture_record_type_in_return(storage: Path) -> None:
    result = capture({"record_type": "idea", "title": "Watch AI trends"}, "user1")
    assert result["record_type"] == "idea"


# ---------------------------------------------------------------------------
# 15. Two sequential captures produce distinct ids
# ---------------------------------------------------------------------------

def test_two_captures_produce_distinct_ids(storage: Path) -> None:
    r1 = capture(_task(title="First"), "user1")
    r2 = capture(_task(title="Second"), "user1")
    assert r1["id"] != r2["id"]
