"""Tests for scripts/gtd/validate.py.

12 behavioral tests retained from 2b.1 (fixtures updated to simplified shapes).
2 new tests for the due_date field added in 2b.2.
Total: 14 tests.
"""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from validate import FieldError, ValidationResult, validate


# ---------------------------------------------------------------------------
# Fixtures — minimal valid records matching the simplified 2b.2 locked shapes
# ---------------------------------------------------------------------------

def _task(**overrides) -> dict:
    base = {
        "id":          "abc-123",
        "record_type": "task",
        "title":       "Call the customs broker",
        "context":     "@phone",
        "created_at":  "2026-04-12T10:00:00+00:00",
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {
        "id":          "abc-456",
        "record_type": "idea",
        "title":       "Build a watch scanner agent",
        "created_at":  "2026-04-12T10:00:00+00:00",
    }
    return {**base, **overrides}


def _parking_lot(**overrides) -> dict:
    base = {
        "id":          "abc-789",
        "record_type": "parking_lot",
        "title":       "some random thought",
        "created_at":  "2026-04-12T10:00:00+00:00",
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# 1. Valid task passes
# ---------------------------------------------------------------------------

def test_valid_task_passes() -> None:
    r = validate("task", _task())
    assert r.valid is True
    assert r.errors == []
    assert r.record_type == "task"


# ---------------------------------------------------------------------------
# 2. Valid idea passes
# ---------------------------------------------------------------------------

def test_valid_idea_passes() -> None:
    r = validate("idea", _idea())
    assert r.valid is True
    assert r.errors == []


# ---------------------------------------------------------------------------
# 3. Valid parking lot passes (title field, not raw_text)
# ---------------------------------------------------------------------------

def test_valid_parking_lot_passes() -> None:
    r = validate("parking_lot", _parking_lot())
    assert r.valid is True
    assert r.errors == []


# ---------------------------------------------------------------------------
# 4. Empty context fails (min_length=1 enforced at spec level)
# ---------------------------------------------------------------------------

def test_task_empty_context_fails() -> None:
    r = validate("task", _task(context=""))
    assert r.valid is False
    assert any(e.field == "context" for e in r.errors)


# ---------------------------------------------------------------------------
# 5. Empty title fails
# ---------------------------------------------------------------------------

def test_empty_title_fails() -> None:
    r = validate("task", _task(title=""))
    assert r.valid is False
    assert any(e.field == "title" for e in r.errors)


# ---------------------------------------------------------------------------
# 6. Wrong record_type value in record fails
# ---------------------------------------------------------------------------

def test_wrong_record_type_value_fails() -> None:
    r = validate("task", _task(record_type="idea"))
    assert r.valid is False
    assert any(e.field == "record_type" for e in r.errors)


# ---------------------------------------------------------------------------
# 7. Unknown record_type argument returns invalid result
# ---------------------------------------------------------------------------

def test_unknown_record_type_returns_invalid() -> None:
    r = validate("widget", {"some": "data"})
    assert r.valid is False


# ---------------------------------------------------------------------------
# 8. Task with waiting_for value passes (nullable field with non-null value)
# ---------------------------------------------------------------------------

def test_task_with_waiting_for_passes() -> None:
    r = validate("task", _task(waiting_for="Alex"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 9. Returns Pydantic model instances
# ---------------------------------------------------------------------------

def test_returns_pydantic_models() -> None:
    r = validate("task", _task())
    assert isinstance(r, ValidationResult)

    r_bad = validate("task", _task(title=""))
    assert isinstance(r_bad, ValidationResult)
    assert all(isinstance(e, FieldError) for e in r_bad.errors)


# ---------------------------------------------------------------------------
# 10. OTEL span with validate.record_type, validate.valid, validate.error_count
# ---------------------------------------------------------------------------

def test_validate_emits_otel_span() -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    validate("task", _task())

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "validate" in s.name), None)
    assert span is not None, f"no validate span in {[s.name for s in spans]}"
    attrs = dict(span.attributes)
    assert attrs.get("validate.record_type") == "task"
    assert attrs.get("validate.valid") is True
    assert attrs.get("validate.error_count") == 0


# ---------------------------------------------------------------------------
# 11. OTEL span with error attributes on validation failure
# ---------------------------------------------------------------------------

def test_validate_span_on_failure() -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    validate("task", _task(title=""))

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "validate" in s.name), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("validate.valid") is False
    assert attrs.get("validate.error_count", 0) >= 1
    assert span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# 12. validate span is a child when invoked inside an active span
# ---------------------------------------------------------------------------

def test_validate_span_is_child_when_parent_active() -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    tracer = otel_common.get_tracer("test.parent")
    with tracer.start_as_current_span("test.parent") as parent:
        parent_span_id = parent.get_span_context().span_id
        validate("task", _task())

    spans = exporter.get_finished_spans()
    validate_span = next((s for s in spans if "gtd.validate" in s.name), None)
    assert validate_span is not None, f"no gtd.validate span in {[s.name for s in spans]}"
    assert validate_span.parent is not None, "expected validate span to be a child"
    assert validate_span.parent.span_id == parent_span_id


# ---------------------------------------------------------------------------
# 13 (new). Task with due_date string passes
# ---------------------------------------------------------------------------

def test_task_with_due_date_passes() -> None:
    r = validate("task", _task(due_date="2026-06-01"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 14 (new). Task with due_date null passes (nullable field)
# ---------------------------------------------------------------------------

def test_task_with_due_date_null_passes() -> None:
    r = validate("task", _task(due_date=None))
    assert r.valid is True
