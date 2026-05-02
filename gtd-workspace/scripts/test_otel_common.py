"""Tests for scripts/otel_common.py — OTLP tracer, traceparent, @traced_llm_call.

Uses InMemorySpanExporter; no live OTLP collector required.
Each test guards a specific production failure mode; see inline comments.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    from otel_common import configure_tracer_provider
    configure_tracer_provider(exporter)
    return exporter


def _attempt_attrs(exporter: InMemorySpanExporter) -> list[dict]:
    """Return attributes dicts for attempt spans only (have llm.attempt attribute)."""
    return [
        dict(s.attributes)
        for s in exporter.get_finished_spans()
        if "llm.attempt" in (s.attributes or {})
    ]


def _all_attrs(exporter: InMemorySpanExporter) -> list[dict]:
    return [dict(s.attributes or {}) for s in exporter.get_finished_spans()]


def _make_anthropic_sdk_mock(response_text: str = '{"result": "ok"}') -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def _make_qwen_http_mock(response_text: str = '{"result": "ok"}') -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": {"content": response_text}}
    return resp


# ---------------------------------------------------------------------------
# Case 1: Outer role, success on first try
# Guards against: role leak — outer call accidentally routing to Qwen.
# ---------------------------------------------------------------------------

def test_outer_success_emits_claude_span() -> None:
    exporter = _make_exporter()

    from otel_common import traced_llm_call

    @traced_llm_call(role="outer", prompt_template="test_outer_v1")
    def my_tool(text: str) -> dict:
        return {"result": text}

    with patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        result = my_tool("hello")

    assert result == {"result": "hello"}
    attempts = _attempt_attrs(exporter)
    assert len(attempts) == 1
    assert attempts[0]["llm.provider"] == "claude"
    assert attempts[0]["llm.model"] == "claude-sonnet-4-6"
    assert attempts[0]["llm.attempt"] == 1
    assert "llm.fallthrough_reason" not in attempts[0]
    qwen_spans = [a for a in _all_attrs(exporter) if a.get("llm.provider") == "qwen"]
    assert len(qwen_spans) == 0


# ---------------------------------------------------------------------------
# Case 2: Outer role, ValidationError → ChainExhausted after ONE attempt
# Guards against: outer role retrying ValidationError (temperature=0 means the
# same bad output on every retry; retry budget is for transient errors only).
# RED check: without "no retry on ValidationError" rule, decorator retries
# MAX_RETRIES times → test's assertion of exactly 1 span fails against unfixed code.
# ---------------------------------------------------------------------------

def test_outer_validation_error_raises_immediately() -> None:
    exporter = _make_exporter()

    from otel_common import ChainExhausted, ValidationError, traced_llm_call

    @traced_llm_call(role="outer", prompt_template="test_outer_v1")
    def my_tool(text: str) -> dict:
        raise ValidationError("schema mismatch")

    with patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()), \
         patch("otel_common.time.sleep"):
        with pytest.raises(ChainExhausted) as exc_info:
            my_tool("hello")

    assert len(exc_info.value.errors) == 1
    attempts = _attempt_attrs(exporter)
    # Exactly one attempt — ValidationError must not be retried
    assert len(attempts) == 1
    assert attempts[0]["llm.provider"] == "claude"
    # No Qwen spans — outer role never falls through to Qwen
    assert all(a.get("llm.provider") != "qwen" for a in _all_attrs(exporter))


# ---------------------------------------------------------------------------
# Case 3: Inner role, Qwen succeeds first try
# Guards against: Sonnet called when Qwen is available (cost waste, wrong telemetry).
# ---------------------------------------------------------------------------

def test_inner_qwen_success_emits_qwen_span() -> None:
    exporter = _make_exporter()

    from otel_common import traced_llm_call

    @traced_llm_call(role="inner", prompt_template="test_inner_v1")
    def my_tool(text: str) -> dict:
        return {"result": text}

    with patch("otel_common.httpx.post", return_value=_make_qwen_http_mock()):
        result = my_tool("hello")

    assert result == {"result": "hello"}
    attempts = _attempt_attrs(exporter)
    assert len(attempts) == 1
    assert attempts[0]["llm.provider"] == "qwen"
    assert attempts[0]["llm.chain_position"] == 0
    assert all(a.get("llm.provider") != "claude" for a in attempts)


# ---------------------------------------------------------------------------
# Case 4: Inner role, Qwen ValidationError → Sonnet succeeds
# Guards against: ValidationError raises instead of chain-advancing,
# causing every inner tool call to fail when Qwen validation is off.
# ---------------------------------------------------------------------------

def test_inner_qwen_validation_fails_sonnet_succeeds() -> None:
    exporter = _make_exporter()

    from otel_common import ValidationError, traced_llm_call

    call_count = {"n": 0}

    @traced_llm_call(role="inner", prompt_template="test_inner_v1")
    def my_tool(text: str) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValidationError("qwen schema fail")
        return {"result": text}

    with patch("otel_common.httpx.post", return_value=_make_qwen_http_mock()), \
         patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        result = my_tool("hello")

    assert result == {"result": "hello"}
    attempts = _attempt_attrs(exporter)
    assert len(attempts) == 2

    qwen = next(a for a in attempts if a["llm.provider"] == "qwen")
    assert qwen["llm.fallthrough_reason"] == "validation_failed"
    assert qwen["llm.chain_position"] == 0

    claude = next(a for a in attempts if a["llm.provider"] == "claude")
    assert claude["llm.chain_position"] == 1

    # Parent span should record retry_occurred
    parent = next(
        (s for s in exporter.get_finished_spans()
         if s.attributes and s.attributes.get("llm.prompt_template") == "test_inner_v1"
         and "llm.attempt" not in s.attributes),
        None,
    )
    assert parent is not None
    assert parent.attributes.get("llm.retry_occurred") is True


# ---------------------------------------------------------------------------
# Case 5: Inner role, both providers fail → ChainExhausted with both errors
# Guards against: losing validation errors makes chain exhaustion undebuggable.
# ---------------------------------------------------------------------------

def test_inner_both_fail_raises_chain_exhausted_with_all_errors() -> None:
    exporter = _make_exporter()

    from otel_common import ChainExhausted, ValidationError, traced_llm_call

    @traced_llm_call(role="inner", prompt_template="test_inner_v1")
    def my_tool(text: str) -> dict:
        raise ValidationError("bad schema")

    with patch("otel_common.httpx.post", return_value=_make_qwen_http_mock()), \
         patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        with pytest.raises(ChainExhausted) as exc_info:
            my_tool("hello")

    assert len(exc_info.value.errors) == 2
    assert all(isinstance(e, ValidationError) for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# Case 6: Inner role, Qwen endpoint unavailable → health cache skips Qwen
# Guards against: per-request Qwen timeouts accumulate without cache,
# making all inner calls slow when Qwen is down.
# RED check: without _qwen_down_since check, every call retries Qwen —
# test asserts "endpoint_unavailable" span in second call — fails unfixed.
# ---------------------------------------------------------------------------

def test_inner_qwen_unavailable_health_cache_skip() -> None:
    import otel_common

    exporter = _make_exporter()
    t0 = 1000.0

    from otel_common import traced_llm_call

    # my_tool calls _client.complete() so that httpx.post fires on the Qwen leg
    # and anthropic.Anthropic().messages.create() fires on the Sonnet leg.
    @traced_llm_call(role="inner", prompt_template="test_inner_v1")
    def my_tool(text: str, _client=None) -> dict:
        if _client is not None:
            _client.complete(text)
        return {"result": text}

    # First call: Qwen raises httpx.ConnectError (production exception, not builtin) →
    # sets health cache, chain advances to Sonnet.
    with patch("otel_common.time.time", return_value=t0), \
         patch("otel_common.time.sleep"), \
         patch("otel_common.httpx.post", side_effect=httpx.ConnectError("refused")), \
         patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        result = my_tool("first")

    assert result == {"result": "first"}
    assert otel_common._qwen_down_since == pytest.approx(t0)

    # Second call within 30s: Qwen skipped, only Sonnet attempted
    exporter.clear()
    with patch("otel_common.time.time", return_value=t0 + 10.0), \
         patch("otel_common.httpx.post") as mock_post, \
         patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        result2 = my_tool("second")

    assert result2 == {"result": "second"}
    mock_post.assert_not_called()
    skipped = [a for a in _all_attrs(exporter) if a.get("llm.fallthrough_reason") == "endpoint_unavailable"]
    assert len(skipped) >= 1

    # Third call after 30s: Qwen retried
    exporter.clear()
    with patch("otel_common.time.time", return_value=t0 + 35.0), \
         patch("otel_common.httpx.post", return_value=_make_qwen_http_mock()):
        result3 = my_tool("third")

    assert result3 == {"result": "third"}
    qwen_attempts = [a for a in _attempt_attrs(exporter) if a.get("llm.provider") == "qwen"]
    assert len(qwen_attempts) >= 1


# ---------------------------------------------------------------------------
# Case 7: Transient error attempt 1 → success attempt 2, same provider
# Guards against: without retry on transient errors, chain falls through to
# Sonnet on every brief network hiccup.
# ---------------------------------------------------------------------------

def test_transient_error_retries_same_provider() -> None:
    exporter = _make_exporter()

    from otel_common import traced_llm_call

    call_count = {"n": 0}

    @traced_llm_call(role="outer", prompt_template="test_outer_v1")
    def my_tool(text: str) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionError("transient")
        return {"result": text}

    with patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()), \
         patch("otel_common.time.sleep") as mock_sleep:
        result = my_tool("hello")

    assert result == {"result": "hello"}
    attempts = _attempt_attrs(exporter)
    assert len(attempts) == 2
    assert attempts[0]["llm.provider"] == "claude"
    assert attempts[0]["llm.attempt"] == 1
    assert attempts[1]["llm.provider"] == "claude"
    assert attempts[1]["llm.attempt"] == 2
    mock_sleep.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Case 8: Temperature always 0
# Tests both AnthropicLLMClient and OllamaLLMClient enforce temperature=0.
# Guards against: non-zero temperature makes retry useless (same bad output
# every attempt) and breaks LLM test determinism.
# RED check: without temperature enforcement in LLMClient, mock shows whatever
# the caller passes — assert 0 fails against unfixed code.
# ---------------------------------------------------------------------------

def test_anthropic_client_temperature_always_zero() -> None:
    """AnthropicLLMClient.complete() must always pass temperature=0 to the SDK."""
    from otel_common import AnthropicLLMClient

    mock_sdk = _make_anthropic_sdk_mock()
    with patch("otel_common.anthropic.Anthropic", return_value=mock_sdk):
        client = AnthropicLLMClient(model="claude-sonnet-4-6", endpoint="https://api.anthropic.com")
        client.complete("test prompt")

    call_kwargs = mock_sdk.messages.create.call_args
    assert call_kwargs is not None
    assert call_kwargs.kwargs.get("temperature") == 0


def test_qwen_client_temperature_always_zero() -> None:
    """OllamaLLMClient.complete() must always pass temperature=0 in request body."""
    from otel_common import OllamaLLMClient

    mock_resp = _make_qwen_http_mock()
    with patch("otel_common.httpx.post", return_value=mock_resp) as mock_post:
        client = OllamaLLMClient(model="qwen3:latest", endpoint="http://localhost:11434")
        client.complete("test prompt")

    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs.get("json") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})
    assert body.get("options", {}).get("temperature") == 0


# ---------------------------------------------------------------------------
# Case 9: Traceparent propagation
# Guards against: broken parent context = all plugin spans appear as orphaned
# roots in Honeycomb, no end-to-end trace.
# ---------------------------------------------------------------------------

def test_traceparent_propagation_returns_context(monkeypatch: pytest.MonkeyPatch) -> None:
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    parent_id = "00f067aa0ba902b7"
    traceparent = f"00-{trace_id}-{parent_id}-01"
    monkeypatch.setenv("TRACEPARENT", traceparent)

    exporter = _make_exporter()

    from otel_common import extract_parent_context, get_tracer

    parent_ctx = extract_parent_context()
    assert parent_ctx is not None

    # Start a child span under the extracted context; verify trace ID propagates
    tracer = get_tracer("test")
    with tracer.start_as_current_span("child_span", context=parent_ctx) as span:
        sc = span.get_span_context()
        extracted_trace_id = format(sc.trace_id, "032x")

    assert extracted_trace_id == trace_id


def test_extract_parent_context_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRACEPARENT", raising=False)

    from otel_common import extract_parent_context
    assert extract_parent_context() is None


# ---------------------------------------------------------------------------
# Case 10: time.sleep mocked — test suite stays fast
# Guards against: retry exhaustion test accumulating 3+ seconds per case.
# ---------------------------------------------------------------------------

def test_retry_sleep_is_mocked_and_test_runs_fast() -> None:
    exporter = _make_exporter()

    from otel_common import ChainExhausted, traced_llm_call

    @traced_llm_call(role="outer", prompt_template="test_outer_v1")
    def my_tool(text: str) -> dict:
        raise ConnectionError("always fails")

    start = time.monotonic()
    with patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()), \
         patch("otel_common.time.sleep") as mock_sleep:
        with pytest.raises(ChainExhausted):
            my_tool("hello")
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"Test took {elapsed:.2f}s — time.sleep not mocked"
    # MAX_RETRIES=3 → 3 sleeps between 4 attempts
    assert mock_sleep.call_count == 3
    mock_sleep.assert_called_with(1)


# ---------------------------------------------------------------------------
# _is_transient_google: direct unit tests
# Guards: Google API 5xx must advance the retry loop; 4xx must not.
# httpx._is_transient handles LLM/httpx errors; _is_transient_google handles
# Google API client errors. Both live in otel_common for cohesion.
# ---------------------------------------------------------------------------

def test_is_transient_google_true_for_5xx_http_error() -> None:
    from googleapiclient.errors import HttpError
    from otel_common import _is_transient_google

    for status in (500, 503):
        resp = MagicMock()
        resp.status = status
        assert _is_transient_google(HttpError(resp=resp, content=b"error"))


def test_is_transient_google_false_for_4xx_http_error() -> None:
    from googleapiclient.errors import HttpError
    from otel_common import _is_transient_google

    for status in (400, 403, 404):
        resp = MagicMock()
        resp.status = status
        assert not _is_transient_google(HttpError(resp=resp, content=b"error"))


def test_is_transient_google_true_for_connection_errors() -> None:
    from otel_common import _is_transient_google

    assert _is_transient_google(ConnectionError("refused"))
    assert _is_transient_google(TimeoutError("timeout"))
    assert _is_transient_google(OSError("os error"))


def test_is_transient_google_false_for_non_network() -> None:
    from otel_common import _is_transient_google

    assert not _is_transient_google(Exception("generic"))
    assert not _is_transient_google(ValueError("val"))
    assert not _is_transient_google(KeyError("key"))


# ---------------------------------------------------------------------------
# _is_transient: direct unit tests — B-1 review finding
# Guards: any future regression in transient-error exception coverage is
# immediately visible without running the full chain integration tests.
# httpx exceptions do NOT inherit from Python builtins; they must be enumerated.
# ---------------------------------------------------------------------------

def test_is_transient_true_for_httpx_network_exceptions() -> None:
    from otel_common import _is_transient

    assert _is_transient(httpx.ConnectError("refused"))
    assert _is_transient(httpx.TimeoutException("timed out"))
    assert _is_transient(httpx.NetworkError("network error"))

    mock_response = MagicMock()
    mock_response.status_code = 503
    assert _is_transient(
        httpx.HTTPStatusError("503", request=MagicMock(), response=mock_response)
    )


def test_is_transient_true_for_builtin_network_exceptions() -> None:
    from otel_common import _is_transient

    assert _is_transient(ConnectionError("conn refused"))
    assert _is_transient(TimeoutError("timed out"))
    assert _is_transient(OSError("os error"))


def test_is_transient_false_for_non_transient_exceptions() -> None:
    from otel_common import _is_transient

    assert not _is_transient(Exception("generic"))
    assert not _is_transient(ValueError("value error"))
    assert not _is_transient(KeyError("key"))

    mock_response = MagicMock()
    mock_response.status_code = 400
    assert not _is_transient(
        httpx.HTTPStatusError("400", request=MagicMock(), response=mock_response)
    )


# ---------------------------------------------------------------------------
# M-1: Qwen 5xx response → raise_for_status raises HTTPStatusError →
# health cache set + chain advances to Sonnet.
# Guards: without raise_for_status(), a 503 returns normally, JSON parsing
# raises KeyError, _is_transient(KeyError) is False, chain dies instead of
# advancing to Sonnet.
# RED check: remove raise_for_status() call from OllamaLLMClient.complete() →
# mock_resp.json()["message"]["content"] raises KeyError → bare raise exits
# chain → result never returned.
# ---------------------------------------------------------------------------

def test_inner_qwen_5xx_sets_health_cache_and_advances_to_sonnet() -> None:
    import otel_common

    exporter = _make_exporter()
    t0 = 2000.0

    from otel_common import traced_llm_call

    @traced_llm_call(role="inner", prompt_template="test_inner_v1")
    def my_tool(text: str, _client=None) -> dict:
        if _client is not None:
            _client.complete(text)
        return {"result": text}

    # Mock a real 503 error body: no "message" key (Ollama error responses differ from 200).
    # Without raise_for_status(): json()["message"] raises KeyError, _is_transient(KeyError)
    # is False, bare raise propagates out → chain dies instead of advancing to Sonnet.
    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.json.return_value = {"error": "service unavailable"}
    mock_503.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503 Server Error", request=MagicMock(), response=mock_503
    )

    with patch("otel_common.time.time", return_value=t0), \
         patch("otel_common.time.sleep"), \
         patch("otel_common.httpx.post", return_value=mock_503), \
         patch("otel_common.anthropic.Anthropic", return_value=_make_anthropic_sdk_mock()):
        result = my_tool("hello")

    assert result == {"result": "hello"}
    assert otel_common._qwen_down_since == pytest.approx(t0)

    attempts = _attempt_attrs(exporter)
    sonnet_attempts = [a for a in attempts if a.get("llm.provider") == "claude"]
    assert len(sonnet_attempts) >= 1
    assert sonnet_attempts[0]["llm.chain_position"] == 1
