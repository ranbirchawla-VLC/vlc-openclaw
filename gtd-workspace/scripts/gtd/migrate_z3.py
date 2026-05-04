"""migrate_z3.py -- one-shot migration from backup shape to Z3 storage contract.

Runs once after backup restore. Removed after Z3 closes.

Invocation:
    python3 scripts/gtd/migrate_z3.py [--user-id USER_ID] [--dry-run | --apply]

Dry-run by default. --apply writes. Per-file sentinel (.migration_z3_complete)
prevents re-processing on second run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from _tools_common import user_path


# ---------------------------------------------------------------------------
# Field-level transforms
# ---------------------------------------------------------------------------

def _map_status(status: str) -> str:
    return {"active": "open", "done": "completed"}.get(status, status)


def _migrate_task(record: dict) -> dict:
    return {
        "id":               record["id"],
        "record_type":      "task",
        "title":            record["title"],
        "context":          record.get("context"),
        "project":          record.get("area") or record.get("project"),  # area → project; idempotent
        "priority":         record.get("priority"),
        "waiting_for":      record.get("waiting_for"),
        "due_date":         record.get("due_date"),
        "notes":            record.get("notes"),
        "status":           _map_status(record.get("status", "open")),
        "created_at":       record["created_at"],
        "updated_at":       record["updated_at"],
        "last_reviewed":    record.get("last_reviewed"),  # None if absent; idempotent
        "completed_at":     record.get("completed_at"),
        "source":           record["source"],
        "telegram_chat_id": record["telegram_chat_id"],
    }


def _migrate_idea(record: dict) -> dict:
    return {
        "id":               record["id"],
        "record_type":      "idea",
        "title":            record["title"],
        "topic":            record.get("domain") or record.get("topic"),       # domain → topic; idempotent
        "content":          record.get("spark_note") or record.get("content", ""),  # spark_note → content; idempotent
        "status":           _map_status(record.get("status", "open")),
        "created_at":       record["created_at"],
        "updated_at":       record["updated_at"],
        "last_reviewed":    record.get("last_reviewed_at") or record.get("last_reviewed"),  # rename; idempotent
        "completed_at":     record.get("completed_at"),
        "source":           record["source"],
        "telegram_chat_id": record["telegram_chat_id"],
    }


def _migrate_parking_lot(record: dict) -> dict:
    return {
        "id":               record["id"],
        "record_type":      "parking_lot",
        "content":          record.get("title") or record.get("content", ""),  # title → content; idempotent
        "reason":           record.get("reason"),
        "status":           "open",  # parking_lot has no completion semantic in 2b
        "created_at":       record["created_at"],
        "updated_at":       record["updated_at"],
        "last_reviewed":    record.get("last_reviewed"),
        "completed_at":     record.get("completed_at"),
        "source":           record["source"],
        "telegram_chat_id": record["telegram_chat_id"],
    }


_MIGRATORS = {
    "task":        _migrate_task,
    "idea":        _migrate_idea,
    "parking_lot": _migrate_parking_lot,
}


def migrate_record(record: dict) -> dict:
    """Transform a single backup-shape record to the Z3 storage contract.

    Dispatches by record_type. Unknown types are returned unchanged.
    """
    migrator = _MIGRATORS.get(record.get("record_type", ""))
    if migrator is None:
        return record
    return migrator(record)


# ---------------------------------------------------------------------------
# File-level migration
# ---------------------------------------------------------------------------

_FILE_NAMES = ["tasks.jsonl", "ideas.jsonl", "parking-lot.jsonl"]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                try:
                    result.append(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
    return result


def _write_jsonl_atomic(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _migrate_file(path: Path, dry_run: bool) -> str:
    """Migrate one JSONL file. Returns "migrated", "skipped", or "absent"."""
    sentinel = path.parent / (path.name + ".migration_z3_complete")

    if sentinel.exists():
        print(f"  {path.name}: already migrated (sentinel present)")
        return "skipped"

    records = _read_jsonl(path)
    if not records:
        print(f"  {path.name}: absent or empty — skipping")
        return "absent"

    transformed = [migrate_record(r) for r in records]

    print(f"  {path.name}: {len(records)} record(s) to migrate"
          + (" [dry-run]" if dry_run else ""))
    for orig, new in zip(records, transformed):
        rt = orig.get("record_type", "?")
        status_change = f"{orig.get('status')} → {new.get('status')}"
        print(f"    {rt} {orig.get('id', '?')[:8]}: {status_change}")

    if not dry_run:
        _write_jsonl_atomic(path, transformed)
        sentinel.write_text("ok")
        print(f"  {path.name}: written; sentinel created")

    return "migrated"


def run_migration(user_id: str, dry_run: bool) -> None:
    """Run migration for all JSONL files under user_path(user_id)."""
    base = user_path(user_id)
    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating Z3 records for user {user_id!r}")
    print(f"  storage path: {base}")

    for fname in _FILE_NAMES:
        _migrate_file(base / fname, dry_run)

    if dry_run:
        print("\nDry-run complete. Re-run with --apply to write changes.")
    else:
        print("\nMigration complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Z3 one-shot storage migration")
    parser.add_argument("--user-id", default=os.environ.get("OPENCLAW_USER_ID", ""),
                        help="User ID (Telegram chat ID)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Show what would be done (default)")
    group.add_argument("--apply", dest="dry_run", action="store_false",
                       help="Write changes to disk")
    args = parser.parse_args()

    if not args.user_id:
        print("ERROR: --user-id required (or set OPENCLAW_USER_ID)", file=sys.stderr)
        sys.exit(1)

    run_migration(user_id=args.user_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
