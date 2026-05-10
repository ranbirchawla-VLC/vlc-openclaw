"""Tests for calendar/update_event.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

sys.path.insert(0, str(Path(__file__).parent.parent))

import otel_common


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


def _patched_event(summary: str = "Updated sync") -> dict:
    return {
        "id": "evt1",
        "summary": summary,
        "start": {"dateTime": "2026-05-12T15:00:00"},
        "end":   {"dateTime": "2026-05-12T16:00:00"},
        "htmlLink": "https://cal.google.com/evt1",
        "attendees": [],
    }


# ---------------------------------------------------------------------------
# Test 1: happy path — updates summary only
# ---------------------------------------------------------------------------

def test_update_event_summary() -> None:
    """run_update_event patches only provided fields."""
    from update_event import run_update_event

    updated = _patched_event("Renamed sync")
    service = MagicMock()
    service.events.return_value.patch.return_value.execute.return_value = updated

    with patch("update_event.build", return_value=service), \
         patch("update_event.get_google_credentials", return_value=MagicMock()):
        result = run_update_event(
            event_id="evt1",
            tz="America/Denver",
            summary="Renamed sync",
        )

    patch_body = service.events.return_value.patch.call_args.kwargs["body"]
    assert patch_body == {"summary": "Renamed sync"}
    assert result["event"]["summary"] == "Renamed sync"


# ---------------------------------------------------------------------------
# Test 2: no_fields_to_update when no fields provided
# ---------------------------------------------------------------------------

def test_update_event_no_fields() -> None:
    """GTDError('no_fields_to_update') raised when patch body would be empty."""
    from update_event import run_update_event
    from common import GTDError

    with patch("update_event.build", return_value=MagicMock()), \
         patch("update_event.get_google_credentials", return_value=MagicMock()):
        with pytest.raises(GTDError) as exc_info:
            run_update_event(event_id="evt1", tz="America/Denver")

    assert exc_info.value.code == "no_fields_to_update"


# ---------------------------------------------------------------------------
# Test 5: add_zoom=True fetches event for timing, sets location to join_url
# ---------------------------------------------------------------------------

def test_update_event_add_zoom() -> None:
    """add_zoom=True fetches existing event, creates Zoom meeting, sets location."""
    from update_event import run_update_event

    existing_event = {
        "id": "evt1",
        "summary": "Team sync",
        "start": {"dateTime": "2026-05-12T14:00:00-06:00"},
        "end":   {"dateTime": "2026-05-12T15:00:00-06:00"},
    }
    updated = _patched_event("Team sync")
    updated["location"] = "https://us06web.zoom.us/j/55544433"

    service = MagicMock()
    service.events.return_value.get.return_value.execute.return_value = existing_event
    service.events.return_value.patch.return_value.execute.return_value = updated

    zoom_result = {"join_url": "https://us06web.zoom.us/j/55544433", "meeting_id": 55544433, "password": ""}

    with patch("update_event.build", return_value=service), \
         patch("update_event.get_google_credentials", return_value=MagicMock()), \
         patch("update_event.create_zoom_meeting", return_value=zoom_result) as mock_zoom:
        result = run_update_event(event_id="evt1", tz="America/Denver", add_zoom=True)

    mock_zoom.assert_called_once_with(
        topic="Team sync",
        start_time="2026-05-12T14:00:00",
        duration_minutes=60,
        tz="America/Denver",
    )
    patch_body = service.events.return_value.patch.call_args.kwargs["body"]
    assert patch_body["location"] == "https://us06web.zoom.us/j/55544433"
    assert result["event"]["zoom_url"] == "https://us06web.zoom.us/j/55544433"


# ---------------------------------------------------------------------------
# Test 3: contact_not_found propagates from attendee_names
# ---------------------------------------------------------------------------

def test_update_event_contact_not_found() -> None:
    """contact_not_found raised when attendee_name unresolvable."""
    from update_event import run_update_event
    from common import GTDError

    with patch("update_event.build", return_value=MagicMock()), \
         patch("update_event.get_google_credentials", return_value=MagicMock()), \
         patch("update_event._resolve_names_to_emails",
               return_value=([], ["Ghost Person"])):
        with pytest.raises(GTDError) as exc_info:
            run_update_event(
                event_id="evt1",
                tz="America/Denver",
                attendee_names=["Ghost Person"],
            )

    assert exc_info.value.code == "contact_not_found"


# ---------------------------------------------------------------------------
# Test 4: main() CLI round-trip
# ---------------------------------------------------------------------------

def test_update_event_main_cli(capsys) -> None:
    """main() reads argv JSON and writes ok envelope to stdout."""
    from update_event import main

    args = json.dumps({"event_id": "evt1", "summary": "Renamed"})
    with patch("update_event.build",
               return_value=MagicMock(
                   **{"events.return_value.patch.return_value.execute.return_value":
                      _patched_event("Renamed")}
               )), \
         patch("update_event.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["update_event.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
