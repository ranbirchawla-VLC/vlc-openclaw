"""migrate_to_simplified_shape.py -- migrate JSONL records to the 2b.2 simplified schema.

Reads existing task, idea, and parking-lot JSONL records; strips fields removed
in the 2b.2 spec simplification; renames parking_lot raw_text -> title.

Usage:
    python migrate_to_simplified_shape.py [--user-id USER_ID] [--apply]

--user-id    User ID to migrate. Falls back to OPENCLAW_USER_ID env var.
--apply      Write migrated records to disk. Default: dry-run (prints plan only).

Idempotent: re-running on already-migrated records produces identical output.
Backup: tasks.jsonl.bak-YYYY-MM-DD created before any write. Re-run protection:
exits with error if backup already exists for today.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from _tools_common import read_jsonl, user_path


# ---------------------------------------------------------------------------
# Field retention sets per record type
# ---------------------------------------------------------------------------

_TASK_RETAIN: frozenset[str] = frozenset({
    "id", "record_type", "title", "context", "due_date", "waiting_for", "created_at",
})

_IDEA_RETAIN: frozenset[str] = frozenset({
    "id", "record_type", "title", "created_at",
})

_PARKING_LOT_RETAIN: frozenset[str] = frozenset({
    "id", "record_type", "title", "created_at",
})


# ---------------------------------------------------------------------------
# Transformation functions (importable for tests)
# ---------------------------------------------------------------------------

def migrate_task(record: dict) -> dict:
    """Retain only the 2b.2 task fields."""
    return {k: v for k, v in record.items() if k in _TASK_RETAIN}


def migrate_idea(record: dict) -> dict:
    """Retain only the 2b.2 idea fields."""
    return {k: v for k, v in record.items() if k in _IDEA_RETAIN}


def migrate_parking_lot(record: dict) -> dict:
    """Retain 2b.2 parking_lot fields; rename raw_text -> title if needed."""
    result = {k: v for k, v in record.items() if k in _PARKING_LOT_RETAIN}
    if "raw_text" in record and "title" not in result:
        result["title"] = record["raw_text"]
    return result


# ---------------------------------------------------------------------------
# File-level migration
# ---------------------------------------------------------------------------

_FILE_CONFIG: list[tuple[str, object]] = [
    ("tasks.jsonl",       migrate_task),
    ("ideas.jsonl",       migrate_idea),
    ("parking-lot.jsonl", migrate_parking_lot),
]


def run_migration(user_id: str, apply: bool = False) -> list[dict]:
    """Migrate all JSONL files for user_id.

    Returns a list of per-file result dicts:
      {filename, before_count, after_count, backup_path (if apply)}

    Dry-run (apply=False): reads and transforms; does not write.
    Apply (apply=True): creates dated backup then rewrites each file.
    Re-run protection: if backup already exists for today, exits with SystemExit.
    Files absent from storage are skipped (empty result for that file).
    """
    base = user_path(user_id)
    today = date.today().isoformat()
    results: list[dict] = []

    for filename, transform in _FILE_CONFIG:
        path = base / filename
        if not path.exists():
            results.append({"filename": filename, "before_count": 0, "after_count": 0, "skipped": True})
            continue

        records = read_jsonl(path)
        migrated = [transform(r) for r in records]
        result: dict = {
            "filename": filename,
            "before_count": len(records),
            "after_count": len(migrated),
            "skipped": False,
        }

        if apply:
            backup_path = path.with_suffix(f".jsonl.bak-{today}")
            if backup_path.exists():
                print(
                    f"ERROR: backup {backup_path} already exists; "
                    "remove it manually before re-running --apply.",
                    file=sys.stderr,
                )
                sys.exit(1)
            path.rename(backup_path)
            with path.open("w", encoding="utf-8") as fh:
                for r in migrated:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            result["backup_path"] = str(backup_path)

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate GTD JSONL records to the 2b.2 simplified schema."
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("OPENCLAW_USER_ID", ""),
        help="User ID to migrate (default: OPENCLAW_USER_ID env var).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write migrated records to disk. Default: dry-run.",
    )
    args = parser.parse_args()

    if not args.user_id:
        print("ERROR: --user-id or OPENCLAW_USER_ID env var is required.", file=sys.stderr)
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Migration mode: {mode}  user: {args.user_id}")

    results = run_migration(args.user_id, apply=args.apply)
    for r in results:
        if r.get("skipped"):
            print(f"  {r['filename']}: absent, skipped")
        else:
            print(f"  {r['filename']}: {r['before_count']} -> {r['after_count']} records", end="")
            if "backup_path" in r:
                print(f"  (backup: {r['backup_path']})", end="")
            print()

    if not args.apply:
        print("\nDry-run complete. Pass --apply to write changes.")


if __name__ == "__main__":
    main()
