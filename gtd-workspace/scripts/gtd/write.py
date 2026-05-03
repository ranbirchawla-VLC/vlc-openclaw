"""write.py -- validate, stamp, and persist a GTD record.

Internal module; imported by capture.py. Not registered with the gateway.
Returns the generated record id (str) on success; raises GTDError on failure.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))           # scripts/gtd/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/

from common import GTDError
from otel_common import get_tracer
from validate import validate

# Load tools/common.py by path to avoid conflict with scripts/common.py
_spec = importlib.util.spec_from_file_location(
    "_gtd_tools_write",
    Path(__file__).parent.parent.parent / "tools" / "common.py",
)
_tools = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_tools)  # type: ignore[union-attr]

append_jsonl    = _tools.append_jsonl
assert_user_match = _tools.assert_user_match
new_id          = _tools.new_id
now_iso         = _tools.now_iso
user_path       = _tools.user_path


# ---------------------------------------------------------------------------
# File routing
# ---------------------------------------------------------------------------

_FILE_MAP: dict[str, str] = {
    "task":        "tasks.jsonl",
    "idea":        "ideas.jsonl",
    "parking_lot": "parking-lot.jsonl",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write(record: dict, requesting_user_id: str) -> str:
    """Validate, stamp, and persist a GTD record.

    Generates id, created_at, and updated_at before validation.
    Returns the generated record id (UUID4 string) on success.

    Raises GTDError with codes:
      unknown_record_type  -- record_type not in writable set
      isolation_violation  -- record["user_id"] != requesting_user_id
      validation_failed    -- validate() returns valid=False
    """
    tracer = get_tracer("gtd.write")
    with tracer.start_as_current_span("gtd.write") as span:
        span.set_attribute("agent.id", "gtd")

        record_type = record.get("record_type", "")
        span.set_attribute("write.record_type", record_type)

        filename = _FILE_MAP.get(record_type)
        if filename is None:
            raise GTDError(
                "unknown_record_type",
                f"Unsupported record_type for write: {record_type!r}",
                provided=record_type,
                allowed=list(_FILE_MAP.keys()),
            )

        record_user_id = record.get("user_id", "")
        try:
            assert_user_match(record_user_id, requesting_user_id)
        except PermissionError:
            raise GTDError(
                "isolation_violation",
                f"User isolation violation: record belongs to {record_user_id!r}, not {requesting_user_id!r}",
                record_user_id=record_user_id,
            )

        record_id = new_id()
        ts = now_iso()
        complete = {**record, "id": record_id, "created_at": ts, "updated_at": ts}

        vr = validate(record_type, complete)
        if not vr.valid:
            raise GTDError(
                "validation_failed",
                f"Record validation failed: {len(vr.errors)} error(s)",
                record_type=record_type,
                errors=[e.model_dump() for e in vr.errors],
            )

        path = user_path(requesting_user_id) / filename
        append_jsonl(path, complete)

        span.set_attribute("write.record_id", record_id)
        return record_id
