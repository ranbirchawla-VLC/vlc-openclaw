"""create_contact.py -- create_contact plugin tool.

Creates a new Google Contact with name, email, and optional phone.

Usage: python3 create_contact.py '<json_args>'
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))            # scripts/contacts/
sys.path.insert(0, str(_here.parent))     # scripts/

from pydantic import BaseModel
from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from contacts_api import create_contact as _create

_TOOL_NAME = "create_contact"
_SPAN_NAME = "gtd.contacts.create_contact"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


class _Input(BaseModel):
    name:       str
    email:      str
    phone:      str | None = None
    first_name: str | None = None
    last_name:  str | None = None
    company:    str | None = None
    title:      str | None = None
    notes:      str | None = None
    phone_type: str = "mobile"
    email_type: str = "work"


def create_contact_tool(
    name: str,
    email: str,
    phone: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    company: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    phone_type: str = "mobile",
    email_type: str = "work",
) -> dict:
    import os
    tracer = get_tracer("gtd.contacts")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        try:
            contact = _create(
                name, email, phone,
                first_name=first_name,
                last_name=last_name,
                company=company,
                title=title,
                notes=notes,
                phone_type=phone_type,
                email_type=email_type,
            )
            span.set_attribute("contacts.resource_name", contact.get("resource_name", ""))
            return {"contact": contact}
        except GTDError:
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise GTDError("contacts_api_error", f"Create failed: {exc}",
                           error_type=type(exc).__name__) from exc


def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python create_contact.py <args.json>"))
        return
    try:
        raw = json.loads(sys.argv[1])
        inp = _Input(**raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = create_contact_tool(
                inp.name, inp.email, inp.phone,
                first_name=inp.first_name,
                last_name=inp.last_name,
                company=inp.company,
                title=inp.title,
                notes=inp.notes,
                phone_type=inp.phone_type,
                email_type=inp.email_type,
            )
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
