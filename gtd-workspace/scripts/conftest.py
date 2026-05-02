"""Pytest configuration for gtd-workspace/scripts tests."""

import os
import sys
from pathlib import Path

# Must be set before common.py is imported; DATA_ROOT = Path(_require_env("GTD_STORAGE_ROOT"))
# evaluates at module load time. setdefault leaves a real value alone if already set.
os.environ.setdefault("GTD_STORAGE_ROOT", "/tmp/gtd-test")

sys.path.insert(0, str(Path(__file__).parent))

import pytest


@pytest.fixture(autouse=True)
def reset_qwen_health_cache():
    """Reset module-level Qwen health cache between tests to prevent state bleed."""
    try:
        import otel_common
        otel_common._qwen_down_since = None
        yield
        otel_common._qwen_down_since = None
    except ImportError:
        yield


@pytest.fixture(autouse=True)
def set_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a fake Anthropic API key so _load_api_key() doesn't fail in tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
