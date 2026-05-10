"""Tests for calendar/create_event.py.

Tests: happy path, Zoom conferencing, attendee_names resolution,
contact_not_found error, retry on transient error, OTEL span, main() round-trip.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, str(Path(__file__).parent.parent))

import otel_common


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


def _make_service_mock(created_event: dict) -> MagicMock:
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = created_event
    return service


def _created_event(
    event_id: str = "new-evt-1",
    summary: str = "Team sync",
    zoom_url: str | None = None,
) -> dict:
    e: dict = {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": "2026-05-12T14:00:00", "timeZone": "America/Denver"},
        "end":   {"dateTime": "2026-05-12T15:00:00", "timeZone": "America/Denver"},
        "htmlLink": f"https://cal.google.com/{event_id}",
        "attendees": [],
    }
    if zoom_url:
        e["conferenceData"] = {
            "entryPoints": [{"entryPointType": "video", "uri": zoom_url}]
        }
    return e


# ---------------------------------------------------------------------------
# Test 1: happy path — creates event, returns projected fields
# ---------------------------------------------------------------------------

def test_create_event_happy_path() -> None:
    """run_create_event returns event dict on success.

    Production failure: no create_event tool; Trina cannot schedule meetings.
    """
    from create_event import run_create_event

    mock_event = _created_event()
    with patch("create_event.build", return_value=_make_service_mock(mock_event)), \
         patch("create_event.get_google_credentials", return_value=MagicMock()):
        result = run_create_event(
            summary="Team sync",
            start="2026-05-12T14:00:00",
            end="2026-05-12T15:00:00",
            tz="America/Denver",
        )

    assert result["event"]["id"] == "new-evt-1"
    assert result["event"]["summary"] == "Team sync"
    assert result["event"]["html_link"] is not None


# ---------------------------------------------------------------------------
# Test 2: add_zoom=True — conferenceData in request, zoom_url in response
# ---------------------------------------------------------------------------

def test_create_event_with_zoom() -> None:
    """add_zoom=True calls Zoom API, sets location to join_url, returns zoom_url.

    Production failure: Zoom not wired; attendees must create meeting separately.
    """
    from create_event import run_create_event

    zoom_join_url = "https://us06web.zoom.us/j/12345"
    mock_event = _created_event()

    with patch("create_event.build", return_value=_make_service_mock(mock_event)), \
         patch("create_event.get_google_credentials", return_value=MagicMock()), \
         patch("create_event.create_zoom_meeting", return_value={
             "join_url": zoom_join_url, "meeting_id": 12345, "password": "pw",
         }) as mock_zoom:
        result = run_create_event(
            summary="Zoom call",
            start="2026-05-12T14:00:00",
            end="2026-05-12T15:00:00",
            tz="America/Denver",
            add_zoom=True,
        )

    # Zoom meeting created with correct args
    mock_zoom.assert_called_once_with(
        topic="Zoom call",
        start_time="2026-05-12T14:00:00",
        duration_minutes=60,
        tz="America/Denver",
    )
    # join_url returned to caller
    assert result["event"]["zoom_url"] == zoom_join_url


# ---------------------------------------------------------------------------
# Test 3: attendee_names resolved to emails via contacts
# ---------------------------------------------------------------------------

def test_create_event_attendee_names_resolved() -> None:
    """attendee_names resolved to emails by Python; attendees list set on event.

    Production failure: LLM must look up contacts separately; multi-turn overhead.
    """
    from create_event import run_create_event

    mock_event = _created_event()
    mock_event["attendees"] = [{"email": "heather@example.com"}]

    with patch("create_event.build", return_value=_make_service_mock(mock_event)), \
         patch("create_event.get_google_credentials", return_value=MagicMock()), \
         patch("create_event._resolve_names_to_emails",
               return_value=(["heather@example.com"], [])):
        result = run_create_event(
            summary="Meeting",
            start="2026-05-12T14:00:00",
            end="2026-05-12T15:00:00",
            tz="America/Denver",
            attendee_names=["Heather VanHalen"],
        )

    assert len(result["event"]["attendees"]) == 1
    assert result["event"]["attendees"][0]["email"] == "heather@example.com"


# ---------------------------------------------------------------------------
# Test 4: contact_not_found when name cannot be resolved
# ---------------------------------------------------------------------------

def test_create_event_contact_not_found() -> None:
    """GTDError('contact_not_found') raised when attendee_name has no email.

    Production failure: unresolved name silently dropped; attendee not invited.
    """
    from create_event import run_create_event
    from common import GTDError

    with patch("create_event.build", return_value=MagicMock()), \
         patch("create_event.get_google_credentials", return_value=MagicMock()), \
         patch("create_event._resolve_names_to_emails",
               return_value=([], ["Unknown Person"])):
        with pytest.raises(GTDError) as exc_info:
            run_create_event(
                summary="Meeting",
                start="2026-05-12T14:00:00",
                end="2026-05-12T15:00:00",
                tz="America/Denver",
                attendee_names=["Unknown Person"],
            )

    assert exc_info.value.code == "contact_not_found"
    assert "Unknown Person" in exc_info.value.fields.get("unresolved_names", [])


# ---------------------------------------------------------------------------
# Test 5: transient error retried
# ---------------------------------------------------------------------------

def test_create_event_retries_on_transient() -> None:
    """Transient 503 retried; succeeds on second attempt.

    Production failure: transient API error surfaces as permanent failure.
    """
    from create_event import run_create_event

    mock_event = _created_event()
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.side_effect = [
        _make_http_error(503),
        mock_event,
    ]

    with patch("create_event.build", return_value=service), \
         patch("create_event.get_google_credentials", return_value=MagicMock()), \
         patch("create_event.time.sleep"):
        result = run_create_event(
            summary="Team sync",
            start="2026-05-12T14:00:00",
            end="2026-05-12T15:00:00",
            tz="America/Denver",
        )

    assert result["event"]["id"] == "new-evt-1"
    assert service.events.return_value.insert.return_value.execute.call_count == 2


# ---------------------------------------------------------------------------
# Test 6: OTEL span attributes
# ---------------------------------------------------------------------------

def test_create_event_span_attributes() -> None:
    """Span 'gtd.calendar.create_event' emits tool.name, request.type, calendar.tz, user.id."""
    from create_event import run_create_event

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    mock_event = _created_event()
    with patch("create_event.build", return_value=_make_service_mock(mock_event)), \
         patch("create_event.get_google_credentials", return_value=MagicMock()):
        run_create_event(
            summary="Team sync",
            start="2026-05-12T14:00:00",
            end="2026-05-12T15:00:00",
            tz="America/Denver",
            user_id="test-user-1",
        )

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.calendar.create_event")
    attrs = dict(span.attributes)
    assert attrs["tool.name"] == "create_event"
    assert attrs["request.type"] == "create_event"
    assert attrs["calendar.tz"] == "America/Denver"
    assert attrs["user.id"] == "test-user-1"


# ---------------------------------------------------------------------------
# Test 7: main() CLI round-trip
# ---------------------------------------------------------------------------

def test_create_event_main_cli(capsys) -> None:
    """main() reads argv JSON and writes ok envelope to stdout."""
    from create_event import main

    args = json.dumps({
        "summary": "Sync",
        "start": "2026-05-12T14:00:00",
        "end": "2026-05-12T15:00:00",
    })
    mock_event = _created_event()

    with patch("create_event.build", return_value=_make_service_mock(mock_event)), \
         patch("create_event.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["create_event.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert "event" in output["data"]
