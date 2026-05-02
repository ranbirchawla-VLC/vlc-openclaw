"""get_events.py — list_events plugin tool for the GTD calendar.

Usage: python3 get_events.py '<json_args>'
Returns {ok: true, data: {events: [...]}} or {ok: false, error: "..."}.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import TZ, err, get_google_credentials, ok
from otel_common import _is_transient_google, extract_parent_context, get_tracer

from googleapiclient.discovery import build
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
_MAX_RETRIES = 3
_TOOL_NAME = "list_events"
_SPAN_NAME = "gtd.calendar.list_events"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
    "request.type":    "OPENCLAW_REQUEST_TYPE",
}


class _Input(BaseModel):
    calendar_id: str = "primary"
    time_min: str | None = None
    time_max: str | None = None
    max_results: int = 25


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seven_days_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _map_event(e: dict) -> dict:
    return {
        "id": e.get("id"),
        "summary": e.get("summary"),
        "start": e.get("start"),
        "end": e.get("end"),
        "attendees": e.get("attendees", []),
        "location": e.get("location"),
        "description": e.get("description"),
        "html_link": e.get("htmlLink"),
    }


def run_list_events(
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 25,
) -> dict:
    resolved_min = time_min or _now_iso()
    resolved_max = time_max or _seven_days_iso()

    tracer = get_tracer("gtd.calendar")
    parent_ctx = extract_parent_context()

    with tracer.start_as_current_span(_SPAN_NAME, context=parent_ctx) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        span.set_attribute("calendar.id", calendar_id)
        span.set_attribute("time_min", resolved_min)
        span.set_attribute("time_max", resolved_max)
        span.set_attribute("max_results", max_results)
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
                    result = service.events().list(
                        calendarId=calendar_id,
                        timeMin=resolved_min,
                        timeMax=resolved_max,
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy="startTime",
                    ).execute()
                    events = [_map_event(e) for e in result.get("items", [])]
                    span.set_attribute("calendar.event_count", len(events))
                    return {"events": events}
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
    try:
        result = run_list_events(
            calendar_id=inp.calendar_id,
            time_min=inp.time_min,
            time_max=inp.time_max,
            max_results=inp.max_results,
        )
    except Exception as exc:
        err(str(exc))
        return
    ok(result)


if __name__ == "__main__":
    main()
