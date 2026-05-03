"""capture.py -- LLM-visible plugin entry point for capturing GTD records.

Validates and persists a single record. Delegates to write() which stamps
generated fields and enforces the data contract. OTEL span covers the full
capture path including write and validate as nested children.
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

from common import GTDError, err, ok
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from write import write


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    record: dict


# ---------------------------------------------------------------------------
# OTEL context attributes from environment
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

def capture(record: dict, requesting_user_id: str) -> dict:
    """Validate and persist a GTD record.

    Calls write(record, requesting_user_id) which stamps id/created_at, validates,
    and appends to the appropriate JSONL file.

    Returns {id, record_type} on success.
    Raises GTDError on any failure; callers translate to err() envelope.
    """
    tracer = get_tracer("gtd.capture")
    with tracer.start_as_current_span("gtd.capture") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "capture_gtd")
        span.set_attribute("request.type", "capture")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)

        record_type = record.get("record_type", "")
        span.set_attribute("capture.record_type", record_type)

        try:
            record_id = write(record, requesting_user_id)
            span.set_attribute("capture.record_id", record_id)
            return {"id": record_id, "record_type": record_type}
        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python capture.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    requesting_user_id = os.environ.get("OPENCLAW_USER_ID", "")
    try:
        result = capture(inp.record, requesting_user_id)
        ok(result)
    except GTDError as exc:
        err(exc)


if __name__ == "__main__":
    main()
