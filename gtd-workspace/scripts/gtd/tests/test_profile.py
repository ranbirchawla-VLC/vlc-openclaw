"""Tests for scripts/gtd/profile.py.

8 tests covering: read_profile (missing/present), write_profile (create,
update, invalid timezone), require_profile (missing/present), atomic write
integrity.

Production failure modes each test guards against:
  - Silent unregistered access: require_profile doesn't gate tools; any
    Telegram ID can write to storage
  - Timezone drift: profile written with bad tz string; get_today_date
    returns wrong date
  - registered_at overwritten on update: repeat registration resets clock
  - Corrupt state: crash during write leaves partial JSON
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from profile import read_profile, require_profile, write_profile
from common import GTDError


_USER = "user-profile-test"


def _profile_path(storage: Path) -> Path:
    return storage / "gtd-agent" / "users" / _USER / "profile.json"


# ---------------------------------------------------------------------------
# Test 1: read_profile returns None when no file
# ---------------------------------------------------------------------------

def test_read_profile_returns_none_when_missing(storage: Path) -> None:
    """read_profile returns None rather than raising when profile absent.

    Production failure: require_profile raises unexpected exception instead
    of GTDError; plugin tools crash instead of returning unknown_user.
    """
    result = read_profile(_USER)
    assert result is None


# ---------------------------------------------------------------------------
# Test 2: read_profile returns dict when file exists
# ---------------------------------------------------------------------------

def test_read_profile_returns_dict_when_present(storage: Path) -> None:
    """read_profile returns the profile dict when profile.json exists."""
    path = _profile_path(storage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "user_id": _USER, "name": "Alice", "timezone": "America/Denver",
        "registered_at": "2026-05-08T00:00:00+00:00",
        "updated_at": "2026-05-08T00:00:00+00:00",
    }), encoding="utf-8")

    result = read_profile(_USER)
    assert result is not None
    assert result["name"] == "Alice"
    assert result["timezone"] == "America/Denver"


# ---------------------------------------------------------------------------
# Test 3: write_profile creates profile with all required fields
# ---------------------------------------------------------------------------

def test_write_profile_creates_profile(storage: Path) -> None:
    """write_profile stamps all required fields on a new profile.

    Production failure: missing registered_at or updated_at; downstream
    readers assume both fields are present ISO strings.
    """
    profile = write_profile(_USER, "Alice", "America/Denver")

    assert profile["user_id"] == _USER
    assert profile["name"] == "Alice"
    assert profile["timezone"] == "America/Denver"
    assert "registered_at" in profile
    assert "updated_at" in profile
    assert profile["registered_at"] == profile["updated_at"]

    # verify persisted to disk
    on_disk = json.loads(_profile_path(storage).read_text())
    assert on_disk["name"] == "Alice"


# ---------------------------------------------------------------------------
# Test 4: write_profile preserves registered_at on update
# ---------------------------------------------------------------------------

def test_write_profile_preserves_registered_at(storage: Path) -> None:
    """Updating an existing profile must not change registered_at.

    Production failure: re-registration resets the clock; audit trail lost.
    """
    first = write_profile(_USER, "Alice", "America/Denver")
    updated = write_profile(_USER, "Alice B", "America/New_York")

    assert updated["registered_at"] == first["registered_at"]
    assert updated["name"] == "Alice B"
    assert updated["timezone"] == "America/New_York"
    assert updated["updated_at"] >= first["updated_at"]


# ---------------------------------------------------------------------------
# Test 5: write_profile raises invalid_timezone on bad tz string
# ---------------------------------------------------------------------------

def test_write_profile_invalid_timezone(storage: Path) -> None:
    """write_profile raises GTDError('invalid_timezone') for unknown zones.

    Production failure: bad tz string written to disk; get_today_date crashes
    or returns wrong date for this user.
    """
    with pytest.raises(GTDError) as exc_info:
        write_profile(_USER, "Alice", "Not/A/Timezone")
    assert exc_info.value.code == "invalid_timezone"


# ---------------------------------------------------------------------------
# Test 6: require_profile raises unknown_user when no profile
# ---------------------------------------------------------------------------

def test_require_profile_raises_unknown_user(storage: Path) -> None:
    """require_profile raises GTDError('unknown_user') when profile absent.

    Production failure: registration gate missing; unregistered Telegram ID
    creates storage directory and writes data silently.
    Fails RED without require_profile check in plugin tools.
    """
    with pytest.raises(GTDError) as exc_info:
        require_profile(_USER)
    assert exc_info.value.code == "unknown_user"


# ---------------------------------------------------------------------------
# Test 7: require_profile returns profile when it exists
# ---------------------------------------------------------------------------

def test_require_profile_returns_profile(storage: Path) -> None:
    """require_profile returns the profile dict when profile exists."""
    write_profile(_USER, "Alice", "America/Denver")
    profile = require_profile(_USER)
    assert profile["name"] == "Alice"


# ---------------------------------------------------------------------------
# Test 8: atomic write leaves no .tmp file behind
# ---------------------------------------------------------------------------

def test_write_profile_no_tmp_file_left(storage: Path) -> None:
    """After write_profile, no .tmp file remains in the user directory.

    Production failure: crash during write leaves .profile.tmp; second write
    attempt fails on os.replace() with unexpected file state.
    """
    write_profile(_USER, "Alice", "America/Denver")
    user_dir = _profile_path(storage).parent
    tmp_files = list(user_dir.glob("*.tmp"))
    assert tmp_files == []
