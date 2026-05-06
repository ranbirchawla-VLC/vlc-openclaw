"""review.py -- LLM-visible plugin entry point for structured review scan.

Reads stale records per record_type, applies read projection, auto-stamps
last_reviewed and updated_at on every returned record (D-A), returns
reviewed_at + by_type envelope.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from pydantic import BaseModel

from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import read_jsonl, user_path
from validate import validate_storage


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    user_id: str
    record_types:   list[str] | None = None   # default: all three
    stale_for_days: int | None = None          # default: 7
    limit_per_type: int | None = None          # default: 25, max: 25


# ---------------------------------------------------------------------------
# OTEL context from environment
# ---------------------------------------------------------------------------

_CONTEXT_ENV: dict[str, str] = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


# ---------------------------------------------------------------------------
# Projection key sets — source, telegram_chat_id, record_type excluded
# ---------------------------------------------------------------------------

_TASK_KEYS = frozenset({
    "id", "title", "context", "project", "priority", "waiting_for",
    "due_date", "notes", "status", "created_at", "updated_at",
    "last_reviewed", "completed_at",
})
_IDEA_KEYS = frozenset({
    "id", "title", "topic", "content", "status",
    "created_at", "updated_at", "last_reviewed", "completed_at",
})
_PARKLOT_KEYS = frozenset({
    "id", "content", "reason", "status",
    "created_at", "updated_at", "last_reviewed", "completed_at",
})

_FILE_INFO: dict[str, tuple[str, str, frozenset]] = {
    "tasks":       ("task",        "tasks.jsonl",       _TASK_KEYS),
    "ideas":       ("idea",        "ideas.jsonl",       _IDEA_KEYS),
    "parking_lot": ("parking_lot", "parking-lot.jsonl", _PARKLOT_KEYS),
}

_DEFAULT_RECORD_TYPES = ["tasks", "ideas", "parking_lot"]
_MAX_LIMIT_PER_TYPE = 25
_DEFAULT_STALE_DAYS = 7


# ---------------------------------------------------------------------------
# Stale filter helpers
# ---------------------------------------------------------------------------

def _is_stale(record: dict, cutoff_iso: str) -> bool:
    lr = record.get("last_reviewed")
    if lr is None:
        return True
    return str(lr) < cutoff_iso   # lexicographic valid for UTC isoformat


# ---------------------------------------------------------------------------
# Auto-stamp write (module-level so tests can patch it)
# ---------------------------------------------------------------------------

def _write_stamp_jsonl(
    path: Path,
    all_records: list[dict],
    ids_to_stamp: set[str],
    reviewed_at: str,
) -> None:
    """Write back all records, updating last_reviewed and updated_at on stamped ids.

    Atomic whole-file temp+rename; called once per JSONL file.
    Raises OSError on disk failure.
    """
    updated = []
    for r in all_records:
        if r.get("id") in ids_to_stamp:
            r = {**r, "last_reviewed": reviewed_at, "updated_at": reviewed_at}
        updated.append(r)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in updated:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review(
    record_types: list[str] | None = None,
    stale_for_days: int | None = None,
    limit_per_type: int | None = None,
    requesting_user_id: str = "",
) -> dict:
    """Run structured review scan per D-A.

    Returns {reviewed_at, by_type: {tasks, ideas, parking_lot}}.
    Each by_type entry is {items, total_count, truncated}.
    Auto-stamps last_reviewed and updated_at on returned records.

    Raises GTDError(storage_unavailable) if stamp write fails.
    """
    effective_record_types = record_types or _DEFAULT_RECORD_TYPES
    effective_stale = stale_for_days if stale_for_days is not None else _DEFAULT_STALE_DAYS
    effective_limit = min(
        limit_per_type if limit_per_type is not None else _MAX_LIMIT_PER_TYPE,
        _MAX_LIMIT_PER_TYPE,
    )

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=effective_stale)
    cutoff_iso = cutoff_dt.isoformat()

    tracer = get_tracer("gtd.review")
    with tracer.start_as_current_span("gtd.review") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "review")
        span.set_attribute("request.type", "review")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            base = user_path(requesting_user_id)
            reviewed_at = datetime.now(timezone.utc).isoformat()

            by_type: dict[str, dict] = {}
            # Map: filename → (all_records, ids_to_stamp)
            stamp_plan: dict[Path, tuple[list[dict], set[str]]] = {}
            total_returned = 0
            invalid_count = 0

            for rt_key in effective_record_types:
                info = _FILE_INFO.get(rt_key)
                if info is None:
                    by_type[rt_key] = {"items": [], "total_count": 0, "truncated": False}
                    continue

                record_type, filename, projection_keys = info
                path = base / filename
                all_records = read_jsonl(path)

                # Read-filter pass: validate_storage on each record (first child span)
                valid_records: list[dict] = []
                for rec in all_records:
                    vr = validate_storage(record_type, rec)
                    if vr.valid:
                        valid_records.append(rec)
                    else:
                        invalid_count += 1

                stale = [r for r in valid_records if _is_stale(r, cutoff_iso)]
                total = len(stale)
                page = stale[:effective_limit]
                truncated = total > effective_limit

                projected = [{k: v for k, v in r.items() if k in projection_keys}
                             for r in page]

                by_type[rt_key] = {
                    "items": projected,
                    "total_count": total,
                    "truncated": truncated,
                }
                total_returned += len(page)

                if page:
                    ids_to_stamp = {r["id"] for r in page}
                    stamp_plan[path] = (all_records, ids_to_stamp)

            span.set_attribute("result.total_count", total_returned)
            span.set_attribute("review.invalid_count", invalid_count)

            # Auto-stamp: one atomic write per file. validate_storage ran above in the
            # read-filter pass; only records that passed are in stamp_plan.
            for path, (all_records, ids_to_stamp) in stamp_plan.items():
                try:
                    _write_stamp_jsonl(path, all_records, ids_to_stamp, reviewed_at)
                except OSError as exc:
                    raise GTDError(
                        "storage_unavailable",
                        f"Failed to write review stamps: {exc}",
                        path=str(path),
                        error_type=type(exc).__name__,
                    ) from exc

            return {"reviewed_at": reviewed_at, "by_type": by_type}

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python review.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = review(
            record_types=inp.record_types,
            stale_for_days=inp.stale_for_days,
            limit_per_type=inp.limit_per_type,
            requesting_user_id=inp.user_id,
        )
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
