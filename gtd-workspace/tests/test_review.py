"""Tests for gtd_review.py — structured review scan, all five sections."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from common import append_jsonl, user_path
from gtd_review import review

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(days_ago: int) -> str:
    """Return an ISO 8601 string for UTC time `days_ago` days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _task(**overrides) -> dict:
    base = {
        "id":               "t1",
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
        "created_at":       _iso(1),
        "updated_at":       _iso(1),
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _idea(**overrides) -> dict:
    base = {
        "id":               "i1",
        "record_type":      "idea",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Some idea",
        "domain":           "ai-automation",
        "context":          "@computer",
        "review_cadence":   "monthly",
        "promotion_state":  "raw",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       _iso(1),
        "updated_at":       _iso(1),
        "spark_note":       None,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }
    return {**base, **overrides}


def _parking(**overrides) -> dict:
    base = {
        "id":               "p1",
        "record_type":      "parking_lot",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "raw_text":         "random thought",
        "source":           "telegram_text",
        "reason":           "ambiguous_capture",
        "status":           "active",
        "created_at":       _iso(1),
        "updated_at":       _iso(1),
    }
    return {**base, **overrides}


def _write_task(uid: str, record: dict) -> None:
    append_jsonl(user_path(uid) / "tasks.jsonl", record)


def _write_idea(uid: str, record: dict) -> None:
    append_jsonl(user_path(uid) / "ideas.jsonl", record)


def _write_parking(uid: str, record: dict) -> None:
    append_jsonl(user_path(uid) / "parking-lot.jsonl", record)


def _section(result: dict, name: str) -> dict:
    return next(s for s in result["sections"] if s["name"] == name)


# ---------------------------------------------------------------------------
# 1. Identifies active task missing context
# ---------------------------------------------------------------------------

def test_identifies_task_missing_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="t-no-ctx", context=""))

    result = review("user1")
    section = _section(result, "active_tasks_missing_metadata")
    ids = [r["id"] for r in section["items"]]
    assert "t-no-ctx" in ids


# ---------------------------------------------------------------------------
# 2. Identifies active task missing area
# ---------------------------------------------------------------------------

def test_identifies_task_missing_area(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="t-no-area", area=""))

    result = review("user1")
    section = _section(result, "active_tasks_missing_metadata")
    ids = [r["id"] for r in section["items"]]
    assert "t-no-area" in ids


# ---------------------------------------------------------------------------
# 3. Identifies stale active task (>14 days since last update)
# ---------------------------------------------------------------------------

def test_identifies_stale_active_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # 15 days old → stale
    _write_task("user1", _task(id="stale", updated_at=_iso(15)))

    result = review("user1")
    section = _section(result, "stale_active_tasks")
    ids = [r["id"] for r in section["items"]]
    assert "stale" in ids


# ---------------------------------------------------------------------------
# 4. Does not flag recently updated active task as stale
# ---------------------------------------------------------------------------

def test_does_not_flag_recently_updated_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # 13 days old → not stale (threshold is >14)
    _write_task("user1", _task(id="fresh", updated_at=_iso(13)))

    result = review("user1")
    section = _section(result, "stale_active_tasks")
    ids = [r["id"] for r in section["items"]]
    assert "fresh" not in ids


# ---------------------------------------------------------------------------
# 5. Identifies idea overdue for weekly review (>7 days since last reviewed)
# ---------------------------------------------------------------------------

def test_identifies_idea_overdue_weekly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_idea(
        "user1",
        _idea(id="weekly-overdue", review_cadence="weekly", last_reviewed_at=_iso(8)),
    )

    result = review("user1")
    section = _section(result, "ideas_overdue_for_review")
    ids = [r["id"] for r in section["items"]]
    assert "weekly-overdue" in ids


# ---------------------------------------------------------------------------
# 6. Identifies idea overdue for monthly review (>30 days)
# ---------------------------------------------------------------------------

def test_identifies_idea_overdue_monthly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_idea(
        "user1",
        _idea(id="monthly-overdue", review_cadence="monthly", last_reviewed_at=_iso(31)),
    )

    result = review("user1")
    section = _section(result, "ideas_overdue_for_review")
    ids = [r["id"] for r in section["items"]]
    assert "monthly-overdue" in ids


# ---------------------------------------------------------------------------
# 7. Does not flag idea reviewed within its cadence
# ---------------------------------------------------------------------------

def test_does_not_flag_idea_within_cadence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Reviewed 3 days ago, weekly cadence → not overdue
    _write_idea(
        "user1",
        _idea(id="fresh-idea", review_cadence="weekly", last_reviewed_at=_iso(3)),
    )

    result = review("user1")
    section = _section(result, "ideas_overdue_for_review")
    ids = [r["id"] for r in section["items"]]
    assert "fresh-idea" not in ids


# ---------------------------------------------------------------------------
# 8. Identifies waiting-for item untouched 7+ days
# ---------------------------------------------------------------------------

def test_identifies_waiting_followup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_task("user1", _task(id="waiting-old", status="waiting", updated_at=_iso(7)))
    _write_task("user1", _task(id="delegated-old", status="delegated", updated_at=_iso(8)))

    result = review("user1")
    section = _section(result, "waiting_for_followup")
    ids = [r["id"] for r in section["items"]]
    assert "waiting-old" in ids
    assert "delegated-old" in ids


# ---------------------------------------------------------------------------
# 9. Identifies active parking-lot items
# ---------------------------------------------------------------------------

def test_identifies_active_parking_lot_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write_parking("user1", _parking(id="p-active", status="active"))
    _write_parking("user1", _parking(id="p-done",   status="done"))

    result = review("user1")
    section = _section(result, "parking_lot_unclassified")
    ids = [r["id"] for r in section["items"]]
    assert "p-active" in ids
    assert "p-done"   not in ids


# ---------------------------------------------------------------------------
# 10. Returns correct total_items_flagged count
# ---------------------------------------------------------------------------

def test_correct_total_items_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # 1 task missing metadata, 1 stale task, 1 overdue idea, 1 waiting, 1 parking
    _write_task("user1",   _task(id="missing-meta", context=""))
    _write_task("user1",   _task(id="stale-t",      updated_at=_iso(15)))
    _write_idea("user1",   _idea(id="overdue-i",    review_cadence="weekly", last_reviewed_at=_iso(8)))
    _write_task("user1",   _task(id="waiting-t",    status="waiting", updated_at=_iso(7)))
    _write_parking("user1", _parking(id="park-1"))

    result = review("user1")
    assert result["total_items_flagged"] == sum(
        s["count"] for s in result["sections"]
    )
    # Each section has exactly one item
    for section in result["sections"]:
        assert section["count"] == len(section["items"])


# ---------------------------------------------------------------------------
# 11. Sections appear in the specified priority order
# ---------------------------------------------------------------------------

def test_sections_in_priority_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    result = review("user1")
    names = [s["name"] for s in result["sections"]]
    assert names == [
        "active_tasks_missing_metadata",
        "stale_active_tasks",
        "ideas_overdue_for_review",
        "waiting_for_followup",
        "parking_lot_unclassified",
    ]
