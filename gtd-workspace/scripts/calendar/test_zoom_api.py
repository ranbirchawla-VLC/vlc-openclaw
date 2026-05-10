"""Tests for calendar/zoom_api.py.

Tests: token success, token auth failure, token missing key,
meeting success, meeting API error, meeting span attributes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, str(Path(__file__).parent.parent))

import otel_common

_TEST_CREDS = {
    "account_id": "test-acct-id",
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
}

_TOKEN_RESP = {"access_token": "fake-token-abc"}

_MEETING_RESP = {
    "id": 99887766,
    "join_url": "https://us06web.zoom.us/j/99887766",
    "password": "abc123",
}


def _mock_http_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


# ---------------------------------------------------------------------------
# Test 1: get_zoom_token success
# ---------------------------------------------------------------------------

def test_get_zoom_token_success() -> None:
    """get_zoom_token returns access_token string on 200.

    Production failure: all Zoom meeting creation fails with zoom_auth_error.
    """
    from zoom_api import get_zoom_token

    with patch("zoom_api.httpx.post", return_value=_mock_http_response(_TOKEN_RESP)):
        token = get_zoom_token(creds=_TEST_CREDS)

    assert token == "fake-token-abc"


# ---------------------------------------------------------------------------
# Test 2: get_zoom_token auth failure (HTTP 401)
# ---------------------------------------------------------------------------

def test_get_zoom_token_auth_failure() -> None:
    """HTTPStatusError on token call raises GTDError('zoom_auth_error').

    Production failure: bad credentials silently swallowed; no diagnostic.
    """
    from zoom_api import get_zoom_token
    from common import GTDError

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status.side_effect = _http_status_error(401)

    with patch("zoom_api.httpx.post", return_value=mock_resp):
        with pytest.raises(GTDError) as exc_info:
            get_zoom_token(creds=_TEST_CREDS)

    assert exc_info.value.code == "zoom_auth_error"


# ---------------------------------------------------------------------------
# Test 3: get_zoom_token missing access_token key in response
# ---------------------------------------------------------------------------

def test_get_zoom_token_missing_key() -> None:
    """KeyError on unexpected token response raises GTDError('zoom_auth_error').

    Production failure: Zoom API shape change silently breaks auth.
    """
    from zoom_api import get_zoom_token
    from common import GTDError

    with patch("zoom_api.httpx.post", return_value=_mock_http_response({"error": "denied"})):
        with pytest.raises(GTDError) as exc_info:
            get_zoom_token(creds=_TEST_CREDS)

    assert exc_info.value.code == "zoom_auth_error"


# ---------------------------------------------------------------------------
# Test 4: create_zoom_meeting success
# ---------------------------------------------------------------------------

def test_create_zoom_meeting_success() -> None:
    """create_zoom_meeting returns {join_url, meeting_id, password} on success.

    Production failure: add_zoom produces no meeting link in calendar event.
    """
    from zoom_api import create_zoom_meeting

    token_resp = _mock_http_response(_TOKEN_RESP)
    meeting_resp = _mock_http_response(_MEETING_RESP)

    with patch("zoom_api.httpx.post", side_effect=[token_resp, meeting_resp]):
        result = create_zoom_meeting(
            topic="Team sync",
            start_time="2026-05-12T14:00:00",
            duration_minutes=60,
            tz="America/Denver",
            creds=_TEST_CREDS,
        )

    assert result["join_url"] == "https://us06web.zoom.us/j/99887766"
    assert result["meeting_id"] == 99887766
    assert result["password"] == "abc123"


# ---------------------------------------------------------------------------
# Test 5: create_zoom_meeting API error on meeting creation
# ---------------------------------------------------------------------------

def test_create_zoom_meeting_api_error() -> None:
    """HTTP 400 on meeting creation raises GTDError('zoom_api_error').

    Production failure: bad meeting params surface as opaque error.
    """
    from zoom_api import create_zoom_meeting
    from common import GTDError

    token_resp = _mock_http_response(_TOKEN_RESP)
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.raise_for_status.side_effect = _http_status_error(400)

    with patch("zoom_api.httpx.post", side_effect=[token_resp, bad_resp]):
        with pytest.raises(GTDError) as exc_info:
            create_zoom_meeting(
                topic="Bad meeting",
                start_time="not-a-date",
                duration_minutes=30,
                tz="America/Denver",
                creds=_TEST_CREDS,
            )

    assert exc_info.value.code == "zoom_api_error"


# ---------------------------------------------------------------------------
# Test 6: create_zoom_meeting OTEL span attributes
# ---------------------------------------------------------------------------

def test_create_zoom_meeting_span_attributes() -> None:
    """Span 'gtd.zoom.create_meeting' emits topic, duration, timezone, meeting_id."""
    from zoom_api import create_zoom_meeting

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    token_resp = _mock_http_response(_TOKEN_RESP)
    meeting_resp = _mock_http_response(_MEETING_RESP)

    with patch("zoom_api.httpx.post", side_effect=[token_resp, meeting_resp]):
        create_zoom_meeting(
            topic="Span test",
            start_time="2026-05-12T14:00:00",
            duration_minutes=45,
            tz="America/Denver",
            creds=_TEST_CREDS,
        )

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.zoom.create_meeting")
    attrs = dict(span.attributes)
    assert attrs["zoom.topic"] == "Span test"
    assert attrs["zoom.duration_minutes"] == 45
    assert attrs["zoom.timezone"] == "America/Denver"
    assert attrs["zoom.meeting_id"] == "99887766"
