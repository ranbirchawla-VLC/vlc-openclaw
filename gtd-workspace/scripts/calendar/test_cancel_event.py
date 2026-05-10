"""Tests for calendar/cancel_event.py."""

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


# ---------------------------------------------------------------------------
# Test 1: happy path — cancels event, notifies attendees
# ---------------------------------------------------------------------------

def test_cancel_event_happy_path() -> None:
    """run_cancel_event returns {cancelled: true, event_id}."""
    from cancel_event import run_cancel_event

    service = MagicMock()
    service.events.return_value.delete.return_value.execute.return_value = None

    with patch("cancel_event.build", return_value=service), \
         patch("cancel_event.get_google_credentials", return_value=MagicMock()):
        result = run_cancel_event(event_id="evt1")

    assert result == {"cancelled": True, "event_id": "evt1"}
    delete_kwargs = service.events.return_value.delete.call_args.kwargs
    assert delete_kwargs["eventId"] == "evt1"
    assert delete_kwargs["sendUpdates"] == "all"


# ---------------------------------------------------------------------------
# Test 2: send_updates="none" skips notifications
# ---------------------------------------------------------------------------

def test_cancel_event_no_notifications() -> None:
    """send_updates='none' is passed through to the API."""
    from cancel_event import run_cancel_event

    service = MagicMock()
    service.events.return_value.delete.return_value.execute.return_value = None

    with patch("cancel_event.build", return_value=service), \
         patch("cancel_event.get_google_credentials", return_value=MagicMock()):
        run_cancel_event(event_id="evt1", send_updates="none")

    assert service.events.return_value.delete.call_args.kwargs["sendUpdates"] == "none"


# ---------------------------------------------------------------------------
# Test 3: transient error retried
# ---------------------------------------------------------------------------

def test_cancel_event_retries_on_transient() -> None:
    """503 retried; succeeds on second attempt."""
    from cancel_event import run_cancel_event

    service = MagicMock()
    service.events.return_value.delete.return_value.execute.side_effect = [
        _make_http_error(503),
        None,
    ]

    with patch("cancel_event.build", return_value=service), \
         patch("cancel_event.get_google_credentials", return_value=MagicMock()), \
         patch("cancel_event.time.sleep"):
        result = run_cancel_event(event_id="evt1")

    assert result["cancelled"] is True
    assert service.events.return_value.delete.return_value.execute.call_count == 2


# ---------------------------------------------------------------------------
# Test 4: main() CLI round-trip
# ---------------------------------------------------------------------------

def test_cancel_event_main_cli(capsys) -> None:
    """main() reads argv JSON and writes ok envelope to stdout."""
    from cancel_event import main

    args = json.dumps({"event_id": "evt1"})
    service = MagicMock()
    service.events.return_value.delete.return_value.execute.return_value = None

    with patch("cancel_event.build", return_value=service), \
         patch("cancel_event.get_google_credentials", return_value=MagicMock()), \
         patch.object(sys, "argv", ["cancel_event.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["data"]["cancelled"] is True
