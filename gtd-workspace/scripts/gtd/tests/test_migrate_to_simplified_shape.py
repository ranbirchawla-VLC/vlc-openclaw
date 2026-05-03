"""Tests for scripts/gtd/migrate_to_simplified_shape.py."""

import json
from pathlib import Path

import pytest

from migrate_to_simplified_shape import (
    migrate_idea,
    migrate_parking_lot,
    migrate_task,
    run_migration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. migrate_task drops excess fields and retains the 7 locked fields
# ---------------------------------------------------------------------------

def test_migrate_task_drops_excess_fields() -> None:
    record = {
        "id": "t1", "record_type": "task", "title": "Buy parts",
        "context": "@errands", "created_at": "2026-04-01T00:00:00+00:00",
        "user_id": "user1", "telegram_chat_id": "chat1",
        "priority": "normal", "energy": "medium", "status": "active",
        "source": "telegram_text", "updated_at": "2026-04-01T00:00:00+00:00",
    }
    result = migrate_task(record)
    assert set(result.keys()) <= {"id", "record_type", "title", "context", "due_date", "waiting_for", "created_at"}
    assert "user_id" not in result
    assert "priority" not in result
    assert "status" not in result
    assert "updated_at" not in result


# ---------------------------------------------------------------------------
# 2. migrate_task preserves all 7 retained fields
# ---------------------------------------------------------------------------

def test_migrate_task_preserves_retained_fields() -> None:
    record = {
        "id": "t1", "record_type": "task", "title": "Buy parts",
        "context": "@errands", "due_date": "2026-06-01",
        "waiting_for": "Alex", "created_at": "2026-04-01T00:00:00+00:00",
        "priority": "normal",
    }
    result = migrate_task(record)
    assert result["id"] == "t1"
    assert result["title"] == "Buy parts"
    assert result["due_date"] == "2026-06-01"
    assert result["waiting_for"] == "Alex"


# ---------------------------------------------------------------------------
# 3. migrate_idea drops excess fields
# ---------------------------------------------------------------------------

def test_migrate_idea_drops_excess_fields() -> None:
    record = {
        "id": "i1", "record_type": "idea", "title": "New feature idea",
        "created_at": "2026-04-01T00:00:00+00:00",
        "domain": "ai-automation", "context": "@computer",
        "review_cadence": "monthly", "status": "active",
        "user_id": "user1", "updated_at": "2026-04-01T00:00:00+00:00",
    }
    result = migrate_idea(record)
    assert set(result.keys()) == {"id", "record_type", "title", "created_at"}
    assert "domain" not in result
    assert "user_id" not in result


# ---------------------------------------------------------------------------
# 4. migrate_parking_lot renames raw_text to title
# ---------------------------------------------------------------------------

def test_migrate_parking_lot_renames_raw_text_to_title() -> None:
    record = {
        "id": "p1", "record_type": "parking_lot",
        "raw_text": "some stray thought", "created_at": "2026-04-01T00:00:00+00:00",
        "source": "telegram_text", "reason": "ambiguous_capture",
        "status": "active", "user_id": "user1",
    }
    result = migrate_parking_lot(record)
    assert result["title"] == "some stray thought"
    assert "raw_text" not in result
    assert "source" not in result


# ---------------------------------------------------------------------------
# 5. migrate_parking_lot is idempotent when title already present
# ---------------------------------------------------------------------------

def test_migrate_parking_lot_idempotent_with_title() -> None:
    record = {
        "id": "p1", "record_type": "parking_lot",
        "title": "already migrated", "created_at": "2026-04-01T00:00:00+00:00",
    }
    first = migrate_parking_lot(record)
    second = migrate_parking_lot(first)
    assert first == second
    assert second["title"] == "already migrated"


# ---------------------------------------------------------------------------
# 6. run_migration dry-run does not modify files
# ---------------------------------------------------------------------------

def test_run_migration_dry_run_does_not_write(storage: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_USER_ID", "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    _write_jsonl(tasks_file, [
        {"id": "t1", "record_type": "task", "title": "T1", "context": "@work",
         "created_at": "2026-04-01T00:00:00+00:00", "priority": "normal"},
    ])
    original_content = tasks_file.read_text()

    run_migration("user1", apply=False)

    assert tasks_file.read_text() == original_content


# ---------------------------------------------------------------------------
# 7. run_migration apply creates a dated backup before rewriting
# ---------------------------------------------------------------------------

def test_run_migration_apply_creates_backup(storage: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date
    monkeypatch.setenv("OPENCLAW_USER_ID", "user1")
    tasks_file = storage / "gtd-agent" / "users" / "user1" / "tasks.jsonl"
    _write_jsonl(tasks_file, [
        {"id": "t1", "record_type": "task", "title": "T1", "context": "@work",
         "created_at": "2026-04-01T00:00:00+00:00", "priority": "normal"},
    ])

    run_migration("user1", apply=True)

    today = date.today().isoformat()
    backup = tasks_file.with_suffix(f".jsonl.bak-{today}")
    assert backup.exists(), f"backup {backup} not created"

    migrated = _read_jsonl(tasks_file)
    assert len(migrated) == 1
    assert "priority" not in migrated[0]
    assert migrated[0]["title"] == "T1"


# ---------------------------------------------------------------------------
# 8. migrate_parking_lot with both raw_text and title keeps title
# ---------------------------------------------------------------------------

def test_migrate_parking_lot_both_fields_keeps_title() -> None:
    record = {
        "id": "p1", "record_type": "parking_lot",
        "raw_text": "raw value X",
        "title": "canonical value Y",
        "created_at": "2026-04-01T00:00:00+00:00",
        "source": "telegram_text",
    }
    result = migrate_parking_lot(record)
    assert result["title"] == "canonical value Y"
    assert "raw_text" not in result
