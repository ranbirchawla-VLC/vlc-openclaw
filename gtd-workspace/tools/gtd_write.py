"""Persist validated GTD records to user-scoped JSONL storage.

Generates ID and timestamps, validates, enforces user isolation,
then appends to the correct JSONL file.

Usage: python3 gtd_write.py <record_type> <file.json>
       (uses user_id from the record as the requesting identity)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from common import append_jsonl, assert_user_match, new_id, now_iso, user_path
from gtd_validate import validate


# ---------------------------------------------------------------------------
# File routing
# ---------------------------------------------------------------------------

# Profile records are managed out-of-band (onboarding flow); not writable here.
_FILE_MAP: dict[str, str] = {
    "task":        "tasks.jsonl",
    "idea":        "ideas.jsonl",
    "parking_lot": "parking-lot.jsonl",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_record(record: dict, record_type: str, requesting_user_id: str) -> dict:
    """Validate and persist a GTD record.

    Generates id, created_at, and updated_at before validation.
    Enforces user isolation via assert_user_match (checked before validation).
    Returns { status, record_type, id } on success or
            { status, record_type, valid, errors } on failure.

    Never skips validation, writes to another user's path, or calls any LLM.
    """
    filename = _FILE_MAP.get(record_type)
    if filename is None:
        return {
            "status": "error",
            "record_type": record_type,
            "valid": False,
            "errors": [{"field": "record_type", "message": f"Unsupported record_type for write: {record_type}"}],
        }

    # Isolation check first — no work done for the wrong user
    record_user_id = record.get("user_id", "")
    try:
        assert_user_match(record_user_id, requesting_user_id)
    except PermissionError as exc:
        return {
            "status": "error",
            "record_type": record_type,
            "valid": False,
            "errors": [{"field": "user_id", "message": str(exc)}],
        }

    # Stamp generated fields before validation so the schema sees a complete record
    record_id = new_id()
    ts = now_iso()
    complete = {**record, "id": record_id, "created_at": ts, "updated_at": ts}

    result = validate(complete, record_type)
    if not result["valid"]:
        return {
            "status": "error",
            "record_type": record_type,
            "valid": False,
            "errors": result["errors"],
        }

    path = user_path(requesting_user_id) / filename
    append_jsonl(path, complete)

    return {"status": "ok", "record_type": record_type, "id": record_id}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: gtd_write.py <record_type> <file.json>")
        sys.exit(1)
    record_type = sys.argv[1]
    path = Path(sys.argv[2])
    record = json.loads(path.read_text(encoding="utf-8"))
    # CLI uses the record's own user_id as the requesting identity
    user_id = record.get("user_id", "")
    result = write_record(record, record_type, user_id)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)
