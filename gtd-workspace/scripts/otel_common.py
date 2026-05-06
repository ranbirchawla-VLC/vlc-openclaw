"""OTLP exporter, tracer factory, traceparent propagation, and @traced_llm_call.

Module-level setup runs once on first import. Tests call configure_tracer_provider()
with InMemorySpanExporter before invoking any decorated function.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

import anthropic
import httpx
from googleapiclient.errors import HttpError as _GoogleHttpError
from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OUTER_MODEL = {
    "provider": "claude",
    "model": "claude-sonnet-4-6",
    "endpoint": "https://api.anthropic.com",
}

_INNER_CHAIN = [
    {"provider": "qwen",   "model": "qwen3:latest",      "endpoint": "http://localhost:11434"},
    {"provider": "claude", "model": "claude-sonnet-4-6",  "endpoint": "https://api.anthropic.com"},
]

_TEMPERATURE = 0
_MAX_TOKENS = 1024
_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Health cache
# ---------------------------------------------------------------------------

_qwen_down_since: float | None = None  # time.time() value when Qwen last failed; None = healthy


def _qwen_is_healthy() -> bool:
    return _qwen_down_since is None or (time.time() - _qwen_down_since) >= 30


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised by a wrapped function on schema/parse failure to trigger chain advance."""


class ChainExhausted(Exception):
    """Raised when all chain providers have been exhausted."""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        super().__init__(f"LLM chain exhausted after {len(errors)} failure(s): {errors}")


# ---------------------------------------------------------------------------
# Exporter / TracerProvider
# ---------------------------------------------------------------------------

_OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "gtd")

_tracer_provider: TracerProvider | None = None


