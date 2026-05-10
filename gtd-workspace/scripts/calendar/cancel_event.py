"""cancel_event.py -- cancel_event plugin tool for the GTD calendar.

Deletes a calendar event. Notifies attendees by default.

Usage: python3 cancel_event.py '<json_args>'
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import GTDError, err, get_google_credentials, ok
from otel_common import _is_transient_google, attach_parent_trace_context, get_tracer

from googleapiclient.discovery import build
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
_MAX_RETRIES = 3
_TOOL_NAME = "cancel_event"
_SPAN_NAME = "gtd.calendar.cancel_event"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


class _Input(BaseModel):
    event_id:        str
    calendar_id:     str = "primary"
    send_updates:    str = "all"    # "all" | "externalOnly" | "none"
    user_id:         str | None = None


def run_cancel_event(
    event_id: str,
    calendar_id: str = "primary",
    send_updates: str = "all",
    user_id: str | None = None,
) -> dict:
    tracer = get_tracer("gtd.calendar")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        span.set_attribute("request.type", _TOOL_NAME)
        span.set_attribute("calendar.event_id", event_id)
        span.set_attribute("calendar.send_updates", send_updates)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        if user_id:
            span.set_attribute("user.id", user_id)

        try:
            creds = get_google_credentials(_SCOPES)
            service = build("calendar", "v3", credentials=creds)

            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES + 1):
                if attempt > 0:
                    time.sleep(1)
                try:
                    service.events().delete(
                        calendarId=calendar_id,
                        eventId=event_id,
                        sendUpdates=send_updates,
                    ).execute()
                    return {"cancelled": True, "event_id": event_id}
                except Exception as exc:
                    if _is_transient_google(exc):
                        last_exc = exc
                        continue
                    raise
            raise last_exc  # type: ignore[misc]

        except GTDError:
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.set_attribute("error.type", type(exc).__name__)
            raise GTDError(
                "calendar_api_error",
                f"Failed to cancel event: {exc}",
                error_type=type(exc).__name__,
            ) from exc


def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python cancel_event.py <args.json>"))
        return
    try:
        raw = json.loads(sys.argv[1])
        inp = _Input(**raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = run_cancel_event(
                event_id=inp.event_id,
                calendar_id=inp.calendar_id,
                send_updates=inp.send_updates,
                user_id=inp.user_id,
            )
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
