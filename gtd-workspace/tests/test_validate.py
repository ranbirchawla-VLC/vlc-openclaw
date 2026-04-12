"""Tests for gtd_validate.py — schema validation and business rules."""

import pytest

from gtd_validate import validate

# ---------------------------------------------------------------------------
# Fixtures — minimal valid records
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
# 1. Valid task record passes
# ---------------------------------------------------------------------------

def test_valid_task_passes() -> None:
    r = validate(_task(), "task")
    assert r["valid"] is True
    assert r["status"] == "ok"
    assert r["errors"] == []
    assert r["record_type"] == "task"


# ---------------------------------------------------------------------------
# 2. Valid idea record passes
# ---------------------------------------------------------------------------

def test_valid_idea_passes() -> None:
    r = validate(_idea(), "idea")
    assert r["valid"] is True
    assert r["errors"] == []


# ---------------------------------------------------------------------------
# 3. Valid parking lot record passes
# ---------------------------------------------------------------------------

def test_valid_parking_lot_passes() -> None:
    r = validate(_parking_lot(), "parking_lot")
    assert r["valid"] is True
    assert r["errors"] == []


# ---------------------------------------------------------------------------
# 4. Missing required field (user_id) fails
# ---------------------------------------------------------------------------

def test_missing_user_id_fails() -> None:
    record = _task()
    del record["user_id"]
    r = validate(record, "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "user_id" in fields


# ---------------------------------------------------------------------------
# 5. Missing context on active task fails (business rule)
# ---------------------------------------------------------------------------

def test_active_task_empty_context_fails() -> None:
    r = validate(_task(context=""), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "context" in fields
    messages = [e["message"] for e in r["errors"]]
    assert any("context" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# 6. Invalid enum value for priority fails
# ---------------------------------------------------------------------------

def test_invalid_priority_fails() -> None:
    r = validate(_task(priority="super-urgent"), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "priority" in fields


# ---------------------------------------------------------------------------
# 7. Invalid enum value for status fails
# ---------------------------------------------------------------------------

def test_invalid_status_fails() -> None:
    r = validate(_task(status="in_progress"), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "status" in fields


# ---------------------------------------------------------------------------
# 8. completed_at set on non-done task fails
# ---------------------------------------------------------------------------

def test_completed_at_on_active_task_fails() -> None:
    r = validate(_task(completed_at="2026-04-12T11:00:00+00:00"), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "completed_at" in fields


# ---------------------------------------------------------------------------
# 9. completed_at set on done task passes
# ---------------------------------------------------------------------------

def test_completed_at_on_done_task_passes() -> None:
    r = validate(_task(status="done", completed_at="2026-04-12T11:00:00+00:00"), "task")
    assert r["valid"] is True


# ---------------------------------------------------------------------------
# 10. status = delegated without delegate_to fails
# ---------------------------------------------------------------------------

def test_delegated_without_delegate_to_fails() -> None:
    r = validate(_task(status="delegated", delegate_to=None), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "delegate_to" in fields


# ---------------------------------------------------------------------------
# 11. status = waiting without waiting_for fails
# ---------------------------------------------------------------------------

def test_waiting_without_waiting_for_fails() -> None:
    r = validate(_task(status="waiting", waiting_for=None), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "waiting_for" in fields


# ---------------------------------------------------------------------------
# 12. Empty string for title fails
# ---------------------------------------------------------------------------

def test_empty_title_fails() -> None:
    r = validate(_task(title=""), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "title" in fields


# ---------------------------------------------------------------------------
# 13. Wrong record_type value fails
# ---------------------------------------------------------------------------

def test_wrong_record_type_fails() -> None:
    r = validate(_task(record_type="idea"), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "record_type" in fields


# ---------------------------------------------------------------------------
# 14. Unknown record_type returns error
# ---------------------------------------------------------------------------

def test_unknown_record_type_returns_error() -> None:
    r = validate({"some": "data"}, "widget")
    assert r["valid"] is False
    assert r["status"] == "error"


# ---------------------------------------------------------------------------
# 15. Delegated task with delegate_to passes
# ---------------------------------------------------------------------------

def test_delegated_with_delegate_to_passes() -> None:
    r = validate(_task(status="delegated", delegate_to="Alex"), "task")
    assert r["valid"] is True


# ---------------------------------------------------------------------------
# 16. Waiting task with waiting_for passes
# ---------------------------------------------------------------------------

def test_waiting_with_waiting_for_passes() -> None:
    r = validate(_task(status="waiting", waiting_for="Alex"), "task")
    assert r["valid"] is True


# ---------------------------------------------------------------------------
# 17. Done task with no context passes (non-active tasks: context not enforced)
# ---------------------------------------------------------------------------

def test_done_task_empty_context_passes() -> None:
    r = validate(_task(status="done", context="", completed_at="2026-04-12T11:00:00+00:00"), "task")
    assert r["valid"] is True


# ---------------------------------------------------------------------------
# 18. Invalid source enum fails
# ---------------------------------------------------------------------------

def test_invalid_source_fails() -> None:
    r = validate(_task(source="whatsapp"), "task")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "source" in fields


# ---------------------------------------------------------------------------
# 19. Invalid idea review_cadence fails
# ---------------------------------------------------------------------------

def test_invalid_review_cadence_fails() -> None:
    r = validate(_idea(review_cadence="daily"), "idea")
    assert r["valid"] is False
    fields = [e["field"] for e in r["errors"]]
    assert "review_cadence" in fields


# ---------------------------------------------------------------------------
# 20. Idea with promoted_task_id set passes
# ---------------------------------------------------------------------------

def test_idea_with_promoted_task_id_passes() -> None:
    r = validate(_idea(promotion_state="promoted_to_task", promoted_task_id="task-999"), "idea")
    assert r["valid"] is True
