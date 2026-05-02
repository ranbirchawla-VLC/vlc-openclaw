"""Tests for calendar/get_event.py — get_event tool.

Each test guards a specific production failure mode; see inline comments.
Mocks at the googleapiclient.discovery.build boundary.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Server Error")


def _make_event_dict() -> dict:
    return {
        "id": "evt42",
        "summary": "Strategy session",
        "start": {"dateTime": "2026-05-06T14:00:00-06:00"},
        "end": {"dateTime": "2026-05-06T15:00:00-06:00"},
        "htmlLink": "https://cal.google.com/evt42",
        "organizer": {"email": "host@example.com"},
    }


def _make_service_mock(event: dict | None = None, side_effect: Exception | None = None) -> MagicMock:
    service = MagicMock()
    execute = service.events.return_value.get.return_value.execute
    if side_effect is not None:
        execute.side_effect = side_effect
    else:
        execute.return_value = event or _make_event_dict()
    return service


def _make_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    import otel_common
    otel_common.configure_tracer_provider(exporter)
    return exporter


# ---------------------------------------------------------------------------
# Case 1: Happy path — full event object returned
# Guards: return shape wrong; raw API dict not passed through.
# ---------------------------------------------------------------------------

def test_happy_path_returns_event() -> None:
    from get_event import run_get_event

    mock_service = _make_service_mock()

    with patch("get_event.build", return_value=mock_service), \
         patch("get_event.get_google_credentials", return_value=MagicMock()):
        result = run_get_event(event_id="evt42")

    assert result["event"]["id"] == "evt42"
    assert result["event"]["summary"] == "Strategy session"
    assert "organizer" in result["event"]


# ---------------------------------------------------------------------------
# Case 2: Missing event_id — err() called (pydantic required field)
# Guards: missing required field not caught; None passed to API.
# ---------------------------------------------------------------------------

def test_missing_event_id_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_event import main

    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_event.py", "{}"]
        main()

    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Case 3: OAuth credential failure — err() called, names the issue
# Guards: EnvironmentError unhandled; raw traceback surfaces to gateway.
# ---------------------------------------------------------------------------

def test_oauth_credential_failure_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_event import main

    with patch("get_event.get_google_credentials",
               side_effect=EnvironmentError("Required environment variable not set: GOOGLE_OAUTH_CREDENTIALS")), \
         pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_event.py", '{"event_id": "evt42"}']
        main()

    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "GOOGLE_OAUTH_CREDENTIALS" in out["error"]


# ---------------------------------------------------------------------------
# Case 4: Transient error (5xx) — retries and succeeds
# Guards: no retry on 5xx; single failure kills the call.
# time.sleep mocked to avoid real seconds.
# ---------------------------------------------------------------------------

def test_transient_error_retries_and_succeeds() -> None:
    from get_event import run_get_event

    call_count = {"n": 0}

    def execute_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _make_http_error(503)
        return _make_event_dict()

    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.side_effect = execute_side_effect

    with patch("get_event.build", return_value=mock_service), \
         patch("get_event.get_google_credentials", return_value=MagicMock()), \
         patch("get_event.time.sleep") as mock_sleep:
        result = run_get_event(event_id="evt42")

    assert result["event"]["id"] == "evt42"
    mock_sleep.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Case 5: Not found (404) — err() on first attempt, no retry
# Guards: 404 retried; non-existent event causes silent loops.
# ---------------------------------------------------------------------------

def test_not_found_surfaces_error_no_retry(capsys: pytest.CaptureFixture) -> None:
    from get_event import main

    mock_service = _make_service_mock(side_effect=_make_http_error(404))

    with patch("get_event.build", return_value=mock_service), \
         patch("get_event.get_google_credentials", return_value=MagicMock()), \
         patch("get_event.time.sleep") as mock_sleep, \
         pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_event.py", '{"event_id": "evt42"}']
        main()

    assert exc_info.value.code == 1
    mock_sleep.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Case 6: OTEL span emitted with correct attributes on success
# Guards: span missing; wrong name; calendar.event_id absent.
# ---------------------------------------------------------------------------

def test_otel_span_attrs_on_success() -> None:
    from get_event import run_get_event

    exporter = _make_exporter()
    mock_service = _make_service_mock()

    with patch("get_event.build", return_value=mock_service), \
         patch("get_event.get_google_credentials", return_value=MagicMock()):
        run_get_event(event_id="evt42", calendar_id="primary")

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.calendar.get_event"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs["agent.id"] == "gtd"
    assert attrs["tool.name"] == "get_event"
    assert attrs["calendar.id"] == "primary"
    assert attrs["calendar.event_id"] == "evt42"


# ---------------------------------------------------------------------------
# Case 7: Invalid JSON args — err() called
# Guards: JSON parse error propagates uncaught.
# ---------------------------------------------------------------------------

def test_invalid_json_args_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_event import main

    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_event.py", "not-json"]
        main()

    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Case 8: Transient error exhausted — err() called after _MAX_RETRIES+1 attempts
# Guards: retry exhaustion not surfaced; real seconds accumulate without sleep mock.
# Symmetric with test_get_events.py Case 8.
# ---------------------------------------------------------------------------

def test_transient_error_exhausted_calls_err(capsys: pytest.CaptureFixture) -> None:
    from get_event import _MAX_RETRIES, main

    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.side_effect = _make_http_error(503)

    with patch("get_event.build", return_value=mock_service), \
         patch("get_event.get_google_credentials", return_value=MagicMock()), \
         patch("get_event.time.sleep") as mock_sleep, \
         pytest.raises(SystemExit) as exc_info:
        sys.argv = ["get_event.py", '{"event_id": "evt42"}']
        main()

    assert exc_info.value.code == 1
    assert mock_sleep.call_count == _MAX_RETRIES
    assert mock_service.events.return_value.get.return_value.execute.call_count == _MAX_RETRIES + 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
