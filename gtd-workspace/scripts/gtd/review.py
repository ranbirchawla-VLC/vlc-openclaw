"""review.py -- LLM-visible plugin entry point for structured review scan.

Entry point is scaffolded; the review_scan() work function is pending a separate
design conversation to define review semantics (stale tasks, overdue items,
review cadence triggers, etc.). Returns scaffold state until that design lands.
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


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
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
# Work function (stub pending design loop)
# ---------------------------------------------------------------------------

def review_scan(limit: int | None = None, requesting_user_id: str = "") -> dict:
    """Stub: review semantics pending a separate design conversation.

    Returns scaffold state so the capability prompt can detect and surface
    the pending design state rather than returning incorrect data.
    """
    return {
        "items": [],
        "total_count": 0,
        "truncated": False,
        "review_available": False,
        "note": "review_design_pending",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review(limit: int | None = None, requesting_user_id: str = "") -> dict:
    """Run structured review scan. Returns {items, total_count, truncated, ...}."""
    config = get_gtd_config()
    effective_limit = min(limit if limit is not None else config.default_query_limit, config.max_query_limit)

    tracer = get_tracer("gtd.review")
    with tracer.start_as_current_span("gtd.review") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "review_gtd")
        span.set_attribute("request.type", "review")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        span.set_attribute("query.limit", effective_limit)

        try:
            if not requesting_user_id:
                raise GTDError("internal_error", "OPENCLAW_USER_ID not set")

            result = review_scan(limit=effective_limit, requesting_user_id=requesting_user_id)

            span.set_attribute("result.total_count", result["total_count"])

            return result

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

    requesting_user_id = os.environ.get("OPENCLAW_USER_ID", "")
    try:
        result = review(limit=inp.limit, requesting_user_id=requesting_user_id)
        ok(result)
    except GTDError as exc:
        err(exc)


if __name__ == "__main__":
    main()
