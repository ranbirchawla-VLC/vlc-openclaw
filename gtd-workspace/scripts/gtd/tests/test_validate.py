"""Tests for scripts/gtd/validate.py.

20 behavioral tests ported from gtd-workspace/tests/test_validate.py
(argument order swap + attribute access rewrite).
3 new tests for the typed Pydantic contract and OTEL span.
"""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from validate import FieldError, ValidationResult, validate


# ---------------------------------------------------------------------------
# Fixtures — minimal valid records (same data as legacy tests)
# ---------------------------------------------------------------------------

def _task(**overrides) -> dict:
    base = {
        "id":               "abc-123",
        "record_type":      "task",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Call the customs broker",
        "context":          "@phone",
        "area":             "business",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       "2026-04-12T10:00:00+00:00",
        "updated_at":       "2026-04-12T10:00:00+00:00",
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {
        "id":               "abc-456",
        "record_type":      "idea",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Build a watch scanner agent",
        "domain":           "ai-automation",
        "context":          "@computer",
        "review_cadence":   "monthly",
        "promotion_state":  "incubating",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       "2026-04-12T10:00:00+00:00",
        "updated_at":       "2026-04-12T10:00:00+00:00",
        "spark_note":       None,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }
    return {**base, **overrides}


def _parking_lot(**overrides) -> dict:
    base = {
        "id":               "abc-789",
        "record_type":      "parking_lot",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "raw_text":         "some random thought",
        "source":           "telegram_text",
        "reason":           "ambiguous_capture",
        "status":           "active",
        "created_at":       "2026-04-12T10:00:00+00:00",
        "updated_at":       "2026-04-12T10:00:00+00:00",
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
# 3. Valid parking lot passes
# ---------------------------------------------------------------------------

def test_valid_parking_lot_passes() -> None:
    r = validate("parking_lot", _parking_lot())
    assert r.valid is True
    assert r.errors == []


# ---------------------------------------------------------------------------
# 4. Missing required field (user_id) fails
# ---------------------------------------------------------------------------

def test_missing_user_id_fails() -> None:
    record = _task()
    del record["user_id"]
    r = validate("task", record)
    assert r.valid is False
    assert any(e.field == "user_id" for e in r.errors)


# ---------------------------------------------------------------------------
# 5. Active task with empty context fails (business rule)
# ---------------------------------------------------------------------------

def test_active_task_empty_context_fails() -> None:
    r = validate("task", _task(context=""))
    assert r.valid is False
    assert any(e.field == "context" for e in r.errors)
    assert any("context" in e.message.lower() for e in r.errors)


# ---------------------------------------------------------------------------
# 6. Invalid priority enum fails
# ---------------------------------------------------------------------------

def test_invalid_priority_fails() -> None:
    r = validate("task", _task(priority="super-urgent"))
    assert r.valid is False
    assert any(e.field == "priority" for e in r.errors)


# ---------------------------------------------------------------------------
# 7. Invalid status enum fails
# ---------------------------------------------------------------------------

def test_invalid_status_fails() -> None:
    r = validate("task", _task(status="in_progress"))
    assert r.valid is False
    assert any(e.field == "status" for e in r.errors)


# ---------------------------------------------------------------------------
# 8. completed_at set on non-done task fails
# ---------------------------------------------------------------------------

def test_completed_at_on_active_task_fails() -> None:
    r = validate("task", _task(completed_at="2026-04-12T11:00:00+00:00"))
    assert r.valid is False
    assert any(e.field == "completed_at" for e in r.errors)


# ---------------------------------------------------------------------------
# 9. completed_at set on done task passes
# ---------------------------------------------------------------------------

def test_completed_at_on_done_task_passes() -> None:
    r = validate("task", _task(status="done", completed_at="2026-04-12T11:00:00+00:00"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 10. delegated without delegate_to fails
# ---------------------------------------------------------------------------

def test_delegated_without_delegate_to_fails() -> None:
    r = validate("task", _task(status="delegated", delegate_to=None))
    assert r.valid is False
    assert any(e.field == "delegate_to" for e in r.errors)


# ---------------------------------------------------------------------------
# 11. waiting without waiting_for fails
# ---------------------------------------------------------------------------

def test_waiting_without_waiting_for_fails() -> None:
    r = validate("task", _task(status="waiting", waiting_for=None))
    assert r.valid is False
    assert any(e.field == "waiting_for" for e in r.errors)


# ---------------------------------------------------------------------------
# 12. Empty title fails
# ---------------------------------------------------------------------------

def test_empty_title_fails() -> None:
    r = validate("task", _task(title=""))
    assert r.valid is False
    assert any(e.field == "title" for e in r.errors)


# ---------------------------------------------------------------------------
# 13. Wrong record_type value in record fails
# ---------------------------------------------------------------------------

def test_wrong_record_type_value_fails() -> None:
    r = validate("task", _task(record_type="idea"))
    assert r.valid is False
    assert any(e.field == "record_type" for e in r.errors)


# ---------------------------------------------------------------------------
# 14. Unknown record_type argument returns invalid result
# ---------------------------------------------------------------------------

def test_unknown_record_type_returns_invalid() -> None:
    r = validate("widget", {"some": "data"})
    assert r.valid is False


# ---------------------------------------------------------------------------
# 15. Delegated with delegate_to passes
# ---------------------------------------------------------------------------

def test_delegated_with_delegate_to_passes() -> None:
    r = validate("task", _task(status="delegated", delegate_to="Alex"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 16. Waiting with waiting_for passes
# ---------------------------------------------------------------------------

def test_waiting_with_waiting_for_passes() -> None:
    r = validate("task", _task(status="waiting", waiting_for="Alex"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 17. Done task with empty context passes (active rule not enforced)
# ---------------------------------------------------------------------------

def test_done_task_empty_context_passes() -> None:
    r = validate("task", _task(status="done", context="", completed_at="2026-04-12T11:00:00+00:00"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 18. Invalid source enum fails
# ---------------------------------------------------------------------------

def test_invalid_source_fails() -> None:
    r = validate("task", _task(source="whatsapp"))
    assert r.valid is False
    assert any(e.field == "source" for e in r.errors)


# ---------------------------------------------------------------------------
# 19. Invalid idea review_cadence fails
# ---------------------------------------------------------------------------

def test_invalid_review_cadence_fails() -> None:
    r = validate("idea", _idea(review_cadence="daily"))
    assert r.valid is False
    assert any(e.field == "review_cadence" for e in r.errors)


# ---------------------------------------------------------------------------
# 20. Idea with promoted_task_id passes
# ---------------------------------------------------------------------------

def test_idea_with_promoted_task_id_passes() -> None:
    r = validate("idea", _idea(promotion_state="promoted_to_task", promoted_task_id="task-999"))
    assert r.valid is True


# ---------------------------------------------------------------------------
# 21 (new). ValidationResult and FieldError are Pydantic model instances
# ---------------------------------------------------------------------------

def test_returns_pydantic_models() -> None:
    r = validate("task", _task())
    assert isinstance(r, ValidationResult)

    r_bad = validate("task", _task(priority="super-urgent"))
    assert isinstance(r_bad, ValidationResult)
    assert all(isinstance(e, FieldError) for e in r_bad.errors)


# ---------------------------------------------------------------------------
# 22 (new). OTEL span with validate.record_type, validate.valid, validate.error_count
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
# 23 (new). OTEL span with error attributes on validation failure
# ---------------------------------------------------------------------------

def test_validate_span_on_failure() -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    validate("task", _task(priority="bad"))

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if "validate" in s.name), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("validate.valid") is False
    assert attrs.get("validate.error_count", 0) >= 1
    assert span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# 24 (new). validate span is a CHILD when invoked inside an active span
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
# 25 (new). whitespace user_id is caught even when other field errors also present
# ---------------------------------------------------------------------------

def test_whitespace_user_id_caught_with_other_errors() -> None:
    r = validate("task", _task(user_id="   ", priority="bad"))
    assert r.valid is False
    fields = [e.field for e in r.errors]
    assert "user_id" in fields
    assert "priority" in fields
