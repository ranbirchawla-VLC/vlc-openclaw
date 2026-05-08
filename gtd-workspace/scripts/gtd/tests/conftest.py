"""Pytest configuration for scripts/gtd/tests/.

Adds scripts/, scripts/gtd/, and tools/ to sys.path.
Parent scripts/conftest.py handles: GTD_STORAGE_ROOT default, isolate_tracer_provider,
reset_qwen_health_cache, set_anthropic_api_key.
"""

import sys
from pathlib import Path

_here = Path(__file__).parent
_gtd = str(_here.parent)                          # scripts/gtd/
_scripts = str(_here.parent.parent)               # scripts/
_tools = str(_here.parent.parent.parent / "tools")  # tools/

for _p in [_tools, _gtd, _scripts]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest


@pytest.fixture(autouse=True)
def set_openclaw_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a default OPENCLAW_USER_ID for plugin entry-point tests that read from env."""
    monkeypatch.setenv("OPENCLAW_USER_ID", "test-user-1")


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect GTD_STORAGE_ROOT to a tmp directory for write-path isolation."""
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def seed_profile(storage: Path, request) -> None:
    """Write profile.json for all known test user IDs when the storage fixture is active.

    Required after the require_profile registration gate was added: all plugin
    tool tests use storage-isolated paths; without a seeded profile every tool
    call would return unknown_user instead of exercising the tool's own logic.

    Tests that intentionally test the unknown_user path must delete the profile
    file for their specific user_id in the test body before calling the tool.
    """
    import json as _json

    _TEST_USERS = [
        ("test-user-1", "Test User"),
        ("user1",       "User One"),
        ("user2",       "User Two"),
    ]
    for uid, name in _TEST_USERS:
        profile_dir = storage / "gtd-agent" / "users" / uid
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "profile.json").write_text(
            _json.dumps({
                "user_id":       uid,
                "name":          name,
                "timezone":      "America/Denver",
                "registered_at": "2026-05-08T00:00:00+00:00",
                "updated_at":    "2026-05-08T00:00:00+00:00",
            }),
            encoding="utf-8",
        )
