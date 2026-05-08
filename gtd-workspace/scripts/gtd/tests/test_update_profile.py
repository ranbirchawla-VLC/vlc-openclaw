"""Tests for scripts/gtd/update_profile.py.

12 tests covering: read-only mode (present/absent), create new profile,
missing_required_field (name/timezone), update timezone only, update name
only, invalid_timezone, storage_io_failed, OTEL span attrs, OTEL error
status, main() CLI round-trip.

Production failure modes each test guards against:
  - Silent read-only on new user: unknown_user not returned; LLM assumes
    user is registered; onboard flow never triggered
  - Partial update clobbers fields: updating timezone overwrites name with None
  - Invalid timezone accepted: bad IANA string written to disk
  - Error path missing span: Honeycomb shows successful span for failure
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from update_profile import update_profile, main
from profile import write_profile as _seed_profile
from common import GTDError
import otel_common as _oc


_USER = "user-update-test"


def _profile_path(storage: Path) -> Path:
    return storage / "gtd-agent" / "users" / _USER / "profile.json"


def _seed(storage: Path, name: str = "Alice", tz: str = "America/Denver") -> dict:
    return _seed_profile(_USER, name, tz)


# ---------------------------------------------------------------------------
# Test 1: read-only returns existing profile
# ---------------------------------------------------------------------------

def test_update_profile_readonly_returns_existing(storage: Path) -> None:
    """Called with user_id only, returns current profile when it exists.

    Production failure: read-only returns error instead of profile; onboard
    capability can't distinguish new vs returning user.
    """
    _seed(storage)
    result = update_profile(_USER)
    assert "profile" in result
    assert result["profile"]["name"] == "Alice"


# ---------------------------------------------------------------------------
# Test 2: read-only raises unknown_user when no profile
# ---------------------------------------------------------------------------

def test_update_profile_readonly_unknown_user(storage: Path) -> None:
    """Called with user_id only, raises unknown_user when no profile exists."""
    with pytest.raises(GTDError) as exc_info:
        update_profile(_USER)
    assert exc_info.value.code == "unknown_user"


# ---------------------------------------------------------------------------
# Test 3: create new profile with all fields
# ---------------------------------------------------------------------------

def test_update_profile_creates_new_profile(storage: Path) -> None:
    """Creates profile with all required fields when none exists.

    Production failure: fields missing from new profile; downstream reads
    KeyError on name or timezone.
    """
    result = update_profile(_USER, name="Bob", timezone="America/Chicago")
    profile = result["profile"]

    assert profile["user_id"] == _USER
    assert profile["name"] == "Bob"
    assert profile["timezone"] == "America/Chicago"
    assert "registered_at" in profile
    assert "updated_at" in profile

    on_disk = json.loads(_profile_path(storage).read_text())
    assert on_disk["name"] == "Bob"


# ---------------------------------------------------------------------------
# Test 4: missing_required_field — name absent for new user
# ---------------------------------------------------------------------------

def test_update_profile_missing_name_for_new_user(storage: Path) -> None:
    """Raises missing_required_field when timezone given but name absent for new user."""
    with pytest.raises(GTDError) as exc_info:
        update_profile(_USER, timezone="America/Denver")
    assert exc_info.value.code == "missing_required_field"
    assert exc_info.value.fields.get("field") == "name"


# ---------------------------------------------------------------------------
# Test 5: missing_required_field — timezone absent for new user
# ---------------------------------------------------------------------------

def test_update_profile_missing_timezone_for_new_user(storage: Path) -> None:
    """Raises missing_required_field when name given but timezone absent for new user."""
    with pytest.raises(GTDError) as exc_info:
        update_profile(_USER, name="Bob")
    assert exc_info.value.code == "missing_required_field"
    assert exc_info.value.fields.get("field") == "timezone"


# ---------------------------------------------------------------------------
# Test 6: update timezone only — name preserved
# ---------------------------------------------------------------------------

def test_update_profile_timezone_only(storage: Path) -> None:
    """Updating timezone only must preserve existing name.

    Production failure: partial update sets name=None; profile corrupted.
    """
    _seed(storage, name="Alice", tz="America/Denver")
    result = update_profile(_USER, timezone="America/New_York")
    assert result["profile"]["name"] == "Alice"
    assert result["profile"]["timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# Test 7: update name only — timezone preserved
# ---------------------------------------------------------------------------

def test_update_profile_name_only(storage: Path) -> None:
    """Updating name only must preserve existing timezone."""
    _seed(storage, name="Alice", tz="America/Denver")
    result = update_profile(_USER, name="Alice B")
    assert result["profile"]["name"] == "Alice B"
    assert result["profile"]["timezone"] == "America/Denver"


# ---------------------------------------------------------------------------
# Test 8: invalid_timezone
# ---------------------------------------------------------------------------

def test_update_profile_invalid_timezone(storage: Path) -> None:
    """Raises invalid_timezone when IANA string is not valid."""
    with pytest.raises(GTDError) as exc_info:
        update_profile(_USER, name="Bob", timezone="Fake/Zone")
    assert exc_info.value.code == "invalid_timezone"


# ---------------------------------------------------------------------------
# Test 9: storage_io_failed
# ---------------------------------------------------------------------------

def test_update_profile_storage_io_failed(storage: Path) -> None:
    """Raises storage_io_failed on OSError during write."""
    with patch("profile._write_profile_atomic", side_effect=OSError("disk full")):
        with pytest.raises(GTDError) as exc_info:
            update_profile(_USER, name="Bob", timezone="America/Denver")
    assert exc_info.value.code == "storage_io_failed"


# ---------------------------------------------------------------------------
# Test 10: OTEL span attributes
# ---------------------------------------------------------------------------

def test_update_profile_span_attributes(storage: Path) -> None:
    """Span 'gtd.update_profile' emits tool.name and mode attribute."""
    exporter = InMemorySpanExporter()
    _oc.configure_tracer_provider(exporter)

    _seed(storage)
    update_profile(_USER)

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.update_profile")
    attrs = dict(span.attributes)
    assert attrs["tool.name"] == "update_profile"
    assert attrs["update_profile.mode"] == "read"


# ---------------------------------------------------------------------------
# Test 11: OTEL error status on unknown_user
# ---------------------------------------------------------------------------

def test_update_profile_span_error_status(storage: Path) -> None:
    """Span status is ERROR and exception recorded on unknown_user.

    Production failure: Honeycomb shows successful span for a failed read;
    silent onboarding failures invisible in traces.
    """
    exporter = InMemorySpanExporter()
    _oc.configure_tracer_provider(exporter)

    with pytest.raises(GTDError):
        update_profile(_USER)

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "gtd.update_profile")
    assert span.status.status_code == StatusCode.ERROR
    assert len(span.events) > 0


# ---------------------------------------------------------------------------
# Test 12: main() CLI round-trip
# ---------------------------------------------------------------------------

def test_update_profile_main_cli_round_trip(storage: Path, capsys) -> None:
    """main() reads argv JSON and writes ok envelope to stdout.

    Production failure: main() missing ok() call; plugin sees empty stdout
    and maps to subprocess_nonzero_exit error.
    """
    args = json.dumps({"user_id": _USER, "name": "Bob", "timezone": "America/Denver"})

    with patch.object(sys, "argv", ["update_profile.py", args]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0

    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["data"]["profile"]["name"] == "Bob"
    assert output["data"]["profile"]["timezone"] == "America/Denver"
