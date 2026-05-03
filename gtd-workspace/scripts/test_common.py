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


def test_err_string_wraps_as_internal_error(capsys: pytest.CaptureFixture) -> None:
    from common import err
    with pytest.raises(SystemExit) as exc_info:
        err("something went wrong")
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["error"]["code"] == "internal_error"
    assert out["error"]["message"] == "something went wrong"


def test_err_gtd_error_emits_lock5_envelope(capsys: pytest.CaptureFixture) -> None:
    from common import GTDError, err
    with pytest.raises(SystemExit) as exc_info:
        err(GTDError("validation_failed", "Priority is invalid", record_type="task"))
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["error"]["code"] == "validation_failed"
    assert out["error"]["message"] == "Priority is invalid"
    assert out["error"]["record_type"] == "task"


def test_err_gtd_error_with_no_extra_fields(capsys: pytest.CaptureFixture) -> None:
    from common import GTDError, err
    with pytest.raises(SystemExit):
        err(GTDError("not_found", "Record not found"))
    out = json.loads(capsys.readouterr().out.strip())
    assert out["error"] == {"code": "not_found", "message": "Record not found"}


def test_gtd_error_fields_accessible(capsys: pytest.CaptureFixture) -> None:
    from common import GTDError
    exc = GTDError("isolation_violation", "User mismatch", record_user_id="alice")
    assert exc.code == "isolation_violation"
    assert exc.message == "User mismatch"
    assert exc.fields == {"record_user_id": "alice"}
    assert str(exc) == "User mismatch"


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
    token_path = tmp_path / "trina-google-creds.json"
    _write_token(token_path, {"type": "authorized_user"})
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

    mock_creds = _make_valid_creds()

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds):
        from common import get_google_credentials
        result = get_google_credentials(["https://www.googleapis.com/auth/calendar"])

    assert result is mock_creds


# Case 2: Missing env var — names the missing variable
# Guards against: "auth failed" error that doesn't identify which env var is absent.
def test_missing_credentials_env_var_names_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CREDENTIALS", raising=False)

    from common import get_google_credentials
    with pytest.raises(EnvironmentError, match="GOOGLE_OAUTH_CREDENTIALS"):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 3: Missing credentials file — names the path
# Guards against: raw FileNotFoundError traceback leaking to operator instead of structured error.
def test_missing_token_file_names_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "trina-google-creds.json"  # does not exist
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

    from common import get_google_credentials
    with pytest.raises(FileNotFoundError, match=str(token_path)):
        get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 4: Insufficient scopes — names the missing scopes
# Guards against: silent success with reduced scope causing confusing 403s downstream.
def test_insufficient_scopes_names_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "trina-google-creds.json"
    _write_token(token_path, {"type": "authorized_user"})
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

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
    token_path = tmp_path / "trina-google-creds.json"
    _write_token(token_path, {"type": "authorized_user"})
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

    mock_creds = _make_valid_creds(expired=True, refresh_token="rt")

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("google.auth.transport.requests.Request"):
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

    token_path = tmp_path / "trina-google-creds.json"
    _write_token(token_path, {"type": "authorized_user"})
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

    mock_creds = _make_valid_creds(expired=True, refresh_token="rt")
    mock_creds.refresh.side_effect = google.auth.exceptions.RefreshError("token expired")

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds), \
         patch("google.auth.transport.requests.Request"):
        from common import get_google_credentials
        with pytest.raises(RuntimeError, match=str(token_path)):
            get_google_credentials(["https://www.googleapis.com/auth/calendar"])


# Case 7: Malformed credentials JSON — names the file path
# Guards against: json.JSONDecodeError surfacing as unstructured traceback.
def test_malformed_token_json_names_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "trina-google-creds.json"
    token_path.write_text("{ not valid json }")
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

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


# ---------------------------------------------------------------------------
# get_gtd_config
# ---------------------------------------------------------------------------

def test_gtd_config_defaults() -> None:
    """GTDConfig() with no args has hard-coded defaults (10, 25)."""
    from common import GTDConfig
    cfg = GTDConfig()
    assert cfg.default_query_limit == 10
    assert cfg.max_query_limit == 25


def test_gtd_config_accepts_explicit_values() -> None:
    """GTDConfig fields can be overridden at construction."""
    from common import GTDConfig
    cfg = GTDConfig(default_query_limit=5, max_query_limit=20)
    assert cfg.default_query_limit == 5
    assert cfg.max_query_limit == 20


def test_gtd_config_partial_construction_fills_defaults() -> None:
    """Providing only one field leaves the other at its default."""
    from common import GTDConfig
    cfg = GTDConfig(default_query_limit=7)
    assert cfg.default_query_limit == 7
    assert cfg.max_query_limit == 25


def test_gtd_config_unknown_keys_filtered_before_construction() -> None:
    """The known-key filter used by get_gtd_config drops unknown fields silently."""
    from common import GTDConfig
    raw = {"default_query_limit": 10, "future_flag": True}
    known = {k: v for k, v in raw.items() if k in GTDConfig.model_fields}
    cfg = GTDConfig(**known)
    assert cfg.default_query_limit == 10
    assert not hasattr(cfg, "future_flag")


def test_get_gtd_config_returns_gtd_config_instance() -> None:
    """get_gtd_config() returns a GTDConfig instance (reads from workspace config/gtd.json)."""
    from common import GTDConfig, get_gtd_config
    cfg = get_gtd_config()
    assert isinstance(cfg, GTDConfig)
    assert cfg.default_query_limit > 0
    assert cfg.max_query_limit >= cfg.default_query_limit


# m-2: creds.scopes = None — token issued without explicit scope recording, accepted without error.
# Guards against: regression that rejects valid tokens from OAuth flows that don't record scopes.
def test_scopes_none_returns_creds_without_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "trina-google-creds.json"
    _write_token(token_path, {"type": "authorized_user"})
    monkeypatch.setenv("GOOGLE_OAUTH_CREDENTIALS", str(token_path))

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.refresh_token = None
    mock_creds.scopes = None

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds):
        from common import get_google_credentials
        result = get_google_credentials(["https://www.googleapis.com/auth/calendar"])

    assert result is mock_creds
