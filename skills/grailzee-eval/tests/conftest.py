"""Shared pytest fixtures for Grailzee Eval v2 tests."""

import json
import pytest


@pytest.fixture(scope="session")
def _otel_session_exporter():
    """Install InMemorySpanExporter as the global OTel TracerProvider once per
    session. The SDK only allows set_tracer_provider to be called once; a
    session-scoped fixture satisfies that constraint.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry import trace

    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    trace.set_tracer_provider(provider)
    return exp


@pytest.fixture
def span_exporter(_otel_session_exporter):
    """Function-scoped exporter view: clears accumulated spans before each
    test and after, so each test sees only the spans it produced.
    """
    _otel_session_exporter.clear()
    yield _otel_session_exporter
    _otel_session_exporter.clear()


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary state directory with standard subfolders."""
    state = tmp_path / "state"
    state.mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports_csv").mkdir()
    (tmp_path / "output" / "briefs").mkdir(parents=True)
    (tmp_path / "backup").mkdir()
    return state


@pytest.fixture
def empty_name_cache(tmp_state_dir):
    """Path to an empty (nonexistent) name_cache.json in a temp dir."""
    return tmp_state_dir / "name_cache.json"


@pytest.fixture
def seeded_name_cache(tmp_state_dir):
    """name_cache.json pre-seeded with a few known references."""
    cache_path = tmp_state_dir / "name_cache.json"
    seed = {
        "79830RB": {
            "brand": "Tudor",
            "model": "BB GMT Pepsi",
            "alt_refs": ["M79830RB", "M79830RB-0001"],
        },
        "210.30.42.20.03.001": {
            "brand": "Omega",
            "model": "SMD 300M Blue",
        },
    }
    cache_path.write_text(json.dumps(seed, indent=2))
    return cache_path
