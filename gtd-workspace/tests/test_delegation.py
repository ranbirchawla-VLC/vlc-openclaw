"""Tests for gtd_delegation.py — grouping, sorting, and filtering."""

from pathlib import Path

import pytest

from common import append_jsonl, user_path
from gtd_delegation import delegation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_OLDEST = "2026-01-01T00:00:00+00:00"
_TS_MIDDLE = "2026-02-01T00:00:00+00:00"
_TS_NEWEST = "2026-03-01T00:00:00+00:00"


def _task(**overrides) -> dict:
    base = {
        "id":               "t1",
        "record_type":      "task",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Follow up",
        "context":          "@computer",
        "area":             "work",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "created_at":       _TS_MIDDLE,
        "updated_at":       _TS_MIDDLE,
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _write(uid: str, record: dict) -> None:
    append_jsonl(user_path(uid) / "tasks.jsonl", record)


# ---------------------------------------------------------------------------
# 1. Groups items by delegate_to person
# ---------------------------------------------------------------------------

def test_groups_by_delegate_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="t1", delegate_to="Alice"))
    _write("user1", _task(id="t2", delegate_to="Alice"))
    _write("user1", _task(id="t3", delegate_to="Bob"))

    result = delegation("user1")
    persons = {g["person"]: g for g in result["groups"]}
    assert "Alice" in persons
    assert "Bob"   in persons
    assert len(persons["Alice"]["items"]) == 2
    assert len(persons["Bob"]["items"])   == 1


# ---------------------------------------------------------------------------
# 2. Groups items by waiting_for person
# ---------------------------------------------------------------------------

def test_groups_by_waiting_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="w1", waiting_for="Carol", status="waiting"))
    _write("user1", _task(id="w2", waiting_for="Carol", status="waiting"))

    result = delegation("user1")
    persons = {g["person"]: g for g in result["groups"]}
    assert "Carol" in persons
    assert len(persons["Carol"]["items"]) == 2


# ---------------------------------------------------------------------------
# 3. Sorts groups by oldest untouched (oldest updated_at first)
# ---------------------------------------------------------------------------

def test_groups_sorted_by_oldest_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Bob's item is older than Alice's
    _write("user1", _task(id="alice-t", delegate_to="Alice", updated_at=_TS_NEWEST))
    _write("user1", _task(id="bob-t",   delegate_to="Bob",   updated_at=_TS_OLDEST))

    result = delegation("user1")
    group_persons = [g["person"] for g in result["groups"]]
    assert group_persons[0] == "Bob"    # oldest first
    assert group_persons[1] == "Alice"


# ---------------------------------------------------------------------------
# 4. Sorts items within group by updated_at ascending
# ---------------------------------------------------------------------------

def test_items_within_group_sorted_by_updated_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="newer", delegate_to="Alice", updated_at=_TS_NEWEST))
    _write("user1", _task(id="older", delegate_to="Alice", updated_at=_TS_OLDEST))

    result = delegation("user1")
    persons = {g["person"]: g for g in result["groups"]}
    items = persons["Alice"]["items"]
    assert items[0]["id"] == "older"
    assert items[1]["id"] == "newer"


# ---------------------------------------------------------------------------
# 5. Returns empty groups when no delegation items exist
# ---------------------------------------------------------------------------

def test_empty_when_no_delegation_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # Regular active task — no delegation fields set
    _write("user1", _task(id="plain", delegate_to=None, waiting_for=None, status="active"))

    result = delegation("user1")
    assert result["groups"]     == []
    assert result["total_items"] == 0


# ---------------------------------------------------------------------------
# 6. Does not include regular tasks without delegation fields
# ---------------------------------------------------------------------------

def test_excludes_regular_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="regular", delegate_to=None, waiting_for=None, status="active"))
    _write("user1", _task(id="delegated", delegate_to="Dave"))

    result = delegation("user1")
    all_ids = [item["id"] for g in result["groups"] for item in g["items"]]
    assert "regular"  not in all_ids
    assert "delegated" in all_ids


# ---------------------------------------------------------------------------
# 7. oldest_untouched matches the oldest item in the group
# ---------------------------------------------------------------------------

def test_oldest_untouched_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="t-old", delegate_to="Alice", updated_at=_TS_OLDEST))
    _write("user1", _task(id="t-new", delegate_to="Alice", updated_at=_TS_NEWEST))

    result = delegation("user1")
    persons = {g["person"]: g for g in result["groups"]}
    assert persons["Alice"]["oldest_untouched"] == _TS_OLDEST


# ---------------------------------------------------------------------------
# 8. total_items counts all items across all groups
# ---------------------------------------------------------------------------

def test_total_items_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    _write("user1", _task(id="a1", delegate_to="Alice"))
    _write("user1", _task(id="a2", delegate_to="Alice"))
    _write("user1", _task(id="b1", delegate_to="Bob"))

    result = delegation("user1")
    assert result["total_items"] == 3
