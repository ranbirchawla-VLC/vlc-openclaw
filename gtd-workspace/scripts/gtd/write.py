"""write.py -- validate, stamp, and persist a GTD record.

Internal module; imported by capture.py. Not registered with the gateway.
Returns the generated record id (str) on success; raises GTDError on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from common import GTDError, err
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from validate import validate
from _tools_common import append_jsonl, assert_user_match, new_id, now_iso, user_path


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
      storage_io_failed    -- OSError from the underlying append_jsonl call
    """
    tracer = get_tracer("gtd.write")
    with tracer.start_as_current_span("gtd.write") as span:
        span.set_attribute("agent.id", "gtd")
        record_type = record.get("record_type", "")
        span.set_attribute("write.record_type", record_type)

        try:
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
            try:
                append_jsonl(path, complete)
            except OSError as exc:
                raise GTDError(
                    "storage_io_failed",
                    f"Failed to write record to storage: {exc}",
                    path=str(path),
                    error_type=type(exc).__name__,
                ) from exc

            span.set_attribute("write.record_id", record_id)
            return record_id

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("Usage: python write.py <file.json>", file=sys.stderr)
        sys.exit(1)
    _record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    _requesting_user_id = _record.get("user_id", "")
    try:
        _record_id = write(_record, _requesting_user_id)
        print(json.dumps({"ok": True, "id": _record_id}))
    except GTDError as _exc:
        err(_exc)
