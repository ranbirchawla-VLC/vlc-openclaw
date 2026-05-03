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
