"""Shared fixtures for GTD LLM tests.

Provides:
- API key resolution (ANTHROPIC_API_KEY env > ~/.openclaw/openclaw.json > skip)
- GTD_CAPABILITIES_DIR set to stub fixtures directory
- isolate_tracer_provider: prevents test spans reaching real OTLP collector
- tools schema loader for tool surface verification
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2])
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_FIXTURES_CAPS = str(Path(__file__).parent / "fixtures" / "capabilities")
_TOOLS_SCHEMA = Path(__file__).resolve().parents[4] / "plugins" / "gtd-tools" / "tools.schema.json"


def _resolve_api_key() -> str | None:
    """Resolve real API key: env first, then ~/.openclaw/openclaw.json."""
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            return config["models"]["providers"]["mnemo"]["apiKey"]
        except (KeyError, json.JSONDecodeError):
            pass
    return None


# Captured at module load time (before any test fixtures run) so that the parent
# conftest's fake-key monkeypatch cannot shadow the real key at fixture execution time.
_REAL_API_KEY: str | None = _resolve_api_key()


def pytest_collection_modifyitems(config, items):
    if not _REAL_API_KEY:
        skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set and not found in ~/.openclaw/openclaw.json")
        for item in items:
            if item.get_closest_marker("llm"):
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def set_capabilities_dir(monkeypatch):
    """Point all LLM tests at stub capability files and restore the real API key.

    Uses _REAL_API_KEY (captured at module load time before any fixture runs) to
    override the fake key injected by the parent conftest autouse fixture.
    """
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", _FIXTURES_CAPS)
    if _REAL_API_KEY:
        monkeypatch.setenv("ANTHROPIC_API_KEY", _REAL_API_KEY)


@pytest.fixture(autouse=True)
def isolate_tracer_provider():
    """Swap tracer provider to in-memory to prevent test spans reaching OTLP."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import turn_state as ts
    ts.configure_tracer_provider(InMemorySpanExporter())
    yield


@pytest.fixture(scope="session")
def tools_schema() -> dict:
    """Load the committed tools.schema.json for surface verification."""
    return json.loads(_TOOLS_SCHEMA.read_text())
