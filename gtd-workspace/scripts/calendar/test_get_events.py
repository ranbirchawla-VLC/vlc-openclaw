"""Tests for calendar/get_events.py — list_events tool.

Each test guards a specific production failure mode; see inline comments.
Mocks at the googleapiclient.discovery.build boundary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from googleapiclient.errors import HttpError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Server Error")


def _make_service_mock(items: list | None = None) -> MagicMock:
    """Return a mock Google Calendar service whose events().list().execute() returns items."""
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": items if items is not None else [],
    }
    return service


def _make_event(
    event_id: str = "evt1",
    summary: str = "Team standup",
    html_link: str = "https://cal.google.com/evt1",
    attendees: list | None = None,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    e: dict = {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": "2026-05-05T10:00:00-06:00"},
        "end": {"dateTime": "2026-05-05T10:30:00-06:00"},
        "htmlLink": html_link,
    }
    if attendees is not None:
        e["attendees"] = attendees
    if location is not None:
        e["location"] = location
    if description is not None:
        e["description"] = description
    return e


def _make_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    import otel_common
    otel_common.configure_tracer_provider(exporter)
    return exporter


# ---------------------------------------------------------------------------
# Case 1: Happy path — events returned with correct field mapping
# Guards: htmlLink -> html_link; absent attendees -> []; absent location/description -> null.
# ---------------------------------------------------------------------------

def test_happy_path_returns_events(capsys: pytest.CaptureFixture) -> None:
    from get_events import run_list_events

    event = _make_event(attendees=[{"email": "a@b.com"}], location="Room 1", description="Sync")
    mock_service = _make_service_mock([event])

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()):
        result = run_list_events()

    assert result["events"][0] == {
        "id": "evt1",
        "summary": "Team standup",
        "start": {"dateTime": "2026-05-05T10:00:00-06:00"},
        "end": {"dateTime": "2026-05-05T10:30:00-06:00"},
        "attendees": [{"email": "a@b.com"}],
        "location": "Room 1",
        "description": "Sync",
        "html_link": "https://cal.google.com/evt1",
    }


# ---------------------------------------------------------------------------
# Case 2: Empty results — events: [] not None
# Guards: None-vs-empty bug; key must be present.
# ---------------------------------------------------------------------------

def test_empty_results_returns_empty_list() -> None:
    from get_events import run_list_events

    mock_service = _make_service_mock([])

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()):
        result = run_list_events()

    assert result["events"] == []


# ---------------------------------------------------------------------------
# Case 3: Default args — calendar_id="primary", max_results=25, time bounds set
# Guards: defaults not wired; plugin call silently overrides explicit args.
# ---------------------------------------------------------------------------

def test_defaults_applied() -> None:
    from get_events import run_list_events

    mock_service = _make_service_mock()

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()):
        run_list_events()

    call_kwargs = mock_service.events.return_value.list.call_args.kwargs
    assert call_kwargs["calendarId"] == "primary"
    assert call_kwargs["maxResults"] == 25
    assert call_kwargs["timeMin"] is not None
    assert call_kwargs["timeMax"] is not None


# ---------------------------------------------------------------------------
# Case 4: Explicit args passed through verbatim
# Guards: defaults silently overriding explicit args.
# ---------------------------------------------------------------------------

def test_explicit_args_passed_through() -> None:
    from get_events import run_list_events

    mock_service = _make_service_mock()

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()):
        run_list_events(
            calendar_id="work@example.com",
            time_min="2026-05-01T00:00:00Z",
            time_max="2026-05-07T23:59:59Z",
            max_results=10,
        )

    call_kwargs = mock_service.events.return_value.list.call_args.kwargs
    assert call_kwargs["calendarId"] == "work@example.com"
    assert call_kwargs["timeMin"] == "2026-05-01T00:00:00Z"
    assert call_kwargs["timeMax"] == "2026-05-07T23:59:59Z"
    assert call_kwargs["maxResults"] == 10


# ---------------------------------------------------------------------------
# Case 5: OAuth credential failure — err() called with structured message
# Guards: EnvironmentError unhandled; raw traceback surfaced to gateway.
# ---------------------------------------------------------------------------

def test_oauth_credential_failure_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_events import main

    with patch("get_events.get_google_credentials",
               side_effect=EnvironmentError("Required environment variable not set: GOOGLE_OAUTH_CREDENTIALS")), \
         pytest.raises(SystemExit) as exc_info:
        main.__wrapped__ = None  # ensure we call main directly
        sys.argv = ["get_events.py", "{}"]
        main()

    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "GOOGLE_OAUTH_CREDENTIALS" in out["error"]


# ---------------------------------------------------------------------------
# Case 6: Permanent API error (4xx) — err() called, no retry
# Guards: 4xx retried; permanent errors silently swallowed.
# ---------------------------------------------------------------------------

def test_api_permanent_error_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_events import main

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.side_effect = _make_http_error(400)

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()), \
         patch("get_events.time.sleep") as mock_sleep, \
         pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_events.py", "{}"]
        main()

    assert exc_info.value.code == 1
    mock_sleep.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Case 7: Transient error (5xx) — retries and succeeds
# Guards: no retry loop; 5xx kills the call permanently.
# time.sleep mocked to avoid real seconds accumulating.
# ---------------------------------------------------------------------------

def test_transient_error_retries_and_succeeds() -> None:
    from get_events import run_list_events

    call_count = {"n": 0}

    def execute_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _make_http_error(503)
        return {"items": [_make_event()]}

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.side_effect = execute_side_effect

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()), \
         patch("get_events.time.sleep") as mock_sleep:
        result = run_list_events()

    assert len(result["events"]) == 1
    mock_sleep.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Case 8: Transient error exhausted — err() called after _MAX_RETRIES+1 attempts
# Guards: retry exhaustion not surfaced; real seconds accumulate without sleep mock.
# ---------------------------------------------------------------------------

def test_transient_error_exhausted_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_events import _MAX_RETRIES, main

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.side_effect = _make_http_error(503)

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()), \
         patch("get_events.time.sleep") as mock_sleep, \
         pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_events.py", "{}"]
        main()

    assert exc_info.value.code == 1
    assert mock_sleep.call_count == _MAX_RETRIES
    assert mock_service.events.return_value.list.return_value.execute.call_count == _MAX_RETRIES + 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Case 9: OTEL span emitted with correct attributes on success
# Guards: span not emitted; wrong name; required attributes absent.
# ---------------------------------------------------------------------------

def test_otel_span_attrs_on_success() -> None:
    from get_events import run_list_events

    exporter = _make_exporter()
    mock_service = _make_service_mock([_make_event()])

    with patch("get_events.build", return_value=mock_service), \
         patch("get_events.get_google_credentials", return_value=MagicMock()):
        run_list_events(calendar_id="primary", max_results=25)

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.calendar.list_events"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs["agent.id"] == "gtd"
    assert attrs["tool.name"] == "list_events"
    assert attrs["calendar.id"] == "primary"
    assert attrs["calendar.event_count"] == 1
    assert attrs["max_results"] == 25
    assert "time_min" in attrs
    assert "time_max" in attrs


# ---------------------------------------------------------------------------
# Case 10: Invalid JSON args — err() called
# Guards: JSON parse error propagates uncaught to gateway as unformatted crash.
# ---------------------------------------------------------------------------

def test_invalid_json_args_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_events import main

    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_events.py", "not-json"]
        main()

    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
