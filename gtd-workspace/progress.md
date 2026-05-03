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

### Review findings (Gate 2)

- 1 blocker (B-1: `_is_transient` missed httpx exception hierarchy — health cache never set in production; test was decorative using builtin `ConnectionError` instead of `httpx.ConnectError`)
- 2 majors (M-1: `OllamaLLMClient.complete()` missing `raise_for_status()` — Qwen 5xx silently broke chain; M-2: `DATA_ROOT` had `/tmp/gtd-missing` sentinel — replaced with `_require_env`)
- 3 minors (m-1: unused `TextMapPropagator` import; m-2: `creds.scopes=None` path untested; m-3: unreachable return after `_run_outer` loop)

**Post-review commit:** `770e7ae` — 37 Python tests (+7: `_is_transient` unit tests, Qwen 5xx chain test, `_require_env` tests, `creds.scopes=None` test).

M-1 RED confirmed: without `raise_for_status()`, mock 503 body (`{"error": "..."}`) causes `KeyError` → non-transient → chain dies. Fixed code: `httpx.HTTPStatusError` raised → transient → health cache set → Sonnet fallback.

**Gate 2:** GREEN — 2026-05-02

### Gate 3

- `make test-gtd`: 37/37 GREEN
- Import check: `from scripts.common import ...; from scripts.otel_common import ...; print('imports clean')` — GREEN (requires `GTD_STORAGE_ROOT` set; M-2 makes it required at import time)

**Gate 3:** GREEN — 2026-05-02

### Squash and merge

**Squash commit:** `ed9f892` — `1: shared helpers foundation` on `main`
Feature branch `feature/gtd-trina-substep-1-shared-helpers` deleted.

**KNOWN_ISSUES added:** OAuth user-flow doc pointer gap (low priority, sub-step 6).

---

## Sub-step 2 — Calendar Read

**Started:** 2026-05-02

**Branch:** `feature/sub-step-2-calendar-read`

**Pre-review commit:** `9e0e45b` — 57 Python tests, 0 LLM tests (no capability prompts this sub-step).

### Files delivered

| File | Purpose |
|---|---|
| `scripts/calendar/get_events.py` | `list_events` tool; Google Calendar events.list(); OTEL span `gtd.calendar.list_events` |
| `scripts/calendar/get_event.py` | `get_event` tool; events.get(); OTEL span `gtd.calendar.get_event` |
| `scripts/calendar/test_get_events.py` | 10 tests (happy path, empty, defaults, explicit args, OAuth fail, 4xx, 5xx retry, exhaustion, span attrs, invalid JSON) |
| `scripts/calendar/test_get_event.py` | 8 tests (same coverage + exhaustion) |
| `scripts/calendar/conftest.py` | sys.path injection for calendar subdirectory |
| `plugins/gtd-tools/index.js` | Plugin wiring; SCRIPTS points to `gtd-workspace/scripts/calendar/` |
| `plugins/gtd-tools/tool-schemas.js` | Two tool definitions (`list_events`, `get_event`) |
| `plugins/gtd-tools/tools.schema.json` | Generated artifact; committed alongside tool-schemas.js |
| `plugins/gtd-tools/package.json` | Plugin metadata with `build:schemas` script |
| `plugins/gtd-tools/openclaw.plugin.json` | Plugin id/name/description |
| `plugins/gtd-tools/scripts/emit-schemas.js` | Schema build script |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | Created; KI-001 through KI-009 |

### Key changes to sub-step 1 files

- `common.py`: `GOOGLE_OAUTH_CREDENTIALS` replaces `GOOGLE_OAUTH_TOKEN_PATH`; `GOOGLE_OAUTH_CLIENT_SECRETS_PATH` removed (setup-time only, not runtime).
- `otel_common.py`: `_is_transient_google` added; `BatchSpanProcessor` replaced with `SimpleSpanProcessor` for production — batch processor's 5s flush window outlives short-lived plugin scripts, causing spans to be silently dropped.
- `conftest.py`: `isolate_tracer_provider` autouse fixture added — prevents test spans from reaching real OTLP collector (Gate 3 finding).
- `test_common.py`: env var rename applied throughout; `test_missing_secrets_path_env_var` removed.
- `test_otel_common.py`: 4 `_is_transient_google` unit tests added.

### Review findings (Gate 2)

- 3 blockers (B-1: request built outside retry loop; B-2: exhaustion test missing execute call_count assertion; B-3: hardcoded .venv path in index.js), all fixed in-pass
- 1 observation promoted to in-pass (Obs-2: `span.record_exception` + `Status` for Honeycomb trace exploration)
- 6 non-blockers routed to KNOWN_ISSUES.md (KI-001 through KI-009)

**Post-review commit:** `bb4145a` — 58 Python tests (+1 exhaustion test for get_event).

**Gate 2:** GREEN — 2026-05-02

### Gate 3 — PARTIAL

OAuth, Google Calendar API, and plugin registration all work. Two infrastructure issues found and fixed during Gate 3:

1. **BatchSpanProcessor flush window** — spans silently dropped (script exits before 5s flush). Fixed: `SimpleSpanProcessor`.
2. **Plist missing env vars** — `GOOGLE_OAUTH_CREDENTIALS`, `GTD_TZ`, `OTEL_EXPORTER_OTLP_ENDPOINT` added manually. `OTEL_SERVICE_NAME` intentionally not added globally (scripts default to `"gtd"`).

**Gate 3 blocker:** `google-calendar` MCP server in `~/.openclaw/openclaw.json` intercepts calendar requests before our plugin tools are reached. Agent (even with Sonnet) has no SKILL.md instruction to prefer our tools over MCP. Real Honeycomb span from our scripts not confirmed.

**Gate 3 deferred to Sub-step 6** — unblocked when SKILL.md capability prompts are written with explicit dispatch rules. Full Gate 3 re-run required after Sub-step 6.

**Additional Gate 3 finding:** Test spans were contaminating Honeycomb — `otel_common.py` sets up real OTLP on import; tests without `_make_exporter()` emit real spans. Fixed by `isolate_tracer_provider` fixture.

### Squash and merge

**Squash commit:** `c16b5ed` — `sub-step-2: calendar read` on `main`
Feature branch `feature/sub-step-2-calendar-read` deleted.

**KNOWN_ISSUES added:** KI-001 through KI-009 (see `gtd-workspace/docs/KNOWN_ISSUES.md`).

### Notes for next session

- Sub-step 2b required before Sub-step 6: migrate 7 legacy `tools/*.py` to plugin pattern + OTEL + exec lockdown. See `trina-scope-2026-05-02-v1.md` for full scope.
- MCP server decision (D-1) needed before writing SKILL.md — keep or remove `google-calendar` MCP server.
- Model confirmed: `mnemo/claude-sonnet-4-6` on gtd agent in `~/.openclaw/openclaw.json`.
- Plist patched: `GOOGLE_OAUTH_CREDENTIALS`, `GTD_TZ`, `OTEL_EXPORTER_OTLP_ENDPOINT` in gateway env.
- Scope and planning document: `gtd-workspace/docs/trina-scope-2026-05-02-v1.md` — revised sub-step sequence, legacy tool inventory, Gate 3 findings, open decisions for supervisor.
