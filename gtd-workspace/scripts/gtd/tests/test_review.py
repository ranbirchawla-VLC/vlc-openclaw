"""Tests for scripts/gtd/review.py -- Z3 version.

Replaces scaffold tests with real behavior tests:
- reviewed_at + by_type envelope
- auto-stamp (D-A): last_reviewed and updated_at = reviewed_at on disk
- stale filter
- read-projection omits channel fields
- per-file stamp failure → ok=false storage_unavailable
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from review import review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _task(title: str = "Task", last_reviewed: str | None = None) -> dict:
    return {
        "id": f"t-{title[:6]}", "record_type": "task", "title": title,
        "context": "@work", "project": None, "priority": None,
        "waiting_for": None, "due_date": None, "notes": None,
        "status": "open", "created_at": "2026-04-01T00:00:00+00:00",
        "updated_at": "2026-04-01T00:00:00+00:00",
        "last_reviewed": last_reviewed,
        "completed_at": None, "source": "telegram_text",
        "telegram_chat_id": "8712103657",
    }


def _idea(title: str = "Idea", last_reviewed: str | None = None) -> dict:
    return {
        "id": f"i-{title[:6]}", "record_type": "idea", "title": title,
        "topic": None, "content": "Content", "status": "open",
        "created_at": "2026-04-01T00:00:00+00:00",
        "updated_at": "2026-04-01T00:00:00+00:00",
        "last_reviewed": last_reviewed,
        "completed_at": None, "source": "telegram_text",
        "telegram_chat_id": "8712103657",
    }


def _pl(content: str = "Parked", last_reviewed: str | None = None) -> dict:
    return {
        "id": f"p-{content[:6]}", "record_type": "parking_lot", "content": content,
        "reason": None, "status": "open",
        "created_at": "2026-04-01T00:00:00+00:00",
        "updated_at": "2026-04-01T00:00:00+00:00",
        "last_reviewed": last_reviewed,
        "completed_at": None, "source": "telegram_text",
        "telegram_chat_id": "8712103657",
    }


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------

def test_review_output_envelope_shape(storage: Path) -> None:
    """Response has reviewed_at and by_type with all three record types."""
    result = review(requesting_user_id="user1")
    assert "reviewed_at" in result
    assert "by_type" in result
    by_type = result["by_type"]
    assert "tasks" in by_type
    assert "ideas" in by_type
    assert "parking_lot" in by_type
    for rt in by_type.values():
        assert "items" in rt
        assert "total_count" in rt
        assert "truncated" in rt


# ---------------------------------------------------------------------------
# Stale filter
# ---------------------------------------------------------------------------

def test_review_stale_filter(storage: Path) -> None:
    """Record with null last_reviewed appears; recently-reviewed record absent."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    tasks_file = user_dir / "tasks.jsonl"
    _write(tasks_file, [
        _task("Stale task", last_reviewed=None),
        _task("Fresh task", last_reviewed=datetime.now(timezone.utc).isoformat()),
    ])
    result = review(requesting_user_id="user1", stale_for_days=7)
    items = result["by_type"]["tasks"]["items"]
    titles = [item["title"] for item in items]
    assert "Stale task" in titles
    assert "Fresh task" not in titles


# ---------------------------------------------------------------------------
# Auto-stamp tests (D-A) — all three record types
# ---------------------------------------------------------------------------

def test_review_auto_stamps_tasks(storage: Path) -> None:
    """After review(), tasks on disk have last_reviewed == updated_at == reviewed_at."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    tasks_file = user_dir / "tasks.jsonl"
    _write(tasks_file, [_task("Review me")])

    result = review(requesting_user_id="user1")
    reviewed_at = result["reviewed_at"]

    stored = _read(tasks_file)
    assert stored[0]["last_reviewed"] == reviewed_at
    assert stored[0]["updated_at"] == reviewed_at


def test_review_auto_stamps_ideas(storage: Path) -> None:
    """After review(), ideas on disk have last_reviewed == updated_at == reviewed_at."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    ideas_file = user_dir / "ideas.jsonl"
    _write(ideas_file, [_idea("Review idea")])

    result = review(requesting_user_id="user1")
    reviewed_at = result["reviewed_at"]

    stored = _read(ideas_file)
    assert stored[0]["last_reviewed"] == reviewed_at
    assert stored[0]["updated_at"] == reviewed_at


def test_review_auto_stamps_parking_lot(storage: Path) -> None:
    """After review(), parking_lot on disk has last_reviewed == updated_at == reviewed_at."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    pl_file = user_dir / "parking-lot.jsonl"
    _write(pl_file, [_pl("Review pl")])

    result = review(requesting_user_id="user1")
    reviewed_at = result["reviewed_at"]

    stored = _read(pl_file)
    assert stored[0]["last_reviewed"] == reviewed_at
    assert stored[0]["updated_at"] == reviewed_at


# ---------------------------------------------------------------------------
# Read-projection — channel fields excluded
# ---------------------------------------------------------------------------

def test_review_read_projection_omits_channel(storage: Path) -> None:
    """Review items must not contain source, telegram_chat_id, or record_type."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    _write(user_dir / "tasks.jsonl", [_task()])

    result = review(requesting_user_id="user1")
    for item in result["by_type"]["tasks"]["items"]:
        assert "source" not in item
        assert "telegram_chat_id" not in item
        assert "record_type" not in item


# ---------------------------------------------------------------------------
# Per-file stamp failure → ok=false storage_unavailable
# ---------------------------------------------------------------------------

def test_review_stamp_single_file_failure(storage: Path) -> None:
    """If the stamp write fails on tasks file, raises GTDError(storage_unavailable)."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    tasks_file = user_dir / "tasks.jsonl"
    _write(tasks_file, [_task()])

    with patch("review._write_stamp_jsonl", side_effect=OSError("disk full")):
        with pytest.raises(GTDError) as exc_info:
            review(requesting_user_id="user1")
    assert exc_info.value.code == "storage_unavailable"


def test_review_stamp_partial_failure(storage: Path) -> None:
    """Tasks stamp succeeds; ideas stamp fails. tasks updated on disk; ideas not.
    Result is GTDError(storage_unavailable)."""
    user_dir = storage / "gtd-agent" / "users" / "user1"
    tasks_file = user_dir / "tasks.jsonl"
    ideas_file = user_dir / "ideas.jsonl"
    _write(tasks_file, [_task("T")])
    _write(ideas_file, [_idea("I")])

    call_count = 0

    def _fail_on_second(path, records, ids, reviewed_at):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("disk full on ideas")
        import json as _json
        import os as _os
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in records:
                if r["id"] in ids:
                    r = {**r, "last_reviewed": reviewed_at, "updated_at": reviewed_at}
                fh.write(_json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, path)

    with patch("review._write_stamp_jsonl", side_effect=_fail_on_second):
        with pytest.raises(GTDError) as exc_info:
            review(requesting_user_id="user1")
    assert exc_info.value.code == "storage_unavailable"


# ---------------------------------------------------------------------------
# Empty user_id guard
# ---------------------------------------------------------------------------

def test_review_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        review(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# OTEL span
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
    assert attrs.get("tool.name") == "review"
