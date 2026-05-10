"""create_event.py -- create_event plugin tool for the GTD calendar.

Accepts attendee_names (display names) or attendees (email strings) or both.
Python resolves names to emails via the Contacts API before creating the event.
Returns contact_not_found for any name that cannot be resolved.

Usage: python3 create_event.py '<json_args>'
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import DATA_ROOT, TZ, GTDError, err, get_google_credentials, ok
from otel_common import _is_transient_google, attach_parent_trace_context, get_tracer
from zoom_api import create_zoom_meeting

from googleapiclient.discovery import build
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/contacts.other.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
]
_MAX_RETRIES = 3
_TOOL_NAME = "create_event"
_SPAN_NAME = "gtd.calendar.create_event"

_CONTEXT_ENV = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


class _Input(BaseModel):
    user_id:         str | None = None
    summary:         str
    start:           str                    # ISO datetime string, no offset (local time)
    end:             str                    # ISO datetime string, no offset (local time)
    timezone:        str | None = None      # IANA string; resolved from profile if absent
    description:     str | None = None
    location:        str | None = None
    attendees:       list[str] = []         # email addresses
    attendee_names:  list[str] = []         # display names to resolve via Contacts
    add_zoom:        bool = False


def _duration_minutes(start: str, end: str) -> int:
    try:
        delta = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S") - datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        return max(1, int(delta.total_seconds() / 60))
    except ValueError:
        return 60


def _resolve_tz(user_id: str | None, timezone_override: str | None = None) -> str:
    if timezone_override:
        return timezone_override
    if user_id:
        profile_path = Path(DATA_ROOT) / "gtd-agent" / "users" / user_id / "profile.json"
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8")).get("timezone", TZ)
            except (json.JSONDecodeError, OSError):
                pass
    return TZ


def _resolve_names_to_emails(names: list[str]) -> tuple[list[str], list[str]]:
    """Resolve display names to email addresses via the Contacts API.

    Returns (resolved_emails, unresolved_names).
    """
    if not names:
        return [], []

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "contacts"))
    from contacts_api import get_primary_email

    resolved: list[str] = []
    unresolved: list[str] = []
    for name in names:
        email = get_primary_email(name)
        if email:
            resolved.append(email)
        else:
            unresolved.append(name)
    return resolved, unresolved


def run_create_event(
    summary: str,
    start: str,
    end: str,
    tz: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    attendee_names: list[str] | None = None,
    add_zoom: bool = False,
    user_id: str | None = None,
) -> dict:
    tracer = get_tracer("gtd.calendar")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", _TOOL_NAME)
        span.set_attribute("request.type", _TOOL_NAME)
        span.set_attribute("calendar.tz", tz)
        span.set_attribute("calendar.add_zoom", add_zoom)
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)
        if user_id:
            span.set_attribute("user.id", user_id)

        try:
            # Resolve display names to emails
            resolved_emails: list[str] = list(attendees or [])
            unresolved: list[str] = []
            if attendee_names:
                extra, unresolved = _resolve_names_to_emails(attendee_names)
                resolved_emails.extend(extra)

            if unresolved:
                raise GTDError(
                    "contact_not_found",
                    f"Could not find contact(s) in Google Contacts: {', '.join(unresolved)}",
                    unresolved_names=unresolved,
                )

            # Build event body
            event_body: dict = {
                "summary": summary,
                "start": {"dateTime": start, "timeZone": tz},
                "end":   {"dateTime": end,   "timeZone": tz},
            }
            # Zoom meeting — created before the Calendar event so join_url is available
            join_url: str | None = None
            if add_zoom:
                zoom = create_zoom_meeting(
                    topic=summary,
                    start_time=start,
                    duration_minutes=_duration_minutes(start, end),
                    tz=tz,
                )
                join_url = zoom["join_url"]

            if description:
                event_body["description"] = description
            # Physical location goes into description when Zoom URL takes the location field
            if location and join_url:
                existing_desc = event_body.get("description", "")
                event_body["description"] = f"Location: {location}\n\n{existing_desc}".strip()
            elif location:
                event_body["location"] = location
            if join_url:
                event_body["location"] = join_url
            if resolved_emails:
                event_body["attendees"] = [{"email": e} for e in resolved_emails]

            creds = get_google_credentials(_SCOPES)
            service = build("calendar", "v3", credentials=creds)

            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES + 1):
                if attempt > 0:
                    time.sleep(1)
                try:
                    event = service.events().insert(
                        calendarId="primary", body=event_body, sendUpdates="all"
                    ).execute()
                    span.set_attribute("calendar.event_id", event.get("id", ""))
                    return {
                        "event": {
                            "id":          event.get("id"),
                            "summary":     event.get("summary"),
                            "start":       event.get("start"),
                            "end":         event.get("end"),
                            "html_link":   event.get("htmlLink"),
                            "attendees":   event.get("attendees", []),
                            "zoom_url":    join_url,
                        }
                    }
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
                f"Failed to create event: {exc}",
                error_type=type(exc).__name__,
            ) from exc


def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python create_event.py <args.json>"))
        return
    try:
        raw = json.loads(sys.argv[1])
        inp = _Input(**raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    tz = _resolve_tz(inp.user_id, inp.timezone)

    with attach_parent_trace_context():
        try:
            result = run_create_event(
                summary=inp.summary,
                start=inp.start,
                end=inp.end,
                tz=tz,
                description=inp.description,
                location=inp.location,
                attendees=inp.attendees,
                attendee_names=inp.attendee_names,
                add_zoom=inp.add_zoom,
                user_id=inp.user_id,
            )
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
