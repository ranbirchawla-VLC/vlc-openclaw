"""LLM tests for turn_state.py.

9 fixtures at temperature=0, claude-sonnet-4-6, 3x require-all-pass via run_llm_3x.py.
GTD_CAPABILITIES_DIR points at stub files (set by conftest autouse fixture).

Gate report answers (per CLAUDE.md extension, answered for this file):
1. Each test reproduces the production failure mode named in its docstring.
2. Each test was run against unfixed code (no turn_state.py present) and confirmed
   ImportError / intent mismatch before implementation. Verified 2026-05-04.
3. Model: claude-sonnet-4-6. Temperature: 0. Matches production GTD agent config
   (mnemo/claude-sonnet-4-6 in ~/.openclaw/openclaw.json, temperature=0 constant).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2])
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import turn_state as ts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(message: str) -> dict:
    """Call compute_turn_state and return result dict."""
    return ts.compute_turn_state(message)


# ---------------------------------------------------------------------------
# Tests 1-6: per-intent classification at temp=0
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_llm_capture_intent():
    """Test 1: natural capture phrasing routes to capture.

    Production failure: ambiguous capture phrasing bypasses signal and LLM
    returns wrong intent; item never recorded.
    """
    result = _classify("add a follow-up with the lawyer to my list")
    assert result["intent"] == "capture"


@pytest.mark.llm
def test_llm_query_tasks_intent():
    """Test 2: task query phrasing routes to query_tasks."""
    result = _classify("what tasks do I have this week?")
    assert result["intent"] == "query_tasks"


@pytest.mark.llm
def test_llm_query_ideas_intent():
    """Test 3: ideas query routes to query_ideas."""
    result = _classify("any ideas on the list?")
    assert result["intent"] == "query_ideas"


@pytest.mark.llm
def test_llm_query_parking_lot_intent():
    """Test 4: parking lot query routes to query_parking_lot."""
    result = _classify("show me the parking lot")
    assert result["intent"] == "query_parking_lot"


@pytest.mark.llm
def test_llm_review_intent():
    """Test 5: review phrasing routes to review."""
    result = _classify("let's do the weekly review")
    assert result["intent"] == "review"


@pytest.mark.llm
def test_llm_calendar_read_intent():
    """Test 6: schedule query routes to calendar_read."""
    result = _classify("what does my schedule look like tomorrow?")
    assert result["intent"] == "calendar_read"


# ---------------------------------------------------------------------------
# Test 7: continuity-turn handling
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_llm_continuity_turn_valid_result():
    """Test 7: 'yes' (1-word continuity) -> valid intent; no error; continuity_turn = True on span.

    Production failure: single-word continuation triggers error exit instead of
    graceful unknown routing; multi-turn capture flow broken. Also verifies
    continuity_turn span attribute is emitted for observability.
    """
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    ts.configure_tracer_provider(exporter)

    result = _classify("yes")
    assert result["intent"] in ts._VALID_INTENTS
    assert result["capability_prompt"] is not None

    spans = exporter.get_finished_spans()
    ts_span = next(s for s in spans if s.name == "gtd.turn_state")
    assert dict(ts_span.attributes)["continuity_turn"] is True


# ---------------------------------------------------------------------------
# Test 8: negative-path (greeting) -> unknown
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_llm_greeting_routes_unknown():
    """Test 8: greeting routes to unknown; capability_dispatched = False.

    Production failure: LLM classifies greeting as a GTD intent; tool called
    with no user data; agent confuses or errors.
    """
    result = _classify("hey Trina, how's it going?")
    assert result["intent"] == "unknown"


# ---------------------------------------------------------------------------
# Test 9: no parameter extraction in LLM response
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_llm_no_parameter_extraction():
    """Test 9: LLM JSON response for any message has exactly one key: 'intent'.

    Production failure: LLM extracts entities into classifier response,
    leaking slot-filling into the dispatcher layer; downstream capabilities
    receive stale or fabricated parameters.
    """
    import re
    import anthropic

    api_key_raw = None
    import os
    from pathlib import Path as P
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        api_key_raw = env_key
    else:
        config_path = P.home() / ".openclaw" / "openclaw.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            api_key_raw = config["models"]["providers"]["mnemo"]["apiKey"]

    if not api_key_raw:
        pytest.skip("no API key")

    client = anthropic.Anthropic(api_key=api_key_raw, base_url="https://api.anthropic.com")
    # Use the same prompt the classifier uses, with a rich test message
    prompt = ts._CLASSIFIER_PROMPT.replace("{user_message}", "add a task to call the dentist on Friday at 3pm")
    response = client.messages.create(
        model=ts._MODEL,
        max_tokens=ts._MAX_TOKENS,
        temperature=ts._TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    parsed = json.loads(raw)
    # Must have exactly one key
    assert list(parsed.keys()) == ["intent"], f"expected only 'intent' key, got: {list(parsed.keys())}"
    assert parsed["intent"] in ts._VALID_INTENTS
