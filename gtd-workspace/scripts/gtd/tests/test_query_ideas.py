"""Tests for scripts/gtd/query_ideas.py."""

import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from query_ideas import query_ideas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ideas(storage: Path, user_id: str, records: list[dict]) -> None:
    path = storage / "gtd-agent" / "users" / user_id / "ideas.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _idea(title: str) -> dict:
    return {
        "id": f"i-{title[:4]}",
        "record_type": "idea",
        "title": title,
        "created_at": "2026-04-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# 1. Empty file returns empty result
# ---------------------------------------------------------------------------

def test_query_ideas_empty_returns_empty(storage: Path) -> None:
    result = query_ideas(requesting_user_id="user1")
    assert result["items"] == []
    assert result["total_count"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 2. Returns all ideas within limit
# ---------------------------------------------------------------------------

def test_query_ideas_returns_all_within_limit(storage: Path) -> None:
    _write_ideas(storage, "user1", [_idea("A"), _idea("B"), _idea("C")])
    result = query_ideas(limit=25, requesting_user_id="user1")
    assert result["total_count"] == 3
    assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# 3. Limit enforced; truncated=True when more records exist
# ---------------------------------------------------------------------------

def test_query_ideas_limit_and_truncated(storage: Path) -> None:
    _write_ideas(storage, "user1", [_idea(f"Idea {i}") for i in range(5)])
    result = query_ideas(limit=2, requesting_user_id="user1")
    assert len(result["items"]) == 2
    assert result["total_count"] == 5
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 4. truncated=False when results fit within limit
# ---------------------------------------------------------------------------

def test_query_ideas_not_truncated(storage: Path) -> None:
    _write_ideas(storage, "user1", [_idea("A"), _idea("B")])
    result = query_ideas(limit=10, requesting_user_id="user1")
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 5. Limit capped at max_query_limit (25)
# ---------------------------------------------------------------------------

def test_query_ideas_limit_capped_at_max(storage: Path) -> None:
    _write_ideas(storage, "user1", [_idea(f"I{i}") for i in range(30)])
    result = query_ideas(limit=100, requesting_user_id="user1")
    assert len(result["items"]) == 25
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 6. Empty requesting_user_id raises internal_error
# ---------------------------------------------------------------------------

def test_query_ideas_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        query_ideas(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 7. Multiple records returned in insertion order
# ---------------------------------------------------------------------------

def test_query_ideas_preserves_order(storage: Path) -> None:
    _write_ideas(storage, "user1", [_idea("First"), _idea("Second"), _idea("Third")])
    result = query_ideas(limit=25, requesting_user_id="user1")
    titles = [r["title"] for r in result["items"]]
    assert titles == ["First", "Second", "Third"]


# ---------------------------------------------------------------------------
# 8. OTEL span emitted with result attributes
# ---------------------------------------------------------------------------

def test_query_ideas_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    _write_ideas(storage, "user1", [_idea("A"), _idea("B")])
    query_ideas(limit=1, requesting_user_id="user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.query_ideas"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("result.total_count") == 2
    assert attrs.get("result.truncated") is True
    assert attrs.get("query.limit") == 1


# ---------------------------------------------------------------------------
# Z3: Read-projection test
# ---------------------------------------------------------------------------

def test_read_projection_omits_channel_idea(storage: Path) -> None:
    """query_ideas items must not contain source, telegram_chat_id, or record_type."""
    _write_ideas(storage, "user1", [
        {
            "id": "i-proj", "record_type": "idea", "title": "Proj idea",
            "topic": None, "content": "The content", "status": "open",
            "created_at": "2026-05-03T10:00:00+00:00",
            "updated_at": "2026-05-03T10:00:00+00:00",
            "last_reviewed": None, "completed_at": None,
            "source": "telegram_text", "telegram_chat_id": "8712103657",
        }
    ])
    result = query_ideas(requesting_user_id="user1")
    assert result["total_count"] == 1
    item = result["items"][0]
    assert "source" not in item
    assert "telegram_chat_id" not in item
    assert "record_type" not in item
