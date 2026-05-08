"""update_profile.py -- LLM-visible plugin entry point for profile management.

Dual mode:
  - Called with {user_id} only → read-only; returns current profile or unknown_user
  - Called with {user_id, name, timezone} → create or update profile

The LLM resolves city names to IANA timezone strings before calling this tool.
Returns {ok: true, data: {profile: {user_id, name, timezone, registered_at, updated_at}}}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
sys.path.insert(0, str(_here))          # scripts/gtd/
sys.path.insert(0, str(_here.parent))   # scripts/

from pydantic import BaseModel

from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, get_tracer
from opentelemetry.trace import Status, StatusCode
from profile import read_profile, write_profile


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    user_id:  str
    name:     str | None = None
    timezone: str | None = None


# ---------------------------------------------------------------------------
# OTEL context attributes
# ---------------------------------------------------------------------------

_CONTEXT_ENV: dict[str, str] = {
    "user.id":         "OPENCLAW_USER_ID",
    "session.id":      "OPENCLAW_SESSION_ID",
    "channel.type":    "OPENCLAW_CHANNEL_TYPE",
    "channel.peer_id": "OPENCLAW_CHANNEL_PEER_ID",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_profile(
    user_id: str,
    name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """Read or create/update a user profile.

    Read mode (name and timezone both None):
      Returns {"profile": <current>} or raises GTDError("unknown_user").

    Write mode (name and/or timezone provided):
      Creates profile if none exists (requires both name and timezone).
      Updates existing profile with whichever fields are provided.
      Returns {"profile": <updated>}.

    Raises GTDError with codes:
      unknown_user          -- read mode, no profile exists
      missing_required_field -- write mode, new user, name or timezone absent
      invalid_timezone      -- timezone string not a valid IANA zone
      storage_io_failed     -- OSError on write
    """
    tracer = get_tracer("gtd.update_profile")
    with tracer.start_as_current_span("gtd.update_profile") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("tool.name", "update_profile")
        span.set_attribute("update_profile.mode", "read" if (name is None and timezone is None) else "write")
        for attr, env_var in _CONTEXT_ENV.items():
            val = os.environ.get(env_var)
            if val:
                span.set_attribute(attr, val)

        try:
            if not user_id:
                raise GTDError("internal_error", "user_id is empty")

            read_only = name is None and timezone is None

            if read_only:
                profile = read_profile(user_id)
                if profile is None:
                    raise GTDError(
                        "unknown_user",
                        f"No profile found for user {user_id!r}. Say hello to Trina to get set up.",
                        user_id=user_id,
                    )
                return {"profile": profile}

            # Write mode — resolve fields against existing profile
            existing = read_profile(user_id)
            is_new = existing is None

            if is_new:
                if name is None:
                    raise GTDError(
                        "missing_required_field",
                        "name is required when creating a new profile",
                        field="name",
                    )
                if timezone is None:
                    raise GTDError(
                        "missing_required_field",
                        "timezone is required when creating a new profile",
                        field="timezone",
                    )
                effective_name = name
                effective_timezone = timezone
            else:
                effective_name     = name     if name     is not None else existing["name"]
                effective_timezone = timezone if timezone is not None else existing["timezone"]

            profile = write_profile(user_id, effective_name, effective_timezone)
            span.set_attribute("update_profile.is_new", is_new)
            return {"profile": profile}

        except GTDError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, exc.message))
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        err(GTDError("internal_error", "Usage: python update_profile.py <args.json>"))
        return
    try:
        args = json.loads(sys.argv[1])
        inp = _Input(**args)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        err(GTDError("internal_error", f"Invalid input: {exc}"))
        return

    with attach_parent_trace_context():
        try:
            result = update_profile(inp.user_id, inp.name, inp.timezone)
            ok(result)
        except GTDError as exc:
            err(exc)


if __name__ == "__main__":
    main()
