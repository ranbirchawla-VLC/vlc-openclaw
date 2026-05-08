"""profile.py -- per-user profile storage for the GTD agent.

Internal module; not registered with the gateway. Provides read_profile,
write_profile, and require_profile. Profile lives at:
  {storage_root}/gtd-agent/users/{user_id}/profile.json

Fields: user_id, name, timezone (IANA), registered_at, updated_at.
"""

from __future__ import annotations

import json
import os
import sys
import zoneinfo
from datetime import datetime, timezone
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from common import GTDError
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode
from _tools_common import user_path


_PROFILE_FILENAME = "profile.json"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_profile(user_id: str) -> dict | None:
    """Return the user's profile dict, or None if no profile exists.

    Does not raise on missing file; callers use require_profile() when
    absence is an error.
    """
    path = user_path(user_id) / _PROFILE_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def require_profile(user_id: str) -> dict:
    """Return profile dict; raises GTDError('unknown_user') if not found.

    Call this after the empty-user_id check in each plugin tool to enforce
    the registration gate.
    """
    profile = read_profile(user_id)
    if profile is None:
        raise GTDError(
            "unknown_user",
            f"No profile found for user {user_id!r}. Say hello to Trina to get set up.",
            user_id=user_id,
        )
    return profile


# ---------------------------------------------------------------------------
# Write (atomic)
# ---------------------------------------------------------------------------

def _write_profile_atomic(path: Path, profile: dict) -> None:
    """Write profile to a .tmp file, fsync, then os.replace() into place."""
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_profile(
    user_id: str,
    name: str,
    timezone_str: str,
) -> dict:
    """Create or update the user's profile.

    Validates timezone_str with zoneinfo. Preserves registered_at on update.
    Returns the full profile dict.

    Raises GTDError with codes:
      invalid_timezone  -- timezone_str is not a valid IANA timezone
      storage_io_failed -- OSError during atomic write
    """
    tracer = get_tracer("gtd.profile")
    with tracer.start_as_current_span("gtd.write_profile") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("profile.user_id", user_id)
        span.set_attribute("profile.timezone", timezone_str)

        try:
            try:
                zoneinfo.ZoneInfo(timezone_str)
            except (zoneinfo.ZoneInfoNotFoundError, KeyError):
                raise GTDError(
                    "invalid_timezone",
                    f"Not a valid IANA timezone: {timezone_str!r}",
                    timezone=timezone_str,
                )

            now = datetime.now(timezone.utc).isoformat()
            existing = read_profile(user_id)

            if existing is None:
                profile: dict = {
                    "user_id":       user_id,
                    "name":          name,
                    "timezone":      timezone_str,
                    "registered_at": now,
                    "updated_at":    now,
                }
            else:
                profile = {
                    **existing,
                    "name":       name,
                    "timezone":   timezone_str,
                    "updated_at": now,
                }

            path = user_path(user_id) / _PROFILE_FILENAME
            try:
                _write_profile_atomic(path, profile)
            except OSError as exc:
                raise GTDError(
                    "storage_io_failed",
                    f"Failed to write profile: {exc}",
                    path=str(path),
                    error_type=type(exc).__name__,
                ) from exc

            return profile

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise
