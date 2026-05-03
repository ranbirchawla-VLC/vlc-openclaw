"""Shared helpers for GTD plugin scripts.

Constants, ok/err output helpers, and Google OAuth credential loader.
Separate from tools/common.py (JSONL/enum layer for legacy pipeline tools).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.credentials


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(f"Required environment variable not set: {name}")
    return val


DATA_ROOT: Path = Path(_require_env("GTD_STORAGE_ROOT"))
TZ: str = os.environ.get("GTD_TZ", "America/Denver")


# ---------------------------------------------------------------------------
# Structured error (Lock 5 envelope)
# ---------------------------------------------------------------------------

class GTDError(Exception):
    """Structured error for the Lock 5 envelope.

    Raised by internal modules; caught by plugin entry points and translated
    to err() output.
    """
    def __init__(self, code: str, message: str, **fields) -> None:
        self.code = code
        self.message = message
        self.fields = fields
        super().__init__(message)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def ok(data: dict) -> None:
    """Print {"ok": true, "data": data} and exit 0."""
    print(json.dumps({"ok": True, "data": data}))
    sys.exit(0)


def err(error: str | GTDError) -> None:
    """Print Lock 5 error envelope and exit 1.

    str: wraps as {code: "internal_error", message: str}.
    GTDError: emits {code, message, **fields}.
    """
    if isinstance(error, str):
        payload: dict = {"code": "internal_error", "message": error}
    else:
        payload = {"code": error.code, "message": error.message, **error.fields}
    print(json.dumps({"ok": False, "error": payload}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Google OAuth credential loader
# ---------------------------------------------------------------------------

def get_google_credentials(scopes: list[str]) -> google.oauth2.credentials.Credentials:
    """Load and return Google OAuth credentials from the paths in env vars.

    Validates that all requested scopes are present and refreshes if expired.
    Raises structured errors naming the specific resource that is missing or
    misconfigured — not generic "auth failed" messages.
    """
    token_path_str = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
    if not token_path_str:
        raise EnvironmentError("Required environment variable not set: GOOGLE_OAUTH_CREDENTIALS")

    token_path = Path(token_path_str)
    if not token_path.exists():
        raise FileNotFoundError(f"Google OAuth token file not found: {token_path}")

    try:
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(token_path)
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Malformed Google OAuth token file: {token_path}") from exc

    # scopes is None when the token was issued without explicit scope recording (common in
    # some OAuth flows); treat as trusted and skip the missing-scope check.
    if creds.scopes is not None:
        missing = [s for s in scopes if s not in creds.scopes]
        if missing:
            raise PermissionError(
                f"Token at {token_path} is missing required scopes: {missing}. "
                "Re-run the OAuth flow with the full scope set."
            )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
        except google.auth.exceptions.RefreshError as exc:
            raise RuntimeError(
                f"Failed to refresh Google OAuth token at {token_path}. "
                "Delete the file and re-run the OAuth flow to re-authenticate."
            ) from exc

    return creds
