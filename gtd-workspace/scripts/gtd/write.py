"""write.py -- stamp, validate, and persist a GTD record.

Internal module; imported by capture.py. Not registered with the gateway.
Returns the full stamped storage dict on success; raises GTDError on failure.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from common import GTDError, err
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from validate import validate_storage
from _tools_common import user_path


# ---------------------------------------------------------------------------
# File routing and optional field defaults
# ---------------------------------------------------------------------------

_FILE_MAP: dict[str, str] = {
    "task":        "tasks.jsonl",
    "idea":        "ideas.jsonl",
    "parking_lot": "parking-lot.jsonl",
}

# Optional submission fields that must be present in storage (as None when not supplied).
# Mirrors the Pydantic model optional fields; ensures the returned dict has all storage fields.
_OPTIONAL_FIELDS: dict[str, set[str]] = {
    "task":        {"context", "project", "priority", "waiting_for", "due_date", "notes"},
    "idea":        {"topic"},
    "parking_lot": {"reason"},
}


# ---------------------------------------------------------------------------
# Atomic append
# ---------------------------------------------------------------------------

def _append_jsonl_fsync(path: Path, record: dict) -> None:
    """Append record as a JSON line; fsync before close for durability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write(
    record: dict,
    requesting_user_id: str,
    source: str = "",
    telegram_chat_id: str = "",
) -> dict:
    """Stamp, validate against storage contract, and persist a GTD record.

    System fields stamped: id (uuid4), created_at, updated_at (= created_at),
    status ("open"), completed_at (null), last_reviewed (null).
    Channel fields source and telegram_chat_id persisted from args.

    Returns the full stamped storage dict on success.

    Raises GTDError with codes:
      internal_error       -- requesting_user_id is empty
      unknown_record_type  -- record_type not in writable set
      validation_failed    -- validate_storage() returns valid=False
      storage_io_failed    -- OSError from _append_jsonl_fsync
    """
    tracer = get_tracer("gtd.write")
    with tracer.start_as_current_span("gtd.write") as span:
        span.set_attribute("agent.id", "gtd")
        record_type = record.get("record_type", "")
        span.set_attribute("write.record_type", record_type)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            filename = _FILE_MAP.get(record_type)
            if filename is None:
                raise GTDError(
                    "unknown_record_type",
                    f"Unsupported record_type for write: {record_type!r}",
                    provided=record_type,
                    allowed=list(_FILE_MAP.keys()),
                )

            record_id = str(uuid4())
            ts = datetime.now(timezone.utc).isoformat()
            complete = {
                **record,
                "id":               record_id,
                "created_at":       ts,
                "updated_at":       ts,
                "status":           "open",
                "completed_at":     None,
                "last_reviewed":    None,
                "source":           source,
                "telegram_chat_id": telegram_chat_id,
            }
            # Ensure optional submission fields are explicitly present as None
            # so the returned dict has all storage fields.
            for field in _OPTIONAL_FIELDS.get(record_type, set()):
                complete.setdefault(field, None)

            vr = validate_storage(record_type, complete)
            if not vr.valid:
                raise GTDError(
                    "validation_failed",
                    f"Record validation failed: {len(vr.errors)} error(s)",
                    record_type=record_type,
                    errors=[e.model_dump() for e in vr.errors],
                )

            path = user_path(requesting_user_id) / filename
            try:
                _append_jsonl_fsync(path, complete)
            except OSError as exc:
                raise GTDError(
                    "storage_io_failed",
                    f"Failed to write record to storage: {exc}",
                    path=str(path),
                    error_type=type(exc).__name__,
                ) from exc

            span.set_attribute("write.record_id", record_id)
            return complete

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python write.py <file.json>", file=sys.stderr)
        sys.exit(1)
    _record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    _requesting_user_id = os.environ.get("OPENCLAW_USER_ID", "")
    _source = os.environ.get("OPENCLAW_CHANNEL_TYPE", "")
    _chat_id = os.environ.get("OPENCLAW_CHANNEL_PEER_ID", "")
    try:
        _stored = write(_record, _requesting_user_id, _source, _chat_id)
        print(json.dumps({"ok": True, "id": _stored["id"]}))
    except GTDError as _exc:
        err(_exc)
