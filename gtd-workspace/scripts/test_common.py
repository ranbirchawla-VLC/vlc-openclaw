"""Tests for scripts/common.py — Google OAuth credential loader.

Each test guards a specific production failure mode; see inline comments.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ok() / err()
# ---------------------------------------------------------------------------

def test_ok_prints_json_and_exits_0(capsys: pytest.CaptureFixture) -> None:
    from common import ok
    with pytest.raises(SystemExit) as exc_info:
        ok({"key": "value"})
    assert exc_info.value.code == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"ok": True, "data": {"key": "value"}}


def test_err_prints_json_and_exits_1(capsys: pytest.CaptureFixture) -> None:
    from common import err
    with pytest.raises(SystemExit) as exc_info:
        err("something went wrong")
    assert exc_info.value.code == 1
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"ok": False, "error": "something went wrong"}


# ---------------------------------------------------------------------------
# get_google_credentials
# ---------------------------------------------------------------------------

def _write_token(path: Path, content: object) -> None:
    """Write a token.json file; content can be a dict or raw string."""
    if isinstance(content, dict):
        path.write_text(json.dumps(content))
    else:
        path.write_text(content)


def _make_valid_creds(
    expired: bool = False,
    refresh_token: str | None = "rt",
    scopes: set[str] | None = None,
) -> MagicMock:
    creds = MagicMock()
    creds.expired = expired
    creds.refresh_token = refresh_token
    creds.scopes = scopes if scopes is not None else {
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/gmail.send",
    }
    return creds


# Case 1: Happy path — returns Credentials
# Guards against: unhandled AttributeError at caller if function returns wrong type.
def test_happy_path_returns_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    _write_token(token_path, {"type": "authorized_user"})
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    mock_creds = _make_valid_creds()

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds):
        from common import get_google_credentials
        result = get_google_credentials(["https://www.googleapis.com/auth/calendar"])

    assert result is mock_creds


# Case 2: Missing env var — names the missing variable
# Guards against: "auth failed" error that doesn't identify which of the two env vars is absent.
def test_missing_token_path_env_var_names_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", raising=False)

    from common import get_google_credentials
    with pytest.raises(EnvironmentError, match="GOOGLE_OAUTH_TOKEN_PATH"):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


def test_missing_secrets_path_env_var_names_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", raising=False)

    from common import get_google_credentials
    with pytest.raises(EnvironmentError, match="GOOGLE_OAUTH_CLIENT_SECRETS_PATH"):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 3: Missing token file — names the path
# Guards against: raw FileNotFoundError traceback leaking to operator instead of structured error.
def test_missing_token_file_names_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"  # does not exist
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    from common import get_google_credentials
    with pytest.raises(FileNotFoundError, match=str(token_path)):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 4: Insufficient scopes — names the missing scopes
# Guards against: silent success with reduced scope causing confusing 403s downstream.
def test_insufficient_scopes_names_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    _write_token(token_path, {"type": "authorized_user"})
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    mock_creds = _make_valid_creds(scopes={"https://www.googleapis.com/auth/calendar"})

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds):
        from common import get_google_credentials
        with pytest.raises(PermissionError, match="gmail.send"):
            get_google_credentials([
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/gmail.send",
            ])


# Case 5: Expired token with refresh token — refresh() is called, returns refreshed creds
# Guards against: unrefreshed expired token causing every Google API call to fail with 401.
def test_expired_token_calls_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    _write_token(token_path, {"type": "authorized_user"})
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    mock_creds = _make_valid_creds(expired=True, refresh_token="rt")

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("google.auth.transport.requests.Request") as mock_request_cls:
        from common import get_google_credentials
        result = get_google_credentials(["https://www.googleapis.com/auth/calendar"])

    mock_creds.refresh.assert_called_once()
    assert result is mock_creds


# Case 6: Expired token, refresh fails — names the file path needing re-auth
# Guards against: generic "refresh failed" leaving operator hunting which credential file to replace.
def test_refresh_failure_names_token_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import google.auth.exceptions

    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    _write_token(token_path, {"type": "authorized_user"})
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    mock_creds = _make_valid_creds(expired=True, refresh_token="rt")
    mock_creds.refresh.side_effect = google.auth.exceptions.RefreshError("token expired")

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("google.auth.transport.requests.Request"):
        from common import get_google_credentials
        with pytest.raises(RuntimeError, match=str(token_path)):
            get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 7: Malformed token JSON — names the file path
# Guards against: json.JSONDecodeError surfacing as unstructured traceback.
def test_malformed_token_json_names_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    token_path.write_text("{ not valid json }")
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    from common import get_google_credentials
    with pytest.raises(ValueError, match=str(token_path)):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# M-2: GTD_STORAGE_ROOT is required — _require_env raises clearly when unset.
# Guards against: misconfigured deploy silently writing to /tmp/gtd-missing.
# The import-time evaluation of DATA_ROOT = Path(_require_env("GTD_STORAGE_ROOT"))
# means a missing env var fails loudly at collection time, not silently at runtime.
def test_require_env_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GTD_STORAGE_ROOT", raising=False)
    from common import _require_env
    with pytest.raises(EnvironmentError, match="GTD_STORAGE_ROOT"):
        _require_env("GTD_STORAGE_ROOT")


def test_require_env_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", "/some/agent/path")
    from common import _require_env
    assert _require_env("GTD_STORAGE_ROOT") == "/some/agent/path"


# m-2: creds.scopes = None — token issued without explicit scope recording, accepted without error.
# Guards against: regression that rejects valid tokens from OAuth flows that don't record scopes.
def test_scopes_none_returns_creds_without_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.json"
    secrets_path = tmp_path / "secrets.json"
    _write_token(token_path, {"type": "authorized_user"})
    secrets_path.write_text("{}")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_PATH", str(secrets_path))

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.refresh_token = None
    mock_creds.scopes = None

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds):
        from common import get_google_credentials
        result = get_google_credentials(["https://www.googleapis.com/auth/calendar"])

    assert result is mock_creds
