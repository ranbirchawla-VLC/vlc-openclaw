"""capture.py -- LLM-visible plugin entry point for capturing GTD records.

Validates the submission contract, delegates to write() for system stamping
and persistence, projects the stored record per read-projection contract,
and returns {"captured": <projection>}.
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
from validate import validate_submission
from write import write


# ---------------------------------------------------------------------------
# Input model (unchanged for Z3; { text: string } reconciliation in 2b.2)
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    record: dict


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
# Read-projection per record_type
# Per segment 2 contracts: source, telegram_chat_id, record_type excluded.
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
_PROJECTIONS: dict[str, frozenset] = {
    "task":        _TASK_KEYS,
    "idea":        _IDEA_KEYS,
    "parking_lot": _PARKLOT_KEYS,
}


def _project(record_type: str, record: dict) -> dict:
    keys = _PROJECTIONS.get(record_type, frozenset())
    return {k: v for k, v in record.items() if k in keys}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture(
    record: dict,
    requesting_user_id: str,
    source: str = "",
    telegram_chat_id: str = "",
) -> dict:
    """Validate submission, stamp, persist, and return read projection.

    1. validate_submission — raises GTDError(submission_invalid) on failure.
    2. write() — stamps system fields, validates storage, persists.
    3. Projects stored record via per-type _project.
    4. Returns {"captured": <projection>}.

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
            vr = validate_submission(record_type, record)
            if not vr.valid:
                raise GTDError(
                    vr.code,
                    f"Submission validation failed: {len(vr.errors)} error(s)",
                    record_type=record_type,
                    errors=[e.model_dump() for e in vr.errors],
                )

            stored = write(record, requesting_user_id, source, telegram_chat_id)
            projection = _project(record_type, stored)

            span.set_attribute("capture.record_id", stored["id"])
            return {"captured": projection}

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
    source           = os.environ.get("OPENCLAW_CHANNEL_TYPE", "")
    telegram_chat_id = os.environ.get("OPENCLAW_CHANNEL_PEER_ID", "")

    try:
        result = capture(inp.record, requesting_user_id, source, telegram_chat_id)
        ok(result)
    except GTDError as exc:
        err(exc)


if __name__ == "__main__":
    main()
