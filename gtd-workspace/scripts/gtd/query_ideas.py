"""query_ideas.py -- LLM-visible plugin entry point to read GTD ideas.

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
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import read_jsonl, user_path

_IDEA_KEYS = frozenset({
    "id", "title", "topic", "content", "status",
    "created_at", "updated_at", "last_reviewed", "completed_at",
})


def _project(record: dict) -> dict:
    return {k: v for k, v in record.items() if k in _IDEA_KEYS}


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    user_id: str
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

def query_ideas(limit: int | None = None, requesting_user_id: str = "") -> dict:
    """Read ideas. Returns {items, total_count, truncated}."""
    config = get_gtd_config()
    effective_limit = min(limit if limit is not None else config.default_query_limit, config.max_query_limit)

    tracer = get_tracer("gtd.query_ideas")
    with tracer.start_as_current_span("gtd.query_ideas") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "query_ideas")
        span.set_attribute("request.type", "query")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        span.set_attribute("query.limit", effective_limit)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            path = user_path(requesting_user_id) / "ideas.jsonl"
            records = read_jsonl(path)

            total = len(records)
            items = [_project(r) for r in records[:effective_limit]]
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
        err(GTDError("internal_error", "Usage: python query_ideas.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = query_ideas(limit=inp.limit, requesting_user_id=inp.user_id)
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
