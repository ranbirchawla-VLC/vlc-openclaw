"""Tests for scripts/gtd/query_tasks.py."""

import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from query_tasks import query_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tasks(storage: Path, user_id: str, records: list[dict]) -> None:
    path = storage / "gtd-agent" / "users" / user_id / "tasks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _t(title: str, context: str = "@work", due_date: str | None = None,
        waiting_for: str | None = None) -> dict:
    r = {"id": f"t-{title[:4]}", "record_type": "task", "title": title,
         "context": context, "created_at": "2026-04-01T00:00:00+00:00"}
    if due_date is not None:
        r["due_date"] = due_date
    if waiting_for is not None:
        r["waiting_for"] = waiting_for
    return r


# ---------------------------------------------------------------------------
# 1. Empty file returns empty result
# ---------------------------------------------------------------------------

def test_query_tasks_empty_file_returns_empty(storage: Path) -> None:
    result = query_tasks(requesting_user_id="user1")
    assert result["items"] == []
    assert result["total_count"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 2. Returns all records when no filters applied
# ---------------------------------------------------------------------------

def test_query_tasks_no_filter_returns_all(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t("A"), _t("B"), _t("C")])
    result = query_tasks(requesting_user_id="user1", limit=25)
    assert result["total_count"] == 3
    assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# 3. Context filter returns only matching records
# ---------------------------------------------------------------------------

def test_query_tasks_context_filter(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Buy milk", "@errands"),
        _t("Email boss", "@work"),
        _t("Buy parts", "@errands"),
    ])
    result = query_tasks(context="@errands", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 2
    assert all(r["context"] == "@errands" for r in result["items"])


# ---------------------------------------------------------------------------
# 4. Context filter with no match returns empty
# ---------------------------------------------------------------------------

def test_query_tasks_context_filter_no_match(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t("Buy milk", "@errands")])
    result = query_tasks(context="@phone", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 0
    assert result["items"] == []


# ---------------------------------------------------------------------------
# 5. due_date_before filter returns records with due_date <= threshold
# ---------------------------------------------------------------------------

def test_query_tasks_due_date_before(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Past", due_date="2026-05-01"),
        _t("Future", due_date="2026-07-01"),
        _t("NoDue"),
    ])
    result = query_tasks(due_date_before="2026-06-01", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "Past"


# ---------------------------------------------------------------------------
# 6. due_date_after filter returns records with due_date >= threshold
# ---------------------------------------------------------------------------

def test_query_tasks_due_date_after(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Past", due_date="2026-05-01"),
        _t("Future", due_date="2026-07-01"),
    ])
    result = query_tasks(due_date_after="2026-06-01", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "Future"


# ---------------------------------------------------------------------------
# 7. has_waiting_for=True returns only records with waiting_for set
# ---------------------------------------------------------------------------

def test_query_tasks_has_waiting_for_true(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Waiting on Alex", waiting_for="Alex"),
        _t("No waiting"),
    ])
    result = query_tasks(has_waiting_for=True, requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["waiting_for"] == "Alex"


# ---------------------------------------------------------------------------
# 8. has_waiting_for=False returns only records without waiting_for
# ---------------------------------------------------------------------------

def test_query_tasks_has_waiting_for_false(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Waiting on Alex", waiting_for="Alex"),
        _t("No waiting"),
    ])
    result = query_tasks(has_waiting_for=False, requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "No waiting"


# ---------------------------------------------------------------------------
# 9. limit enforced; truncated=True when more records exist
# ---------------------------------------------------------------------------

def test_query_tasks_limit_and_truncated(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t(f"Task {i}") for i in range(5)])
    result = query_tasks(limit=3, requesting_user_id="user1")
    assert len(result["items"]) == 3
    assert result["total_count"] == 5
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 10. truncated=False when results fit within limit
# ---------------------------------------------------------------------------

def test_query_tasks_not_truncated_when_within_limit(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t("A"), _t("B")])
    result = query_tasks(limit=10, requesting_user_id="user1")
    assert result["truncated"] is False
    assert result["total_count"] == 2


# ---------------------------------------------------------------------------
# 11. limit capped at max_query_limit (25) regardless of input
# ---------------------------------------------------------------------------

def test_query_tasks_limit_capped_at_max(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t(f"T{i}") for i in range(30)])
    result = query_tasks(limit=100, requesting_user_id="user1")
    assert len(result["items"]) == 25
    assert result["total_count"] == 30
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 12. Empty requesting_user_id raises internal_error
# ---------------------------------------------------------------------------

def test_query_tasks_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        query_tasks(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 13. OTEL span emitted with result attributes
# ---------------------------------------------------------------------------

def test_query_tasks_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    _write_tasks(storage, "user1", [_t("A"), _t("B")])
    query_tasks(limit=1, requesting_user_id="user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.query_tasks"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("result.total_count") == 2
    assert attrs.get("result.truncated") is True


# ---------------------------------------------------------------------------
# 14. OTEL span includes filter attributes when set
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 15. null due_date excluded when due_date_before filter is set
# ---------------------------------------------------------------------------

def test_query_tasks_null_due_date_excluded_by_before_filter(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Has date", due_date="2026-04-01"),
        _t("No date"),
    ])
    result = query_tasks(due_date_before="2026-05-01", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "Has date"


# ---------------------------------------------------------------------------
# 16. null due_date excluded when due_date_after filter is set
# ---------------------------------------------------------------------------

def test_query_tasks_null_due_date_excluded_by_after_filter(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Has date", due_date="2026-07-01"),
        _t("No date"),
    ])
    result = query_tasks(due_date_after="2026-06-01", requesting_user_id="user1", limit=25)
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "Has date"


# ---------------------------------------------------------------------------
def test_query_tasks_span_includes_filter_attrs(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    query_tasks(context="@work", has_waiting_for=True, requesting_user_id="user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.query_tasks"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("query.context") == "@work"
    assert attrs.get("query.has_waiting_for") is True


# ---------------------------------------------------------------------------
# Z3: Read-projection test — channel fields and record_type excluded
# ---------------------------------------------------------------------------

def test_read_projection_omits_channel_task(storage: Path) -> None:
    """query_tasks items must not contain source, telegram_chat_id, or record_type."""
    _write_tasks(storage, "user1", [
        {
            "id": "t-proj", "record_type": "task", "title": "Project test",
            "context": "@work", "project": None, "priority": None,
            "waiting_for": None, "due_date": None, "notes": None,
            "status": "open", "created_at": "2026-05-03T10:00:00+00:00",
            "updated_at": "2026-05-03T10:00:00+00:00", "last_reviewed": None,
            "completed_at": None, "source": "telegram_text",
            "telegram_chat_id": "8712103657",
        }
    ])
    result = query_tasks(requesting_user_id="user1")
    assert result["total_count"] == 1
    item = result["items"][0]
    assert "source" not in item
    assert "telegram_chat_id" not in item
    assert "record_type" not in item
