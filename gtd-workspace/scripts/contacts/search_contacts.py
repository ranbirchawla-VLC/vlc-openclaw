"""search_contacts.py -- search_contacts plugin tool.

Searches Google Contacts by name or email and returns matching contacts.

Usage: python3 search_contacts.py '<json_args>'
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))            # scripts/contacts/
sys.path.insert(0, str(_here.parent))     # scripts/

from pydantic import BaseModel
from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from contacts_api import search_contacts as _search

_TOOL_NAME = "search_contacts"
_SPAN_NAME = "gtd.contacts.search_contacts"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


class _Input(BaseModel):
    query:   str
    user_id: str | None = None


def search_contacts_tool(query: str, user_id: str | None = None) -> dict:
    tracer = get_tracer("gtd.contacts")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        span.set_attribute("request.type", _TOOL_NAME)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        if user_id:
            span.set_attribute("user.id", user_id)
        try:
            contacts = _search(query)
            span.set_attribute("contacts.result_count", len(contacts))
            return {"contacts": contacts, "total_count": len(contacts)}
        except GTDError:
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.set_attribute("error.type", type(exc).__name__)
            raise GTDError("contacts_api_error", f"Search failed: {exc}",
                           error_type=type(exc).__name__) from exc


def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python search_contacts.py <args.json>"))
        return
    try:
        raw = json.loads(sys.argv[1])
        inp = _Input(**raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = search_contacts_tool(inp.query, user_id=inp.user_id)
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
