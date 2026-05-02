# GTD Workspace — Progress Log

## Sub-step Z — Storage Migration

**Started:** 2026-05-02

**Pre-review commit:** `3f10ea2` — 8 Python tests (7 original + 1 B-1 recovery added post-review), 0 LLM tests (no LLM calls in this sub-step).

**Review findings:**
- 2 blockers (B-1 no park-failure recovery, B-2 weak byte-count verification), both fixed
- 3 majors (M-1 empty-dest semantics — doc only; M-2 missing recovery test — added; M-3 hardcoded Python path in Makefile — fixed to `$(PYTEST)`)
- Minors and nits applied (sha256 hash tree, sentinel file, `shutil.move`, type hints, `Path` objects to `copytree`)

**Post-review commit:** `f959015`

**Live migration:** Run. 2 files, 5,888 bytes copied to `~/agent_data/gtd/ranbir/`. Source parked at `gtd-workspace/storage.migrated/`. sha256 verified.

**Plist patched:** `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir` added to `~/Library/LaunchAgents/ai.openclaw.gateway.plist`.

**Gate 3 — PENDING operator:**
1. Restart gateway: `launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway.plist && launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist`
2. Smoke test: send a GTD action through Telegram, confirm read/write hits `~/agent_data/gtd/ranbir/`
3. Cleanup: `rm -rf gtd-workspace/storage.migrated`
4. Squash: `git rebase -i HEAD~2` on `feature/gtd-trina-substep-Z-storage-migration`, then merge to main

**KNOWN_ISSUES:** None.

**Notes:** Sub-step Z squashed to `bd210f4` and merged to main.

---

## Sub-step 1 — Shared Helpers Foundation

**Started:** 2026-05-02

**Branch:** `feature/gtd-trina-substep-1-shared-helpers`

**Pre-review commit:** `ffb4b76` — 30 Python tests (10 common + 12 otel + 8 migrate carry-forward), 0 LLM tests (no capability prompts this sub-step).

### Files delivered

| File | Purpose |
|---|---|
| `gtd-workspace/scripts/common.py` | Plugin-layer constants (`DATA_ROOT`, `TZ`), `ok()`/`err()` with `sys.exit(0/1)`, `get_google_credentials(scopes)` |
| `gtd-workspace/scripts/otel_common.py` | OTLP exporter init, `configure_tracer_provider()`, `get_tracer()`, `extract_parent_context()`, `ValidationError`, `ChainExhausted`, `AnthropicLLMClient`, `OllamaLLMClient`, `@traced_llm_call(role, prompt_template)` |
| `gtd-workspace/scripts/conftest.py` | `sys.path` injection for scripts/ tests; autouse `reset_qwen_health_cache` fixture; autouse `set_anthropic_api_key` fixture |
| `gtd-workspace/scripts/test_common.py` | 10 tests for `get_google_credentials()` + `ok()`/`err()` |
| `gtd-workspace/scripts/test_otel_common.py` | 12 tests for decorator, LLMClient implementations, traceparent, health cache |
| `gtd-workspace/pyproject.toml` | `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `opentelemetry-{api,sdk,exporter-otlp-proto-http}`, `anthropic`, `httpx` |
| `Makefile` | Added `test-gtd-helpers`, `test-gtd-common`, `test-gtd-otel` targets; `make setup` now installs `gtd-workspace[dev]` |
| `KNOWN_ISSUES.md` | Created; OAuth user-flow doc pointer gap (low priority, sub-step 6) |
| `gtd-workspace/docs/sub-step-1-shared-helpers.md` | Per-sub-step spec doc with design decisions |

### Key design decisions (context for reviewer)

**`ok()`/`err()` use `sys.exit(0/1)`.** Matches canonical pattern in `agent_api_integration_pattern.md`. The `index.js` gateway dispatcher checks `result.status !== 0`; removing exit codes halves failure detection. Tests use `pytest.raises(SystemExit)` + `capsys`.

**`@traced_llm_call` error classification — two distinct classes:**
- `ValidationError` → immediate `ChainExhausted` (outer) or immediate chain advance (inner). No retry. At `temperature=0`, retrying a validation failure produces the same bad output.
- Transient errors (`ConnectionError`, `OSError`, 5xx) → consume retry budget (`_MAX_RETRIES=3`, `time.sleep(1)` between). After budget exhausted: `ChainExhausted` (outer) or advance chain (inner).

**TracerProvider held module-level, not set globally.** `trace.set_tracer_provider()` can only be called once per process (OTel SDK `_Once` guard). Module keeps `_tracer_provider`; `get_tracer()` reads it directly. Tests call `configure_tracer_provider(InMemorySpanExporter())` to swap providers freely.

**`_active_provider` contextvar omitted.** No Phase 1 wrapped function needs provider-aware prompts. Dropped per supervisor review (M-1). `_client` is injected via `inspect.signature` check only when function signature declares it.

**`llm.cost_usd` omitted for Anthropic.** Emitted as `0.0` for Qwen. `llm.input_tokens` + `llm.output_tokens` are sufficient for external cost calculation. No pricing table in this sub-step.

**`_qwen_down_since` is module-level mutable state.** Autouse pytest fixture in `conftest.py` resets it to `None` before and after each test to prevent inter-test bleed.

### Structural note (critical for reviewer)

`gtd-workspace/tools/common.py` is a pre-existing file serving the legacy GTD pipeline tools (JSONL I/O, enums, path resolution). It was **not touched**. The new `scripts/common.py` is a separate file for a separate layer (plugin scripts). They coexist intentionally.

### Gate 1 answers

1. **Tests reproduce production failures?** Yes — each test has an inline comment naming the specific production failure it guards against.
2. **Tests failed against unfixed code first?** All 22 new tests confirmed RED before implementation. Cases 2, 6, 8 specifically demonstrated:
   - Case 2 (outer ValidationError): without the "no retry" rule, decorator retries MAX_RETRIES times → exactly-1-span assertion fails.
   - Case 6 (health cache): without `_qwen_down_since` check, every call retries Qwen → `endpoint_unavailable` span assertion fails.
   - Case 8 (temperature): direct `AnthropicLLMClient`/`OllamaLLMClient` unit test; fails if `temperature` param is omitted or wrong in the mock call.
3. **Model and temperature?** N/A — no live LLM calls. All SDK calls mocked. LLM tests deferred to Sub-step 2 when capability prompts are introduced.

### Gate 2 — PENDING

Run code-reviewer subagent in fresh context. Diff to review: commit `ffb4b76` on `feature/gtd-trina-substep-1-shared-helpers`. Key areas for reviewer:
- `otel_common.py` decorator logic (outer vs inner error handling, retry loop, health cache)
- `common.py` credential loader error handling (all 5 failure modes)
- Test assertions match the behavior they claim to cover
- No dead code; no YAGNI additions

### Gate 3 — PENDING

Light smoke test: confirm `make test-gtd` passes and both modules import cleanly. Real OTLP span verification deferred to Sub-step 2 (first live Google API call).

### Notes for next session

- After Gate 2/3 clear: squash `ffb4b76` + post-review commit into one, merge to main.
- Sub-step 2 starts `gtd-workspace/scripts/calendar/get_events.py` + plugin wiring + LLM tests + OTEL span verification in Honeycomb.
- Read `trina-build.md` §2 (plugin pattern) and `agent_api_integration_pattern.md` before Sub-step 2.
- `plugins/gtd-tools/` directory does not exist yet — Sub-step 2 creates it.
