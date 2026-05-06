"""Tests for gtd-workspace/scripts/turn_state.py.

19 tests covering: signal (deterministic) paths per intent, decision-6 edge
cases, LLM fallback mocking, retry exhaustion for both error codes,
capability-file error codes, span attribute shape and types, PII discipline,
continuity-turn detection, and stdin parsing.

Production failure modes each test guards against:
  - Wrong dispatch: correct intent not reached due to missing signal pattern
  - Silent LLM drift: retry loop absent, broken LLM silently swallowed
  - Span gaps: required attribute missing or wrong type in Honeycomb trace
  - PII leak: user message text in span attributes
  - File error silent: missing capability file not surfaced as error code
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

SCRIPTS_DIR = str(Path(__file__).resolve().parents[1])
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _make_exporter():
    """Return (exporter, exporter) -- configure_tracer_provider takes a SpanExporter."""
    exporter = InMemorySpanExporter()
    return exporter




# ---------------------------------------------------------------------------
# Tests 1-6: deterministic signal path per intent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected_intent", [
    ("remind me to call the dentist", "capture"),
    ("what are my tasks", "query_tasks"),
    ("any ideas on the list", "query_ideas"),
    ("parking lot please", "query_parking_lot"),
    ("let's run my weekly review", "review"),
    ("what's on my calendar today", "calendar_read"),
])
def test_deterministic_signal_per_intent(message, expected_intent, tmp_path, monkeypatch):
    """Tests 1-6: each intent's signal pattern catches the canonical trigger message.

    Production failure: wrong dispatch when signal pattern is absent or too broad.
    Fails RED without signal patterns in _classify_deterministic().
    Model/temperature: N/A -- Python-only, no LLM call.
    """
    cap_file = tmp_path / f"{expected_intent}.md"
    cap_file.write_text(f"# stub: {expected_intent}")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts
    result = ts.compute_turn_state(message)
    assert result["intent"] == expected_intent
    assert result["capability_prompt"] == f"# stub: {expected_intent}"


# ---------------------------------------------------------------------------
# Tests 7-8: decision-6 edge cases
# ---------------------------------------------------------------------------

def test_decision6_plate_routes_query_tasks(tmp_path, monkeypatch):
    """Test 7: 'what's on my plate today' -> query_tasks (commitment-biased reading).

    Production failure: ambiguous phrasing escapes deterministic layer and
    routes to unknown, missing a high-intent query signal.
    Fails RED without the plate/on-my-plate pattern in query_tasks signals.
    Model/temperature: N/A.
    """
    (tmp_path / "query_tasks.md").write_text("# stub: query_tasks")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts
    result = ts.compute_turn_state("what's on my plate today")
    assert result["intent"] == "query_tasks"


def test_decision6_park_in_ideas_routes_capture(tmp_path, monkeypatch):
    """Test 8: 'park this in ideas: call dentist' -> capture (verb wins over target).

    Production failure: 'idea' keyword triggers query_ideas instead of capture,
    dropping the item instead of recording it.
    Fails RED without verb-wins-over-target ordering in signal patterns.
    Model/temperature: N/A.
    """
    (tmp_path / "capture.md").write_text("# stub: capture")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts
    result = ts.compute_turn_state("park this in ideas: call dentist")
    assert result["intent"] == "capture"


# ---------------------------------------------------------------------------
# Test 9: LLM fallback called on signal miss
# ---------------------------------------------------------------------------

def test_llm_fallback_called_on_signal_miss(tmp_path, monkeypatch):
    """Test 9: ambiguous message -> LLM mock called; intent committed; strategy='llm'.

    Production failure: LLM fallback absent, ambiguous messages routed to unknown
    silently without attempting classification.
    Fails RED without _classify_llm() call in compute_turn_state.
    Model/temperature: mocked; not a live LLM call.
    """
    (tmp_path / "query_tasks.md").write_text("# stub: query_tasks")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps({"intent": "query_tasks"}))]
    mock_client.messages.create.return_value = mock_msg

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client):
        result = ts.compute_turn_state("hmm")

    assert result["intent"] == "query_tasks"
    assert mock_client.messages.create.called


# ---------------------------------------------------------------------------
# Test 10: classifier_invalid_response on parse failure exhaustion
# ---------------------------------------------------------------------------

def test_classifier_invalid_response_immediate_on_parse_failure(tmp_path, monkeypatch):
    """Test 10: non-JSON LLM response -> classifier_invalid_response raised immediately; no retry.

    Production failure: bad LLM response swallowed silently; no error surfaced;
    agent responds with no capability context.
    Fails RED if retry loop retries on parse failures (temp=0 makes them deterministic).
    Model/temperature: mocked.
    """
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json at all")]
    mock_client.messages.create.return_value = mock_msg

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client), \
         patch("turn_state.time.sleep") as mock_sleep, \
         pytest.raises(SystemExit) as exc_info:
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            ts.compute_turn_state("hmm")

    assert exc_info.value.code == 1
    assert mock_client.messages.create.call_count == 1  # immediate raise; no retries
    assert mock_sleep.call_count == 0
    output = json.loads(captured.getvalue())
    assert output["ok"] is False
    assert output["error"]["code"] == "classifier_invalid_response"


# ---------------------------------------------------------------------------
# Test 11: classifier_call_failed on SDK exception exhaustion
# ---------------------------------------------------------------------------

def test_classifier_call_failed_on_sdk_exception(tmp_path, monkeypatch):
    """Test 11: ConnectionError on all 4 attempts -> classifier_call_failed.

    Production failure: network failure swallowed; agent hangs or responds
    without capability context; no span ERROR emitted.
    Fails RED without exception catch in retry loop.
    Model/temperature: mocked.
    """
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("network down")

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client), \
         patch("turn_state.time.sleep"), \
         pytest.raises(SystemExit) as exc_info:
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            ts.compute_turn_state("hmm")

    assert exc_info.value.code == 1
    assert mock_client.messages.create.call_count == 4
    output = json.loads(captured.getvalue())
    assert output["ok"] is False
    assert output["error"]["code"] == "classifier_call_failed"


# ---------------------------------------------------------------------------
# Test 12: capability_file_missing
# ---------------------------------------------------------------------------

def test_capability_file_missing(tmp_path, monkeypatch):
    """Test 12: signal hits capture but capabilities/capture.md absent.

    Production failure: dispatcher routes correctly but silently returns empty
    capability_prompt; capability never reached; agent behaves as if unset.
    Fails RED without path.exists() check in _read_capability().
    Model/temperature: N/A.
    """
    # No capture.md created in tmp_path
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    with pytest.raises(SystemExit) as exc_info:
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            ts.compute_turn_state("remind me to call the dentist")

    assert exc_info.value.code == 1
    output = json.loads(captured.getvalue())
    assert output["ok"] is False
    assert output["error"]["code"] == "capability_file_missing"


# ---------------------------------------------------------------------------
# Test 13: capability_file_unreadable
# ---------------------------------------------------------------------------

def test_capability_file_unreadable(tmp_path, monkeypatch):
    """Test 13: capability file exists but open() raises OSError.

    Production failure: file permission error or concurrent write silently
    swallowed; agent proceeds with empty capability_prompt.
    Fails RED without OSError catch in _read_capability().
    Model/temperature: N/A.
    """
    cap_file = tmp_path / "capture.md"
    cap_file.write_text("# stub: capture")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    with patch("builtins.open", side_effect=OSError("permission denied")), \
         pytest.raises(SystemExit) as exc_info:
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            ts.compute_turn_state("remind me to call the dentist")

    assert exc_info.value.code == 1
    output = json.loads(captured.getvalue())
    assert output["ok"] is False
    assert output["error"]["code"] == "capability_file_unreadable"


# ---------------------------------------------------------------------------
# Test 14: success path emits all 7 span attributes with correct types
# ---------------------------------------------------------------------------

def test_success_span_attributes(tmp_path, monkeypatch):
    """Test 14: success path emits all 7 required span attributes.

    Production failure: Honeycomb query for span attribute returns no results
    because attribute was never set; hotload and determinism unverifiable.
    Fails RED without span.set_attribute() calls in compute_turn_state().
    Model/temperature: N/A.
    """
    (tmp_path / "capture.md").write_text("# stub: capture")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    ts.compute_turn_state("remind me to call the dentist")

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    attrs = dict(ts_span.attributes)

    assert attrs["intent"] == "capture"
    assert attrs["capability_dispatched"] is True
    assert attrs["capability_file"] == "capabilities/capture.md"
    assert attrs["classifier_strategy"] == "deterministic"
    assert isinstance(attrs["classifier_latency_ms"], int)
    assert attrs["classifier_latency_ms"] >= 0
    assert isinstance(attrs["continuity_turn"], bool)
    assert isinstance(attrs["capability_file_mtime"], float)
    assert attrs["capability_file_mtime"] > 0


# ---------------------------------------------------------------------------
# Test 15: capability_dispatched = False for unknown intent
# ---------------------------------------------------------------------------

def test_capability_dispatched_false_for_unknown(tmp_path, monkeypatch):
    """Test 15: when intent = 'unknown', capability_dispatched = False (bool).

    Production failure: Honeycomb query 'capability_dispatched = false' never
    matches because attribute is True or string; negative-path debugging broken.
    Fails RED if capability_dispatched is set as string mirror of intent.
    Model/temperature: mocked LLM returns 'unknown'.
    """
    (tmp_path / "unknown.md").write_text("# stub: unknown")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps({"intent": "unknown"}))]
    mock_client.messages.create.return_value = mock_msg

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client):
        ts.compute_turn_state("hmm")

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    attrs = dict(ts_span.attributes)
    assert attrs["capability_dispatched"] is False
    assert isinstance(attrs["capability_dispatched"], bool)


# ---------------------------------------------------------------------------
# Test 16: PII discipline on error path
# ---------------------------------------------------------------------------

def test_error_span_no_pii_no_exception_message(tmp_path, monkeypatch):
    """Test 16: classifier_call_failed span has error attrs; no exception.message; no user text.

    Production failure: user message or exception text lands in span attribute,
    leaking PII into Honeycomb or breaking family-deployment compliance.
    Fails RED if exception text or user_message is written to span attributes.
    Model/temperature: mocked.
    """
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("network down")
    user_message = "hmm secret project details"

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client), \
         patch("turn_state.time.sleep"), \
         pytest.raises(SystemExit):
        with patch("sys.stdout", io.StringIO()):
            ts.compute_turn_state(user_message)

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    attrs = dict(ts_span.attributes)

    assert "error.code" in attrs
    assert attrs["error.code"] == "classifier_call_failed"
    assert "error.type" in attrs
    assert "error.location" in attrs
    assert "exception.message" not in attrs
    assert "exception.stacktrace" not in attrs
    # No user message text in any attribute value
    for v in attrs.values():
        if isinstance(v, str):
            assert user_message not in v


# ---------------------------------------------------------------------------
# Test 17: continuity_turn = True for short message
# ---------------------------------------------------------------------------

def test_continuity_turn_true_for_short_message(tmp_path, monkeypatch):
    """Test 17: 'yes' (1 word) -> continuity_turn = True on span.

    Production failure: multi-turn debugging in Honeycomb broken; cannot
    distinguish continuation turns from intent turns in trace queries.
    Fails RED without _is_continuity() and span.set_attribute('continuity_turn').
    Model/temperature: mocked.
    """
    (tmp_path / "unknown.md").write_text("# stub: unknown")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps({"intent": "unknown"}))]
    mock_client.messages.create.return_value = mock_msg

    with patch("turn_state.anthropic.Anthropic", return_value=mock_client):
        ts.compute_turn_state("yes")

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    assert dict(ts_span.attributes)["continuity_turn"] is True


# ---------------------------------------------------------------------------
# Test 18: continuity_turn = False for long message
# ---------------------------------------------------------------------------

def test_continuity_turn_false_for_long_message(tmp_path, monkeypatch):
    """Test 18: 7-word message -> continuity_turn = False.

    Production failure: false positives on continuity_turn flag every normal
    message as a continuation; debugging signal becomes noise.
    Fails RED if _is_continuity threshold is wrong or attribute not set.
    Model/temperature: N/A (signal hit).
    """
    (tmp_path / "query_tasks.md").write_text("# stub: query_tasks")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    ts.compute_turn_state("what are my tasks this week please")

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    assert dict(ts_span.attributes)["continuity_turn"] is False


# ---------------------------------------------------------------------------
# Test 19: latency and mtime attributes are correct types
# ---------------------------------------------------------------------------

def test_latency_and_mtime_types(tmp_path, monkeypatch):
    """Test 19: classifier_latency_ms is int >= 0; capability_file_mtime is non-zero float.

    Production failure: Honeycomb numeric queries on latency or mtime fail
    because attribute is wrong type or zero.
    Fails RED without time.monotonic() measurement and os.path.getmtime() call.
    Model/temperature: N/A.
    """
    (tmp_path / "capture.md").write_text("# stub")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))

    exporter = _make_exporter()
    import turn_state as ts
    ts.configure_tracer_provider(exporter)

    ts.compute_turn_state("remind me to call the dentist")

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    attrs = dict(ts_span.attributes)

    assert isinstance(attrs["classifier_latency_ms"], int)
    assert attrs["classifier_latency_ms"] >= 0
    assert isinstance(attrs["capability_file_mtime"], float)
    assert attrs["capability_file_mtime"] > 0.0


# ---------------------------------------------------------------------------
# Test 20: main() stdout contract
# ---------------------------------------------------------------------------

def test_main_stdout_contract(tmp_path, monkeypatch):
    """Test 20: main() writes ok=True JSON with intent and capability_prompt to stdout.

    Production failure: main() discards compute_turn_state() return value; no stdout
    emitted on success path; plugin maps subprocess to non-zero exit error; every
    GTD tool call silently fails.
    Fails RED without ok(result) call in main().
    Model/temperature: N/A -- deterministic signal path.
    """
    (tmp_path / "capture.md").write_text("# stub: capture")
    monkeypatch.setenv("GTD_CAPABILITIES_DIR", str(tmp_path))
    import turn_state as ts

    stdin_payload = json.dumps({"user_message": "remind me to call the dentist"})
    captured = io.StringIO()

    with patch("sys.stdin", io.StringIO(stdin_payload)), \
         patch("sys.stdout", captured), \
         pytest.raises(SystemExit) as exc_info:
        ts.main()

    assert exc_info.value.code == 0
    output = json.loads(captured.getvalue())
    assert output["ok"] is True
    assert output["data"]["intent"] in ts._VALID_INTENTS
    assert output["data"]["capability_prompt"] != ""
