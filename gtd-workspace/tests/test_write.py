"""Tests for gtd_write.py — persistence, isolation, and round-trips."""

import re
import pytest
from pathlib import Path

from common import read_jsonl, user_path
from gtd_write import write_record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _task_input(**overrides) -> dict:
    """Minimal task input — no id/timestamps (write generates those)."""
    base = {
        "record_type":      "task",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Submit the quarterly report",
        "context":          "@computer",
        "area":             "business",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    return {**base, **overrides}


def _idea_input(**overrides) -> dict:
    base = {
        "record_type":      "idea",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "title":            "Automate the listing workflow",
        "domain":           "ai-automation",
        "context":          "@computer",
        "review_cadence":   "monthly",
        "promotion_state":  "incubating",
        "status":           "active",
        "source":           "telegram_text",
        "spark_note":       None,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }
    return {**base, **overrides}


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


# ---------------------------------------------------------------------------
# 1. Successful task write creates file and appends record
# ---------------------------------------------------------------------------

def test_task_write_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    result = write_record(_task_input(), "task", "user1")
    assert result["status"] == "ok"
    assert result["record_type"] == "task"
    tasks_file = user_path("user1") / "tasks.jsonl"
    assert tasks_file.exists()


# ---------------------------------------------------------------------------
# 2. Successful idea write
# ---------------------------------------------------------------------------

def test_idea_write_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    result = write_record(_idea_input(), "idea", "user1")
    assert result["status"] == "ok"
    assert result["record_type"] == "idea"


# ---------------------------------------------------------------------------
# 3. Write generates UUID id and timestamps automatically
# ---------------------------------------------------------------------------

def test_write_generates_id_and_timestamps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    result = write_record(_task_input(), "task", "user1")
    assert result["status"] == "ok"
    assert _UUID4_RE.match(result["id"])

    # Verify the stored record has id and timestamps
    records = read_jsonl(user_path("user1") / "tasks.jsonl")
    assert len(records) == 1
    stored = records[0]
    assert _UUID4_RE.match(stored["id"])
    assert stored["created_at"]
    assert stored["updated_at"]


# ---------------------------------------------------------------------------
# 4. Write to non-existent user directory creates it
# ---------------------------------------------------------------------------

def test_write_creates_user_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    new_user = "brand-new-user"
    result = write_record(_task_input(user_id=new_user), "task", new_user)
    assert result["status"] == "ok"
    assert (tmp_path / "gtd-agent" / "users" / new_user).is_dir()


# ---------------------------------------------------------------------------
# 5. Write with invalid record is refused
# ---------------------------------------------------------------------------

def test_write_invalid_record_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    bad = _task_input(priority="galaxy-brain")  # invalid enum
    result = write_record(bad, "task", "user1")
    assert result["status"] == "error"
    assert result["errors"]
    # File must not be created
    tasks_file = tmp_path / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    assert not tasks_file.exists()


# ---------------------------------------------------------------------------
# 6. Written record round-trips correctly through JSONL reader
# ---------------------------------------------------------------------------

def test_write_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    input_record = _task_input(title="Call the customs broker", context="@phone")
    result = write_record(input_record, "task", "user1")
    assert result["status"] == "ok"

    records = read_jsonl(user_path("user1") / "tasks.jsonl")
    assert len(records) == 1
    stored = records[0]
    assert stored["title"] == "Call the customs broker"
    assert stored["context"] == "@phone"
    assert stored["record_type"] == "task"
    assert stored["user_id"] == "user1"


# ---------------------------------------------------------------------------
# 7. Two sequential writes append correctly
# ---------------------------------------------------------------------------

def test_two_sequential_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    write_record(_task_input(title="Task one"), "task", "user1")
    write_record(_task_input(title="Task two"), "task", "user1")
    records = read_jsonl(user_path("user1") / "tasks.jsonl")
    assert len(records) == 2
    assert records[0]["title"] == "Task one"
    assert records[1]["title"] == "Task two"


# ---------------------------------------------------------------------------
# 8. User isolation: write with mismatched user_id is refused
# ---------------------------------------------------------------------------

def test_isolation_mismatch_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    # record claims to belong to user1 but requesting_user_id is user2
    result = write_record(_task_input(user_id="user1"), "task", "user2")
    assert result["status"] == "error"
    fields = [e["field"] for e in result["errors"]]
    assert "user_id" in fields


# ---------------------------------------------------------------------------
# 9. Parking lot write goes to parking-lot.jsonl
# ---------------------------------------------------------------------------

def test_parking_lot_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    record = {
        "record_type":      "parking_lot",
        "user_id":          "user1",
        "telegram_chat_id": "chat1",
        "raw_text":         "some random thought I had",
        "source":           "telegram_text",
        "reason":           "ambiguous_capture",
        "status":           "active",
    }
    result = write_record(record, "parking_lot", "user1")
    assert result["status"] == "ok"
    pl_file = user_path("user1") / "parking-lot.jsonl"
    assert pl_file.exists()


# ---------------------------------------------------------------------------
# 10. Unsupported record_type (profile) returns error
# ---------------------------------------------------------------------------

def test_unsupported_record_type_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    result = write_record({"user_id": "user1"}, "profile", "user1")
    assert result["status"] == "error"