def configure_tracer_provider(exporter: SpanExporter | None = None) -> None:
    """Configure the module TracerProvider.

    Pass InMemorySpanExporter in tests. The module-level _tracer_provider is
    replaced directly; trace.set_tracer_provider() is NOT called because the
    OTel SDK only allows one global override per process (subsequent calls are
    silently ignored). All internal callers use get_tracer() which reads the
    module-level variable directly, so tests can swap providers freely.
    """
    global _tracer_provider
    resource = Resource(attributes={SERVICE_NAME: _SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if exporter is None:
        real_exporter = OTLPSpanExporter(
            endpoint=f"{_OTEL_ENDPOINT}/v1/traces"
        )
        # SimpleSpanProcessor ships spans synchronously; required for short-lived plugin scripts
        # that exit before BatchSpanProcessor's default 5s flush window.
        provider.add_span_processor(SimpleSpanProcessor(real_exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))

    _tracer_provider = provider


# Run once on import with the real OTLP exporter.
configure_tracer_provider()


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer from the module TracerProvider (not the global OTel default)."""
    return _tracer_provider.get_tracer(name)


# ---------------------------------------------------------------------------
# Traceparent propagation
# ---------------------------------------------------------------------------

def extract_parent_context() -> context.Context | None:
    """Read TRACEPARENT env var and return an OTel Context for parent linkage.

    Returns None if TRACEPARENT is not set.
    """
    tp = os.environ.get("TRACEPARENT")
    if not tp:
        return None
    propagator = TraceContextTextMapPropagator()
    return propagator.extract(carrier={"traceparent": tp})


@contextlib.contextmanager
def attach_parent_trace_context():
    """Read TRACEPARENT from env and attach it as the active OTel context.

    Use in comma-form wrapping the script's top-level span so the Python span
    becomes a child of the Node plugin-layer parent span in Honeycomb:

        with attach_parent_trace_context():
            with tracer.start_as_current_span("gtd.<tool>.run") as span:
                ...

    No-op if TRACEPARENT is absent, malformed, or opentelemetry is not installed.
    """
    token = None
    try:
        traceparent = os.environ.get("TRACEPARENT", "").strip()
        if traceparent:
            from opentelemetry.propagate import extract
            from opentelemetry import context as otel_context
            ctx = extract({"traceparent": traceparent})
            token = otel_context.attach(ctx)
    except Exception:
        pass
    try:
        yield
    finally:
        if token is not None:
            try:
                from opentelemetry import context as otel_context
                otel_context.detach(token)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# LLM client abstraction
# ---------------------------------------------------------------------------

def _load_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        try:
            return config["models"]["providers"]["mnemo"]["apiKey"]
        except KeyError:
            pass
    raise RuntimeError(
        "ANTHROPIC_API_KEY not set and no key found at ~/.openclaw/openclaw.json"
    )


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class AnthropicLLMClient:
    """Wraps anthropic.Anthropic SDK; enforces temperature=0."""

    def __init__(self, model: str, endpoint: str) -> None:
        self._model = model
        self._sdk = anthropic.Anthropic(
            api_key=_load_api_key(),
            base_url=endpoint,
        )

    def complete(self, prompt: str) -> str:
        response = self._sdk.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class OllamaLLMClient:
    """Calls Ollama chat API via httpx; enforces temperature=0."""

    def __init__(self, model: str, endpoint: str) -> None:
        self._model = model
        self._endpoint = endpoint

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            f"{self._endpoint}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": _TEMPERATURE},
                "stream": False,
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


def _make_client(provider_config: dict) -> LLMClient:
    if provider_config["provider"] == "qwen":
        return OllamaLLMClient(model=provider_config["model"], endpoint=provider_config["endpoint"])
    return AnthropicLLMClient(model=provider_config["model"], endpoint=provider_config["endpoint"])


# ---------------------------------------------------------------------------
# @traced_llm_call decorator
# ---------------------------------------------------------------------------

def traced_llm_call(
    role: Literal["inner", "outer"],
    prompt_template: str,
) -> Callable:
    """Decorator that wraps an LLM call function with retry/chain logic and OTLP spans.

    The wrapped function:
    - Returns a dict on success.
    - Raises ValidationError on schema failure (triggers chain advance / ChainExhausted).
    - Raises any other exception to abort immediately (e.g. auth errors).

    If the function signature includes a `_client` parameter, the decorator
    injects the active LLMClient so the function can make the actual API call.
    """
    def decorator(fn: Callable) -> Callable:
        _accepts_client = "_client" in inspect.signature(fn).parameters

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            tracer = get_tracer(fn.__module__ or __name__)
            span_name = f"llm.{prompt_template}"

            with tracer.start_as_current_span(span_name) as parent_span:
                parent_span.set_attribute("llm.prompt_template", prompt_template)

                if role == "outer":
                    result, errors, retry_occurred = _run_outer(
                        fn, args, kwargs, tracer, prompt_template, _accepts_client
                    )
                else:
                    result, errors, retry_occurred = _run_inner(
                        fn, args, kwargs, tracer, prompt_template, _accepts_client
                    )

                if retry_occurred:
                    parent_span.set_attribute("llm.retry_occurred", True)

                if errors:
                    raise ChainExhausted(errors)

                return result

        return wrapper
    return decorator


def _run_outer(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    tracer: trace.Tracer,
    prompt_template: str,
    accepts_client: bool,
) -> tuple[dict | None, list[Exception], bool]:
    """Outer role: single provider (Sonnet), retry on transient errors only.

    Returns (result, errors, retry_occurred).
    """
    provider_config = _OUTER_MODEL
    client = _make_client(provider_config)
    errors: list[Exception] = []

    for attempt in range(1, _MAX_RETRIES + 2):
        with tracer.start_as_current_span("llm.attempt") as span:
            _set_attempt_attrs(span, provider_config, attempt, prompt_template)
            if attempt > 1:
                time.sleep(1)
            try:
                call_kwargs = {**kwargs}
                if accepts_client:
                    call_kwargs["_client"] = client
                result = fn(*args, **call_kwargs)
                return result, [], attempt > 1
            except ValidationError as exc:
                span.set_attribute("llm.fallthrough_reason", "validation_failed")
                span.set_attribute("llm.validation_error", str(exc))
                errors.append(exc)
                return None, errors, False  # immediate ChainExhausted; no retry
            except Exception as exc:
                if _is_transient(exc):
                    errors.append(exc)
                    if attempt <= _MAX_RETRIES:
                        continue  # retry same provider
                    return None, errors, attempt > 1  # retries exhausted
                raise  # non-transient: re-raise immediately


def _run_inner(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    tracer: trace.Tracer,
    prompt_template: str,
    accepts_client: bool,
) -> tuple[dict | None, list[Exception], bool]:
    """Inner role: Qwen primary, Sonnet fallback; ValidationError advances chain.

    Returns (result, errors, retry_occurred).
    """
    global _qwen_down_since

    errors: list[Exception] = []
    total_calls = 0

    for position, provider_config in enumerate(_INNER_CHAIN):
        # Health cache check for Qwen
        if position == 0 and not _qwen_is_healthy():
            with tracer.start_as_current_span("llm.skipped") as skip_span:
                skip_span.set_attribute("llm.provider", provider_config["provider"])
                skip_span.set_attribute("llm.chain_position", position)
                skip_span.set_attribute("llm.fallthrough_reason", "endpoint_unavailable")
                skip_span.set_attribute("llm.prompt_template", prompt_template)
            continue

        client = _make_client(provider_config)

        for attempt in range(1, _MAX_RETRIES + 2):
            with tracer.start_as_current_span("llm.attempt") as span:
                _set_attempt_attrs(span, provider_config, attempt, prompt_template)
                span.set_attribute("llm.chain_position", position)
                if attempt > 1:
                    time.sleep(1)
                try:
                    call_kwargs = {**kwargs}
                    if accepts_client:
                        call_kwargs["_client"] = client
                    total_calls += 1
                    result = fn(*args, **call_kwargs)
                    retry_occurred = total_calls > 1 or attempt > 1
                    return result, [], retry_occurred
                except ValidationError as exc:
                    span.set_attribute("llm.fallthrough_reason", "validation_failed")
                    span.set_attribute("llm.validation_error", str(exc))
                    errors.append(exc)
                    break  # advance chain immediately; don't retry same provider
                except Exception as exc:
                    if _is_transient(exc):
                        if position == 0:
                            _qwen_down_since = time.time()
                        errors.append(exc)
                        if attempt <= _MAX_RETRIES:
                            continue  # retry same provider
                        break  # retries exhausted; advance chain
                    raise  # non-transient: re-raise immediately

    return None, errors, len(errors) > 0


def _set_attempt_attrs(
    span: trace.Span,
    provider_config: dict,
    attempt: int,
    prompt_template: str,
) -> None:
    span.set_attribute("llm.provider", provider_config["provider"])
    span.set_attribute("llm.model", provider_config["model"])
    span.set_attribute("llm.temperature", _TEMPERATURE)
    span.set_attribute("llm.attempt", attempt)
    span.set_attribute("llm.prompt_template", prompt_template)
    span.set_attribute("llm.endpoint", provider_config["endpoint"])


def _is_transient(exc: Exception) -> bool:
    return (
        isinstance(exc, (ConnectionError, TimeoutError, OSError))
        or isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError))
        or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500)
    )


def _is_transient_google(exc: Exception) -> bool:
    return (
        isinstance(exc, _GoogleHttpError) and exc.resp.status >= 500
    ) or isinstance(exc, (ConnectionError, TimeoutError, OSError))
