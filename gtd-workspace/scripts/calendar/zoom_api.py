"""zoom_api.py -- Zoom Server-to-Server OAuth helpers for calendar tools.

Internal module; not registered with the gateway. Provides:
  get_zoom_token(creds=None) -> str
  create_zoom_meeting(topic, start_time, duration_minutes, tz, creds=None) -> dict

Credentials read from ~/.openclaw/credentials/zoom-creds.json unless creds dict passed directly.
"""

from __future__ import annotations

import json
from pathlib import Path

_here = Path(__file__).parent
import sys
sys.path.insert(0, str(_here.parent))  # scripts/

from common import GTDError
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode

import httpx

_CREDS_PATH = Path.home() / ".openclaw" / "credentials" / "zoom-creds.json"
_TOKEN_URL = "https://zoom.us/oauth/token"
_MEETINGS_URL = "https://zoom.us/v2/users/me/meetings"
_TIMEOUT = 10.0


def _load_creds() -> dict:
    try:
        return json.loads(_CREDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GTDError(
            "zoom_config_error",
            f"Cannot read Zoom credentials from {_CREDS_PATH}: {exc}",
        ) from exc


def get_zoom_token(creds: dict | None = None) -> str:
    """Return a Zoom Server-to-Server OAuth access token."""
    if creds is None:
        creds = _load_creds()
    try:
        resp = httpx.post(
            _TOKEN_URL,
            params={"grant_type": "account_credentials", "account_id": creds["account_id"]},
            auth=(creds["client_id"], creds["client_secret"]),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except (httpx.HTTPError, KeyError) as exc:
        raise GTDError(
            "zoom_auth_error",
            f"Failed to obtain Zoom token: {exc}",
            error_type=type(exc).__name__,
        ) from exc


def create_zoom_meeting(
    topic: str,
    start_time: str,
    duration_minutes: int,
    tz: str,
    creds: dict | None = None,
) -> dict:
    """Create a Zoom meeting and return {join_url, meeting_id, password}.

    start_time: ISO datetime string without UTC offset (local time in tz).
    tz: IANA timezone string.
    """
    tracer = get_tracer("gtd.zoom")
    with tracer.start_as_current_span("gtd.zoom.create_meeting") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("zoom.topic", topic)
        span.set_attribute("zoom.duration_minutes", duration_minutes)
        span.set_attribute("zoom.timezone", tz)
        try:
            token = get_zoom_token(creds)
            resp = httpx.post(
                _MEETINGS_URL,
                json={
                    "topic": topic,
                    "type": 2,
                    "start_time": start_time,
                    "duration": duration_minutes,
                    "timezone": tz,
                    "settings": {"join_before_host": True, "waiting_room": False},
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            result = {
                "join_url":   data["join_url"],
                "meeting_id": data["id"],
                "password":   data.get("password", ""),
            }
            span.set_attribute("zoom.meeting_id", str(result["meeting_id"]))
            return result
        except GTDError:
            raise
        except (httpx.HTTPError, KeyError) as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise GTDError(
                "zoom_api_error",
                f"Failed to create Zoom meeting: {exc}",
                error_type=type(exc).__name__,
            ) from exc
