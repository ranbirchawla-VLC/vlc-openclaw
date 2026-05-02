# Sub-step 1 — Shared Helpers Foundation

## What was built

- `scripts/common.py` — plugin-layer constants (`DATA_ROOT`, `TZ`), output helpers (`ok()`, `err()`), and `get_google_credentials(scopes)`.
- `scripts/otel_common.py` — OTLP exporter init, `get_tracer()`, `extract_parent_context()`, `LLMClient` abstraction (`AnthropicLLMClient`, `OllamaLLMClient`), and `@traced_llm_call(role, prompt_template)` decorator.
- `scripts/conftest.py` — sys.path injection and autouse fixtures (health cache reset, ANTHROPIC_API_KEY stub).
- `gtd-workspace/pyproject.toml` — declares all plugin deps.

## Key design decisions

**`ok()`/`err()` exit codes.** Both call `sys.exit(0)`/`sys.exit(1)`. The gateway dispatcher (`index.js`) checks process exit code; removing exits would halve failure detection.

**`@traced_llm_call` error classification.** `ValidationError` causes immediate chain advance (inner) or immediate `ChainExhausted` (outer) — no retry. At `temperature=0`, retrying the same prompt on a validation failure produces the same bad output. Retry budget (`_MAX_RETRIES=3`) is reserved for transient errors only.

**`_active_provider` contextvar omitted.** No Phase 1 wrapped function needs provider-aware prompts. Add if Sub-step 2 surfaces an actual use case.

**`llm.cost_usd`.** Emitted as `0.0` for Qwen (local, no cost). Omitted for Anthropic until a pricing table is wired; `llm.input_tokens` + `llm.output_tokens` are sufficient to compute cost externally.

**TracerProvider not set globally.** `trace.set_tracer_provider()` can only be called once per process. The module holds `_tracer_provider` directly; `get_tracer()` reads it. Tests swap the provider freely via `configure_tracer_provider(InMemorySpanExporter())`.

## Test targets

```
make test-gtd-helpers   # common.py + otel_common.py (22 tests)
make test-gtd           # full scripts suite (30 tests)
```

## Gate 1 result

30 Python tests. 0 LLM tests (no capability prompts this sub-step).

## Lessons

`httpx.ConnectError` and `httpx.TimeoutException` do not inherit from Python builtins (`ConnectionError`, `TimeoutError`); transient-error checks must enumerate httpx exception classes explicitly. Calendar, Gmail, and Calendly plugins built in subsequent sub-steps will hit this trap otherwise.
