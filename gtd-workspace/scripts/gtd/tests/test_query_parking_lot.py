"""Tests for scripts/gtd/query_parking_lot.py."""

import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from query_parking_lot import query_parking_lot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pl(storage: Path, user_id: str, records: list[dict]) -> None:
    path = storage / "gtd-agent" / "users" / user_id / "parking-lot.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _pl(content: str) -> dict:
    return {
        "id": f"p-{content[:4]}",
        "record_type": "parking_lot",
        "content": content,
        "created_at": "2026-04-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# 1. Empty file returns empty result
# ---------------------------------------------------------------------------

def test_query_parking_lot_empty_returns_empty(storage: Path) -> None:
    result = query_parking_lot(requesting_user_id="user1")
    assert result["items"] == []
    assert result["total_count"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 2. Returns all records within limit
# ---------------------------------------------------------------------------

def test_query_parking_lot_returns_all(storage: Path) -> None:
    _write_pl(storage, "user1", [_pl("A"), _pl("B")])
    result = query_parking_lot(limit=25, requesting_user_id="user1")
    assert result["total_count"] == 2
    assert len(result["items"]) == 2


# ---------------------------------------------------------------------------
# 3. Limit enforced; truncated=True when more records exist
# ---------------------------------------------------------------------------

def test_query_parking_lot_limit_and_truncated(storage: Path) -> None:
    _write_pl(storage, "user1", [_pl(f"Item {i}") for i in range(5)])
    result = query_parking_lot(limit=2, requesting_user_id="user1")
    assert len(result["items"]) == 2
    assert result["total_count"] == 5
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 4. truncated=False when results fit within limit
# ---------------------------------------------------------------------------

def test_query_parking_lot_not_truncated(storage: Path) -> None:
    _write_pl(storage, "user1", [_pl("A")])
    result = query_parking_lot(limit=10, requesting_user_id="user1")
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 5. Limit capped at max_query_limit (25)
# ---------------------------------------------------------------------------

def test_query_parking_lot_limit_capped_at_max(storage: Path) -> None:
    _write_pl(storage, "user1", [_pl(f"P{i}") for i in range(30)])
    result = query_parking_lot(limit=100, requesting_user_id="user1")
    assert len(result["items"]) == 25
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 6. Empty requesting_user_id raises internal_error
# ---------------------------------------------------------------------------

def test_query_parking_lot_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        query_parking_lot(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 7. Records use content field (Z3 storage contract)
# ---------------------------------------------------------------------------

def test_query_parking_lot_content_field(storage: Path) -> None:
    _write_pl(storage, "user1", [_pl("Stray thought about watches")])
    result = query_parking_lot(limit=25, requesting_user_id="user1")
    assert result["items"][0]["content"] == "Stray thought about watches"
    assert "title" not in result["items"][0]
    assert "raw_text" not in result["items"][0]


# ---------------------------------------------------------------------------
# 8. OTEL span emitted with result attributes
# ---------------------------------------------------------------------------

def test_query_parking_lot_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    _write_pl(storage, "user1", [_pl("A"), _pl("B"), _pl("C")])
    query_parking_lot(limit=2, requesting_user_id="user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.query_parking_lot"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("result.total_count") == 3
    assert attrs.get("result.truncated") is True


# ---------------------------------------------------------------------------
# Z3: Read-projection test
# ---------------------------------------------------------------------------

def test_read_projection_omits_channel_parking_lot(storage: Path) -> None:
    """query_parking_lot items must not contain source, telegram_chat_id, or record_type."""
    _write_pl(storage, "user1", [
        {
            "id": "pl-proj", "record_type": "parking_lot", "content": "Parked",
            "reason": None, "status": "open",
            "created_at": "2026-05-03T10:00:00+00:00",
            "updated_at": "2026-05-03T10:00:00+00:00",
            "last_reviewed": None, "completed_at": None,
            "source": "telegram_text", "telegram_chat_id": "8712103657",
        }
    ])
    result = query_parking_lot(requesting_user_id="user1")
    assert result["total_count"] == 1
    item = result["items"][0]
    assert "source" not in item
    assert "telegram_chat_id" not in item
    assert "record_type" not in item
