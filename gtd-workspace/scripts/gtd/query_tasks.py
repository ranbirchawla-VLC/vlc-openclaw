"""query_tasks.py -- LLM-visible plugin entry point to read GTD tasks.

Filters by context, due date range, and waiting_for presence.
Returns the standard Lock 6 envelope: {items, total_count, truncated}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from pydantic import BaseModel

from common import GTDError, err, get_gtd_config, ok
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import read_jsonl, user_path

_TASK_KEYS = frozenset({
    "id", "title", "context", "project", "priority", "waiting_for",
    "due_date", "notes", "status", "created_at", "updated_at",
    "last_reviewed", "completed_at",
})


def _project(record: dict) -> dict:
    return {k: v for k, v in record.items() if k in _TASK_KEYS}


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    context: str | None = None
    due_date_before: str | None = None
    due_date_after: str | None = None
    has_waiting_for: bool | None = None
    limit: int | None = None


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

def query_tasks(
    context: str | None = None,
    due_date_before: str | None = None,
    due_date_after: str | None = None,
    has_waiting_for: bool | None = None,
    limit: int | None = None,
    requesting_user_id: str = "",
) -> dict:
    """Read tasks, optionally filtered. Returns {items, total_count, truncated}.

    Tasks with no due_date are excluded from results when due_date_before or
    due_date_after is set; absence of due_date is not a match for any date range.
    """
    config = get_gtd_config()
    effective_limit = min(limit if limit is not None else config.default_query_limit, config.max_query_limit)

    tracer = get_tracer("gtd.query_tasks")
    with tracer.start_as_current_span("gtd.query_tasks") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "query_tasks")
        span.set_attribute("request.type", "query")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        if context is not None:
            span.set_attribute("query.context", context)
        if has_waiting_for is not None:
            span.set_attribute("query.has_waiting_for", has_waiting_for)
        span.set_attribute("query.limit", effective_limit)
        # query.status retired with the status filter (sub-step 2b.2 supervisor
        # decision); restore alongside any future status filter reintroduction.

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            path = user_path(requesting_user_id) / "tasks.jsonl"
            records = read_jsonl(path)

            filtered = records
            if context is not None:
                filtered = [r for r in filtered if r.get("context") == context]
            if due_date_before is not None:
                filtered = [r for r in filtered
                            if r.get("due_date") and r["due_date"] <= due_date_before]
            if due_date_after is not None:
                filtered = [r for r in filtered
                            if r.get("due_date") and r["due_date"] >= due_date_after]
            if has_waiting_for is True:
                filtered = [r for r in filtered if r.get("waiting_for")]
            elif has_waiting_for is False:
                filtered = [r for r in filtered if not r.get("waiting_for")]

            total = len(filtered)
            items = [_project(r) for r in filtered[:effective_limit]]
            truncated = total > effective_limit

            span.set_attribute("result.total_count", total)
            span.set_attribute("result.truncated", truncated)

            return {"items": items, "total_count": total, "truncated": truncated}

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python query_tasks.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    requesting_user_id = os.environ.get("OPENCLAW_USER_ID", "")
    try:
        result = query_tasks(
            context=inp.context,
            due_date_before=inp.due_date_before,
            due_date_after=inp.due_date_after,
            has_waiting_for=inp.has_waiting_for,
            limit=inp.limit,
            requesting_user_id=requesting_user_id,
        )
        ok(result)
    except GTDError as exc:
        err(exc)


if __name__ == "__main__":
    main()
