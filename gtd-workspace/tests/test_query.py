"""Tests for gtd_query.py — retrieval, filtering, sorting, and isolation."""

import json
from pathlib import Path

import pytest

from common import append_jsonl, user_path
from gtd_query import query

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_OLD = "2026-01-01T00:00:00+00:00"   # older created_at (sorts earlier)
_TS_NEW = "2026-03-01T00:00:00+00:00"   # newer created_at (sorts later)


def _task(**overrides) -> dict:
    """Minimal valid task record ready to write directly to JSONL."""
    base = {
        "id":               "task-id-1",
        "record_type":      "task",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Do something",
        "context":          "@computer",
        "area":             "work",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       _TS_OLD,
        "updated_at":       _TS_OLD,
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    """Minimal valid idea record (must never appear in query results)."""
    base = {
        "id":               "idea-id-1",
        "record_type":      "idea",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Automate all the things",
        "domain":           "ai-automation",
        "context":          "@computer",
        "review_cadence":   "monthly",
        "promotion_state":  "raw",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       _TS_OLD,
        "updated_at":       _TS_OLD,
        "spark_note":       None,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }
    return {**base, **overrides}


def _write_task(user_id: str, record: dict, tmp_path: Path) -> None:
    path = user_path(user_id) / "tasks.jsonl"
    append_jsonl(path, record)


def _write_idea(user_id: str, record: dict, tmp_path: Path) -> None:
    path = user_path(user_id) / "ideas.jsonl"
    append_jsonl(path, record)


# ---------------------------------------------------------------------------
# 1. Returns only task records — ideas in tasks.jsonl are filtered out
# ---------------------------------------------------------------------------

def test_returns_only_task_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Write a task and a bogus idea entry both into tasks.jsonl
    _write_task("user1", _task(id="t1", title="Real task"), tmp_path)
    path = user_path("user1") / "tasks.jsonl"
    append_jsonl(path, _idea(id="i1", title="Idea that snuck in"))

    results = query("user1")
    assert all(r["record_type"] == "task" for r in results)
    assert len(results) == 1
    assert results[0]["id"] == "t1"


# ---------------------------------------------------------------------------
# 2. Excludes done, cancelled, archived by default
# ---------------------------------------------------------------------------

def test_excludes_done_cancelled_archived_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="active",    status="active"),    tmp_path)
    _write_task("user1", _task(id="done",      status="done"),      tmp_path)
    _write_task("user1", _task(id="cancelled", status="cancelled"), tmp_path)
    _write_task("user1", _task(id="archived",  status="archived"),  tmp_path)

    results = query("user1")
    ids = [r["id"] for r in results]
    assert "active" in ids
    assert "done" not in ids
    assert "cancelled" not in ids
    assert "archived" not in ids


# ---------------------------------------------------------------------------
# 3. Filters by context correctly
# ---------------------------------------------------------------------------

def test_filters_by_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="home",     context="@home"),     tmp_path)
    _write_task("user1", _task(id="computer", context="@computer"), tmp_path)
    _write_task("user1", _task(id="phone",    context="@phone"),    tmp_path)

    results = query("user1", context="@home")
    assert len(results) == 1
    assert results[0]["id"] == "home"


# ---------------------------------------------------------------------------
# 4. Filters by priority correctly
# ---------------------------------------------------------------------------

def test_filters_by_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="low",      priority="low"),      tmp_path)
    _write_task("user1", _task(id="critical", priority="critical"), tmp_path)
    _write_task("user1", _task(id="high",     priority="high"),     tmp_path)

    results = query("user1", priority="critical")
    assert len(results) == 1
    assert results[0]["id"] == "critical"


# ---------------------------------------------------------------------------
# 5. Filters by energy correctly
# ---------------------------------------------------------------------------

def test_filters_by_energy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="low",    energy="low"),    tmp_path)
    _write_task("user1", _task(id="medium", energy="medium"), tmp_path)
    _write_task("user1", _task(id="high",   energy="high"),   tmp_path)

    results = query("user1", energy="low")
    assert len(results) == 1
    assert results[0]["id"] == "low"


# ---------------------------------------------------------------------------
# 6. Respects duration_minutes max threshold; nulls are included
# ---------------------------------------------------------------------------

def test_duration_minutes_max_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="short",   duration_minutes=15),   tmp_path)
    _write_task("user1", _task(id="exact",   duration_minutes=30),   tmp_path)
    _write_task("user1", _task(id="long",    duration_minutes=60),   tmp_path)
    _write_task("user1", _task(id="unknown", duration_minutes=None), tmp_path)

    results = query("user1", duration_minutes=30)
    ids = [r["id"] for r in results]
    assert "short"   in ids
    assert "exact"   in ids
    assert "unknown" in ids
    assert "long"    not in ids


# ---------------------------------------------------------------------------
# 7. Sorts by priority descending, then created_at ascending
# ---------------------------------------------------------------------------

def test_sort_priority_descending_then_created_at_ascending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Two normal tasks: older one should appear before newer at same priority
    _write_task("user1", _task(id="normal-old", priority="normal", created_at=_TS_OLD), tmp_path)
    _write_task("user1", _task(id="normal-new", priority="normal", created_at=_TS_NEW), tmp_path)
    # Critical task should be first regardless of created_at
    _write_task("user1", _task(id="critical",   priority="critical", created_at=_TS_NEW), tmp_path)
    # Low priority task should be last
    _write_task("user1", _task(id="low",        priority="low",      created_at=_TS_OLD), tmp_path)

    results = query("user1", limit=10)
    ids = [r["id"] for r in results]
    assert ids[0] == "critical"
    assert ids[1] == "normal-old"
    assert ids[2] == "normal-new"
    assert ids[3] == "low"


# ---------------------------------------------------------------------------
# 8. Respects limit parameter
# ---------------------------------------------------------------------------

def test_respects_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    for i in range(10):
        _write_task("user1", _task(id=f"task-{i}", title=f"Task {i}"), tmp_path)

    results = query("user1", limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# 9. Returns empty list when no records match
# ---------------------------------------------------------------------------

def test_returns_empty_when_no_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Only done tasks — all excluded by default
    _write_task("user1", _task(id="done1", status="done"), tmp_path)
    _write_task("user1", _task(id="done2", status="done"), tmp_path)

    results = query("user1")
    assert results == []


# ---------------------------------------------------------------------------
# 10. User isolation: user2 cannot see user1's tasks
# ---------------------------------------------------------------------------

def test_user_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="u1-task", user_id="user1"), tmp_path)

    results = query("user2")
    assert results == []
