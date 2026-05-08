"""complete.py -- LLM-visible plugin entry point to mark a GTD record as done.

Accepts user_id, record_id, and record_type. Finds the record in storage,
sets status="completed", completed_at=<now>, updated_at=<now>, rewrites the
JSONL file atomically, and returns {"completed": <projection>}.

Only task and idea support completion. parking_lot stays status="open" until 2d.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from pydantic import BaseModel

from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import read_jsonl, user_path
from profile import require_profile


# ---------------------------------------------------------------------------
# Supported record types for completion
# ---------------------------------------------------------------------------

_COMPLETABLE: frozenset[str] = frozenset({"task", "idea"})

_FILE_MAP: dict[str, str] = {
    "task": "tasks.jsonl",
    "idea": "ideas.jsonl",
}

# Per-type read projections (strips source, telegram_chat_id, record_type)
_TASK_KEYS = frozenset({
    "id", "title", "context", "project", "priority", "waiting_for",
    "due_date", "notes", "status", "created_at", "updated_at",
    "last_reviewed", "completed_at",
})
_IDEA_KEYS = frozenset({
    "id", "title", "topic", "content", "status",
    "created_at", "updated_at", "last_reviewed", "completed_at",
})
_PROJECTIONS: dict[str, frozenset] = {
    "task": _TASK_KEYS,
    "idea": _IDEA_KEYS,
}


def _project(record_type: str, record: dict) -> dict:
    return {k: v for k, v in record.items() if k in _PROJECTIONS[record_type]}


# ---------------------------------------------------------------------------
# Atomic JSONL rewrite
# ---------------------------------------------------------------------------

def _rewrite_jsonl_atomic(path: Path, records: list[dict]) -> None:
    """Write records to a .tmp file, fsync, then os.replace() into place."""
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    user_id: str
    record_id: str
    record_type: str


# ---------------------------------------------------------------------------
# OTEL context attributes
# ---------------------------------------------------------------------------

_CONTEXT_ENV: dict[str, str] = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def complete(
    record_id: str,
    record_type: str,
    requesting_user_id: str,
) -> dict:
    """Mark a task or idea as completed.

    Reads the JSONL file, finds the record by id, stamps status/completed_at/
    updated_at, rewrites atomically, and returns {"completed": <projection>}.

    Raises GTDError with codes:
      internal_error           -- requesting_user_id is empty
      unsupported_record_type  -- record_type is not task or idea
      record_not_found         -- no record with record_id in storage
      already_completed        -- record.status is already "completed"
      storage_io_failed        -- OSError during JSONL rewrite
    """
    tracer = get_tracer("gtd.complete")
    with tracer.start_as_current_span("gtd.complete") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "complete")
        span.set_attribute("complete.record_type", record_type)
        span.set_attribute("complete.record_id", record_id)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "requesting_user_id is empty")

            require_profile(requesting_user_id)

            if record_type not in _COMPLETABLE:
                raise GTDError(
                    "unsupported_record_type",
                    f"record_type {record_type!r} does not support completion; use task or idea",
                    provided=record_type,
                    allowed=sorted(_COMPLETABLE),
                )

            path = user_path(requesting_user_id) / _FILE_MAP[record_type]
            records = read_jsonl(path)

            idx = next(
                (i for i, r in enumerate(records) if r.get("id") == record_id),
                None,
            )
            if idx is None:
                raise GTDError(
                    "record_not_found",
                    f"No {record_type} with id {record_id!r} found in storage",
                    record_id=record_id,
                    record_type=record_type,
                )

            record = records[idx]
            if record.get("status") == "completed":
                raise GTDError(
                    "already_completed",
                    f"{record_type} {record_id!r} is already completed",
                    record_id=record_id,
                    record_type=record_type,
                )

            now = datetime.now(timezone.utc).isoformat()
            updated = {**record, "status": "completed", "completed_at": now, "updated_at": now}
            records[idx] = updated

            try:
                _rewrite_jsonl_atomic(path, records)
            except OSError as exc:
                raise GTDError(
                    "storage_io_failed",
                    f"Failed to rewrite storage: {exc}",
                    path=str(path),
                    error_type=type(exc).__name__,
                ) from exc

            return {"completed": _project(record_type, updated)}

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python complete.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = complete(inp.record_id, inp.record_type, inp.user_id)
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
