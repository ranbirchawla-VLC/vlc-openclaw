"""Tests for scripts/gtd/review.py.

Review work function is scaffolded pending a design loop.
Tests verify the scaffold contract so the capability prompt can detect
and surface the pending design state.
"""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from review import review


# ---------------------------------------------------------------------------
# 1. Returns scaffold state with review_available=False
# ---------------------------------------------------------------------------

def test_review_returns_scaffold_state(storage: Path) -> None:
    result = review(requesting_user_id="user1")
    assert result["review_available"] is False


# ---------------------------------------------------------------------------
# 2. Returns empty items list
# ---------------------------------------------------------------------------

def test_review_returns_empty_items(storage: Path) -> None:
    result = review(requesting_user_id="user1")
    assert result["items"] == []
    assert result["total_count"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 3. Returns the note field indicating pending design
# ---------------------------------------------------------------------------

def test_review_note_field_indicates_pending_design(storage: Path) -> None:
    result = review(requesting_user_id="user1")
    assert result.get("note") == "review_design_pending"


# ---------------------------------------------------------------------------
# 4. Empty requesting_user_id raises internal_error
# ---------------------------------------------------------------------------

def test_review_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        review(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 5. OTEL span emitted
# ---------------------------------------------------------------------------

def test_review_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    review(requesting_user_id="user1")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.review"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("tool.name") == "review_gtd"
    assert attrs.get("result.total_count") == 0
