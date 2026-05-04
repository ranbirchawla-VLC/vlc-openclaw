"""test_validate.py -- validate_submission and validate_storage contract tests.

Scrubbed from 14 old unified-validate tests. Replaces with 12 tests
against the split contracts. TDD: all written before implementation;
confirmed RED against the old unified validate() before fix applied.
"""
from __future__ import annotations

from validate import validate_submission, validate_storage


# ---------------------------------------------------------------------------
# Fixtures — minimal valid records per contract
# ---------------------------------------------------------------------------

def _task_submission() -> dict:
    return {"record_type": "task", "title": "Do the thing"}


def _idea_submission() -> dict:
    return {"record_type": "idea", "title": "Great idea", "content": "The content here"}


def _parking_lot_submission() -> dict:
    return {"record_type": "parking_lot", "content": "Parked item"}


def _task_storage() -> dict:
    return {
        "id":               "uuid-task-1",
        "record_type":      "task",
        "title":            "Do the thing",
        "context":          "@work",
        "project":          "watch-business",
        "priority":         "normal",
        "waiting_for":      None,
        "due_date":         None,
        "notes":            None,
        "status":           "open",
        "created_at":       "2026-05-03T10:00:00+00:00",
        "updated_at":       "2026-05-03T10:00:00+00:00",
        "last_reviewed":    None,
        "completed_at":     None,
        "source":           "telegram_text",
        "telegram_chat_id": "8712103657",
    }


def _idea_storage() -> dict:
    return {
        "id":               "uuid-idea-1",
        "record_type":      "idea",
        "title":            "Great idea",
        "topic":            "system",
        "content":          "The content here",
        "status":           "open",
        "created_at":       "2026-05-03T10:00:00+00:00",
        "updated_at":       "2026-05-03T10:00:00+00:00",
        "last_reviewed":    None,
        "completed_at":     None,
        "source":           "telegram_text",
        "telegram_chat_id": "8712103657",
    }


def _parking_lot_storage() -> dict:
    return {
        "id":               "uuid-pl-1",
        "record_type":      "parking_lot",
        "content":          "Parked item",
        "reason":           None,
        "status":           "open",
        "created_at":       "2026-05-03T10:00:00+00:00",
        "updated_at":       "2026-05-03T10:00:00+00:00",
        "last_reviewed":    None,
        "completed_at":     None,
        "source":           "telegram_text",
        "telegram_chat_id": "8712103657",
    }


# ---------------------------------------------------------------------------
# Submission contract tests
# ---------------------------------------------------------------------------

def test_submit_task_positive():
    result = validate_submission("task", _task_submission())
    assert result.valid is True
    assert result.code == ""
    assert result.errors == []


def test_submit_task_missing_title():
    record = {k: v for k, v in _task_submission().items() if k != "title"}
    result = validate_submission("task", record)
    assert result.valid is False
    assert result.code == "submission_invalid"
    field_names = [e.field for e in result.errors]
    assert "title" in field_names


def test_submit_idea_positive():
    result = validate_submission("idea", _idea_submission())
    assert result.valid is True
    assert result.code == ""


def test_submit_idea_missing_content():
    record = {k: v for k, v in _idea_submission().items() if k != "content"}
    result = validate_submission("idea", record)
    assert result.valid is False
    field_names = [e.field for e in result.errors]
    assert "content" in field_names


def test_submit_parking_lot_positive():
    result = validate_submission("parking_lot", _parking_lot_submission())
    assert result.valid is True
    assert result.code == ""


# ---------------------------------------------------------------------------
# Storage contract tests
# ---------------------------------------------------------------------------

def test_storage_task_full():
    """All 16 task storage fields → validate_storage valid=True."""
    result = validate_storage("task", _task_storage())
    assert result.valid is True, f"Unexpected errors: {result.errors}"
    assert result.code == ""


def test_storage_task_missing_status():
    record = {k: v for k, v in _task_storage().items() if k != "status"}
    result = validate_storage("task", record)
    assert result.valid is False
    assert result.code == "missing_required_field"
    assert any(e.field == "status" for e in result.errors)


def test_storage_task_missing_id():
    record = {k: v for k, v in _task_storage().items() if k != "id"}
    result = validate_storage("task", record)
    assert result.valid is False
    assert any(e.field == "id" for e in result.errors)


def test_storage_task_empty_source():
    """Empty-string source fails validate_storage (NonEmptyStr min_length=1)."""
    record = {**_task_storage(), "source": ""}
    result = validate_storage("task", record)
    assert result.valid is False
    assert any(e.field == "source" for e in result.errors)


def test_storage_idea_full():
    """All 12 idea storage fields → valid=True."""
    result = validate_storage("idea", _idea_storage())
    assert result.valid is True, f"Unexpected errors: {result.errors}"


def test_storage_parking_lot_full():
    """All 11 parking_lot storage fields → valid=True."""
    result = validate_storage("parking_lot", _parking_lot_storage())
    assert result.valid is True, f"Unexpected errors: {result.errors}"


def test_unknown_record_type():
    result = validate_submission("unknown_type", {"title": "x"})
    assert result.valid is False
    assert result.code == "unknown_record_type"
