"""test_migrate_z3.py -- tests for the Z3 one-shot migration script.

TDD: each test written before the implementation; confirmed RED against
no-migrate_z3 state before implementation written.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_BACKUP = {
    "id": "task-001",
    "record_type": "task",
    "user_id": "8712103657",
    "telegram_chat_id": "8712103657",
    "title": "Do the thing",
    "status": "active",
    "priority": "normal",
    "energy": "low",
    "context": "@work",
    "area": "watch-business",
    "duration_minutes": 15,
    "delegate_to": None,
    "waiting_for": None,
    "notes": "Some notes",
    "source": "telegram_text",
    "created_at": "2026-04-12T23:08:55+00:00",
    "updated_at": "2026-04-12T23:08:55+00:00",
    "completed_at": None,
}

_TASK_DONE_BACKUP = {**_TASK_BACKUP, "id": "task-002", "status": "done",
                    "completed_at": "2026-04-13T14:46:08+00:00"}

_IDEA_BACKUP = {
    "id": "idea-001",
    "record_type": "idea",
    "user_id": "8712103657",
    "telegram_chat_id": "8712103657",
    "title": "Some idea",
    "domain": "system",
    "context": "@computer",
    "review_cadence": "monthly",
    "promotion_state": "raw",
    "status": "active",
    "spark_note": "The idea content goes here",
    "source": "telegram_text",
    "created_at": "2026-04-12T23:10:51+00:00",
    "updated_at": "2026-04-12T23:10:51+00:00",
    "last_reviewed_at": None,
    "promoted_task_id": None,
}

_PARKING_LOT_BACKUP = {
    "id": "pl-001",
    "record_type": "parking_lot",
    "user_id": "8712103657",
    "telegram_chat_id": "8712103657",
    "title": "Parked item",
    "reason": "Not urgent",
    "status": "active",
    "source": "telegram_text",
    "created_at": "2026-04-12T23:00:00+00:00",
    "updated_at": "2026-04-12T23:00:00+00:00",
    "completed_at": None,
}


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# migrate_record unit tests (field transforms)
# ---------------------------------------------------------------------------

def test_migrate_z3_task_shape(tmp_path, monkeypatch):
    """After --apply: task has 16 storage fields; area→project; active→open;
    energy/duration_minutes/delegate_to/user_id absent."""
    from migrate_z3 import migrate_record

    result = migrate_record(_TASK_BACKUP)

    # all 16 storage fields present
    storage_fields = {
        "id", "record_type", "title", "context", "project", "priority",
        "waiting_for", "due_date", "notes", "status", "created_at",
        "updated_at", "last_reviewed", "completed_at", "source", "telegram_chat_id",
    }
    assert storage_fields == result.keys(), (
        f"Missing: {storage_fields - result.keys()}; Extra: {result.keys() - storage_fields}"
    )

    assert result["status"] == "open"         # active → open
    assert result["project"] == "watch-business"  # area → project
    assert result["last_reviewed"] is None
    assert result["due_date"] is None

    # dropped fields absent
    for dropped in ("user_id", "energy", "duration_minutes", "delegate_to", "area"):
        assert dropped not in result, f"Expected {dropped!r} to be dropped"


def test_migrate_z3_task_done_to_completed(tmp_path):
    """Task with status 'done' → status 'completed'; completed_at preserved."""
    from migrate_z3 import migrate_record

    result = migrate_record(_TASK_DONE_BACKUP)

    assert result["status"] == "completed"
    assert result["completed_at"] == _TASK_DONE_BACKUP["completed_at"]


def test_migrate_z3_idea_shape(tmp_path):
    """After --apply: idea has 12 storage fields; spark_note→content;
    domain→topic; last_reviewed_at→last_reviewed; user_id absent."""
    from migrate_z3 import migrate_record

    result = migrate_record(_IDEA_BACKUP)

    storage_fields = {
        "id", "record_type", "title", "topic", "content", "status",
        "created_at", "updated_at", "last_reviewed", "completed_at",
        "source", "telegram_chat_id",
    }
    assert storage_fields == result.keys(), (
        f"Missing: {storage_fields - result.keys()}; Extra: {result.keys() - storage_fields}"
    )

    assert result["content"] == "The idea content goes here"  # spark_note → content
    assert result["topic"] == "system"                         # domain → topic
    assert result["last_reviewed"] is None                     # last_reviewed_at rename
    assert result["status"] == "open"                          # active → open
    assert result["completed_at"] is None

    for dropped in ("user_id", "spark_note", "domain", "context",
                    "review_cadence", "promotion_state", "promoted_task_id", "last_reviewed_at"):
        assert dropped not in result, f"Expected {dropped!r} to be dropped"


def test_migrate_z3_parking_lot_shape(tmp_path):
    """Parking lot records: dropped fields absent; active→open; 11 storage fields."""
    from migrate_z3 import migrate_record

    result = migrate_record(_PARKING_LOT_BACKUP)

    storage_fields = {
        "id", "record_type", "content", "reason", "status",
        "created_at", "updated_at", "last_reviewed", "completed_at",
        "source", "telegram_chat_id",
    }
    assert storage_fields == result.keys(), (
        f"Missing: {storage_fields - result.keys()}; Extra: {result.keys() - storage_fields}"
    )
    assert result["status"] == "open"
    assert result["content"] == "Parked item"  # title → content
    assert "user_id" not in result
    assert "title" not in result


# ---------------------------------------------------------------------------
# File-level migration tests
# ---------------------------------------------------------------------------

def test_migrate_z3_dry_run_no_write(tmp_path, monkeypatch):
    """--dry-run does not modify files."""
    tasks = tmp_path / "gtd-agent" / "users" / "test_user" / "tasks.jsonl"
    _write_jsonl(tasks, [_TASK_BACKUP])
    original_mtime = tasks.stat().st_mtime

    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    from migrate_z3 import run_migration
    run_migration(user_id="test_user", dry_run=True)

    assert tasks.stat().st_mtime == original_mtime
    assert not (tasks.parent / "tasks.jsonl.migration_z3_complete").exists()


def test_migrate_z3_per_file_sentinel(tmp_path, monkeypatch):
    """tasks.jsonl.migration_z3_complete written after tasks migrate;
    ideas sentinel written separately."""
    user_dir = tmp_path / "gtd-agent" / "users" / "test_user"
    tasks = user_dir / "tasks.jsonl"
    ideas = user_dir / "ideas.jsonl"
    _write_jsonl(tasks, [_TASK_BACKUP])
    _write_jsonl(ideas, [_IDEA_BACKUP])

    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    from migrate_z3 import run_migration
    run_migration(user_id="test_user", dry_run=False)

    assert (user_dir / "tasks.jsonl.migration_z3_complete").exists()
    assert (user_dir / "ideas.jsonl.migration_z3_complete").exists()


def test_migrate_z3_idempotent(tmp_path, monkeypatch):
    """Running --apply twice produces identical JSONL output."""
    tasks = tmp_path / "gtd-agent" / "users" / "test_user" / "tasks.jsonl"
    _write_jsonl(tasks, [_TASK_BACKUP])

    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    from migrate_z3 import run_migration

    run_migration(user_id="test_user", dry_run=False)
    first = tasks.read_text()

    # Delete sentinel so second run executes
    (tasks.parent / "tasks.jsonl.migration_z3_complete").unlink()
    run_migration(user_id="test_user", dry_run=False)
    second = tasks.read_text()

    assert first == second


def test_migrate_z3_second_run_no_op(tmp_path, monkeypatch, capsys):
    """With sentinel present, second run does not modify files."""
    tasks = tmp_path / "gtd-agent" / "users" / "test_user" / "tasks.jsonl"
    _write_jsonl(tasks, [_TASK_BACKUP])

    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    from migrate_z3 import run_migration

    run_migration(user_id="test_user", dry_run=False)
    mtime_after_first = tasks.stat().st_mtime

    run_migration(user_id="test_user", dry_run=False)
    assert tasks.stat().st_mtime == mtime_after_first

    out = capsys.readouterr().out
    assert "already migrated" in out.lower()


def test_migrate_z3_preserves_source_data(tmp_path, monkeypatch):
    """All submission and channel fields preserved verbatim after migration."""
    task = {**_TASK_BACKUP, "waiting_for": "Bob", "notes": "Important note"}
    tasks = tmp_path / "gtd-agent" / "users" / "test_user" / "tasks.jsonl"
    _write_jsonl(tasks, [task])

    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    from migrate_z3 import run_migration
    run_migration(user_id="test_user", dry_run=False)

    records = _read_jsonl(tasks)
    assert records[0]["waiting_for"] == "Bob"
    assert records[0]["notes"] == "Important note"
    assert records[0]["source"] == "telegram_text"
    assert records[0]["telegram_chat_id"] == "8712103657"
    assert records[0]["created_at"] == task["created_at"]
    assert records[0]["updated_at"] == task["updated_at"]


def test_migrate_z3_parking_lot_done_to_open(tmp_path):
    """Parking lot record with status 'done' migrates to 'open'; no completion semantic in 2b."""
    from migrate_z3 import migrate_record

    done_pl = {**_PARKING_LOT_BACKUP, "status": "done", "completed_at": "2026-04-14T10:00:00+00:00"}
    result = migrate_record(done_pl)

    assert result["status"] == "open"


def test_migrate_z3_validate_storage_on_migrated_records(tmp_path, monkeypatch):
    """migrate_record output passes validate_storage for all three record types."""
    from migrate_z3 import migrate_record
    from validate import validate_storage

    cases = [
        ("task",        _TASK_BACKUP),
        ("idea",        _IDEA_BACKUP),
        ("parking_lot", _PARKING_LOT_BACKUP),
    ]
    for record_type, backup in cases:
        migrated = migrate_record(backup)
        vr = validate_storage(record_type, migrated)
        assert vr.valid, f"{record_type}: {vr.errors}"
