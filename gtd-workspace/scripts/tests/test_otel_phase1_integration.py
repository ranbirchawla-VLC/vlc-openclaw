"""test_otel_phase1_integration.py -- Phase 1 cross-process OTEL propagation tests.

Tests 10-11: verify attach_parent_trace_context correctly propagates a TRACEPARENT
injected by the plugin-layer (Node.js) into the Python subprocess context.

Harness note: uses in-process approach (approach a from Phase 1 plan) rather than
full subprocess spawn, because InMemorySpanExporter is in-process only. The
core behavior under test (attach and detach of parent trace context) is equivalent
regardless of whether the Python code runs in-process or as a subprocess.

RED baseline: ImportError on attach_parent_trace_context before Phase 1 otel_common.py update.
Model/temperature: N/A; no LLM calls.
"""
from __future__ import annotations

import os
import sys

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cross_process_trace_id_propagated(monkeypatch):
    """Python span trace_id matches the trace_id in the injected TRACEPARENT.

    Reproduces: plugin-layer Node parent sets TRACEPARENT in subprocess env;
    Python script must attach that context before creating its top-level span,
    so the span inherits the same trace_id and is not an orphan root in Honeycomb.

    Failed against unfixed code: ImportError (attach_parent_trace_context absent).
    Model/temperature: N/A.
    """
    from otel_common import attach_parent_trace_context, configure_tracer_provider, get_tracer

    known_trace_id = "abcdef1234567890abcdef1234567890"
    known_parent_id = "1234567890abcdef"
    traceparent = f"00-{known_trace_id}-{known_parent_id}-01"
    monkeypatch.setenv("TRACEPARENT", traceparent)

    exporter = InMemorySpanExporter()
    configure_tracer_provider(exporter)
    tracer = get_tracer("integration.test")

    with attach_parent_trace_context():
        with tracer.start_as_current_span("gtd.capture") as span:
            pass

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1, "at least one span must be emitted"
    child = spans[-1]
    trace_id_hex = format(child.get_span_context().trace_id, "032x")
    assert trace_id_hex == known_trace_id, (
        f"child trace_id {trace_id_hex!r} must equal injected TRACEPARENT trace_id {known_trace_id!r}; "
        "span would be an orphan root in Honeycomb without this"
    )


def test_python_span_parent_id_matches_injected_parent(monkeypatch):
    """Python span parent_span_id matches the parent_id in the injected TRACEPARENT.

    Failed against unfixed code: ImportError (attach_parent_trace_context absent).
    Model/temperature: N/A.
    """
    from otel_common import attach_parent_trace_context, configure_tracer_provider, get_tracer

    known_trace_id = "abcdef1234567890abcdef1234567890"
    known_parent_id = "1234567890abcdef"
    traceparent = f"00-{known_trace_id}-{known_parent_id}-01"
    monkeypatch.setenv("TRACEPARENT", traceparent)

    exporter = InMemorySpanExporter()
    configure_tracer_provider(exporter)
    tracer = get_tracer("integration.test.parent")

    with attach_parent_trace_context():
        with tracer.start_as_current_span("gtd.capture") as span:
            pass

    spans = exporter.get_finished_spans()
    child = spans[-1]
    assert child.parent is not None, "span must have a parent span context"
    parent_id_hex = format(child.parent.span_id, "016x")
    assert parent_id_hex == known_parent_id, (
        f"child parent_span_id {parent_id_hex!r} must equal injected parent_id {known_parent_id!r}"
    )
