"""get_event.py — get_event plugin tool for the GTD calendar.

Usage: python3 get_event.py '<json_args>'
Returns {ok: true, data: {event: {...}}} or {ok: false, error: "..."}.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import TZ, err, get_google_credentials, ok
from otel_common import _is_transient_google, attach_parent_trace_context, get_tracer

from googleapiclient.discovery import build
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
_MAX_RETRIES = 3
_TOOL_NAME = "get_event"
_SPAN_NAME = "gtd.calendar.get_event"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
    "request.type":    "OPENCLAW_REQUEST_TYPE",
}


def _to_local(dt_field: dict | None) -> dict | None:
    if dt_field is None or "dateTime" not in dt_field:
        return dt_field
    dt = datetime.fromisoformat(dt_field["dateTime"])
    local = dt.astimezone(ZoneInfo(TZ))
    return {"dateTime": local.isoformat(), "timeZone": TZ}


def _normalize_event(event: dict) -> dict:
    event["start"] = _to_local(event.get("start"))
    event["end"] = _to_local(event.get("end"))
    return event


class _Input(BaseModel):
    event_id: str
    calendar_id: str = "primary"


def run_get_event(event_id: str, calendar_id: str = "primary") -> dict:
    tracer = get_tracer("gtd.calendar")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        span.set_attribute("calendar.id", calendar_id)
        span.set_attribute("calendar.event_id", event_id)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)

        try:
            creds = get_google_credentials(_SCOPES)
            service = build("calendar", "v3", credentials=creds)

            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES + 1):
                if attempt > 0:
                    time.sleep(1)
                try:
                    event = service.events().get(
                        calendarId=calendar_id,
                        eventId=event_id,
                    ).execute()
                    return {"event": _normalize_event(event)}
                except Exception as exc:
                    if _is_transient_google(exc):
                        last_exc = exc
                        continue
                    raise
            raise last_exc  # type: ignore[misc]

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            raise


def main() -> None:
    if len(sys.argv) < 2:
        err("missing args: expected JSON string as sys.argv[1]")
        return
    try:
        raw = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        err(f"invalid JSON args: {exc}")
        return
    try:
        inp = _Input(**raw)
    except Exception as exc:
        err(f"invalid input: {exc}")
        return
    with attach_parent_trace_context():
        try:
            result = run_get_event(event_id=inp.event_id, calendar_id=inp.calendar_id)
        except Exception as exc:
            err(str(exc))
            return
        ok(result)


if __name__ == "__main__":
    main()
