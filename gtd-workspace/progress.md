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

---

## Sub-step 2b.1 — Internal Modules (normalize, validate, write)

**Started:** 2026-05-02

**Branch:** `feature/sub-step-2b-api-surface` (single long-lived branch for all 2b phases)

**Pre-review commit:** `4afe92d` — 86 Python tests, 0 LLM tests.

### Files delivered

| File | Purpose |
|---|---|
| `scripts/gtd/normalize.py` | `normalize(raw_input) -> Classification`; intent classification + field extraction; OTEL child span |
| `scripts/gtd/validate.py` | `validate(record_type, record) -> ValidationResult`; full data contract enforcement; OTEL child span |
| `scripts/gtd/write.py` | `write(record, requesting_user_id) -> str`; stamps + validates + persists; raises GTDError; OTEL child span |
| `scripts/gtd/_tools_common.py` | Single canonical load of `tools/common.py`; pins to `sys.modules`; prevents enum double-load |
| `scripts/gtd/tests/conftest.py` | sys.path setup for gtd module imports; `storage` fixture |
| `scripts/gtd/tests/test_normalize.py` | 33 tests (25 ported behavioral + 6 typed contract/OTEL + 2 span tests) |
| `scripts/gtd/tests/test_validate.py` | 25 tests (20 ported + 3 typed contract/OTEL + 2 new) |
| `scripts/gtd/tests/test_write.py` | 19 tests (10 ported + 7 typed contract/OTEL + 2 new) |
| `scripts/gtd/tests/test__tools_common.py` | 3 tests for sys.modules registration and double-load protection |
| `scripts/common.py` | Added `GTDError(code, message, **fields)`; updated `err()` to Lock 5 envelope |
| `scripts/test_common.py` | 4 new tests for GTDError and err() envelope shape |
| `scripts/calendar/test_get_events.py` | 1-line fix: `out["error"]["message"]` for new err() envelope |
| `scripts/calendar/test_get_event.py` | Same 1-line fix |
| `Makefile` | `test-gtd-internal` target added |

### Key design decisions

**Lock 5 error envelope.** `{"ok": false, "error": {"code": "...", "message": "...", ...fields}}`. `err()` updated to accept `str | GTDError`; string callers get `code: "internal_error"` automatically. Calendar tool tests updated for the new shape.

**Internal modules, not plugin tools.** `normalize`, `validate`, `write` are Python function imports; not registered with the gateway; not LLM-visible. `capture.py` (2b.2) imports and orchestrates them.

**`_tools_common.py` canonical load.** `tools/common.py` loaded once via importlib; registered as `sys.modules["gtd._tools_common"]`. `validate.py` and `write.py` both import from `_tools_common`; enum class identity is preserved across both callers for normal import paths. Residual: raw `exec_module` calls bypass `sys.modules`; documented in `test__tools_common.py`; no production path uses raw exec_module.

**OTEL spans as children.** Internal modules use `tracer.start_as_current_span()` with no explicit context arg; OTel context propagation via Python contextvars makes them children of `capture.py`'s root span automatically when called inside it. Standalone (tests, CLI) they are root spans.

**`_task_rules` unconditional.** All three rule sets (`_validate_fields`, `_ownership_rules`, `_task_rules`) now run unconditionally; all violations on a multi-error record surface in a single pass.

### Gate 2 — Round 1 (2026-05-02)

Code reviewer: fresh context subagent.

- 2 blockers: B1 `append_jsonl` bare OSError unhandled; B2 unused `extract_parent_context` import
- 5 non-blockers: N1 OTEL ERROR status missing; N2 `_ownership_rules` conditional; N3 `object.__setattr__` in non-frozen dataclass; N4 `tools/common.py` double-loaded (distinct sys.modules names); N5 weak disjunctive test assertion; N6 taxonomy load no error message

All eight fixed. Post-review commit: `0fa3098` — 109 tests.

### Gate 2 — Round 2 (2026-05-02)

Code reviewer: fresh context subagent. Additional question: `_tools_common.py` mechanism and N4 residual risk.

- 2 blockers: B1 `_mod` not registered in `sys.modules` (routed around, not fixed); B2 `os.path` instead of Pathlib in validate/write
- 3 non-blockers: N1 `_task_rules` still gated on clean schema; N2 missing `__main__` blocks; N3 test 3 disjunction undocumented

All five fixed. Post-review commit: `41c73c3` — 112 tests.

**Process note:** no Gate 2 round 3; supervisor reviewed final diff directly per resolution memo.

### Gate 1 — Final

- **112 Python tests passing** (`make test-gtd-internal` + calendar suite)
- 0 LLM tests (no capability prompts in 2b.1; internal modules only)
- All Gate 2 findings resolved across two rounds

**Gate 1:** GREEN — 2026-05-02

### Gate 2 — Final

Cleared by supervisor diff review of commit `41c73c3`. No further subagent run.

**Gate 2:** GREEN — 2026-05-02

### Gate 3

Batched to end of 2b.4 per plan. No per-phase Gate 3.

### KNOWN_ISSUES added

None. All findings resolved in-pass.

### Notes for next session (2b.2)

- Error code `storage_io_failed` (B1 fix slug) is proposed; supervisor locks or renames before 2b.2 references it.
- 2b.2 scope: `capture.py` plugin entry point + `query_tasks.py`, `query_ideas.py`, `query_parking_lot.py`, `review.py`, `delegation.py` + `tool-schemas.js` wiring + OTEL spans per attribute table.
- `docs/` in this repo missing: `trina-handoff-2026-05-02-v4.md`, `sub-step-2b-api-surface-proposal-2026-05-02-v1.md`, `trina-build-amendment-2026-05-02-v1.md`. All three live in `~/Downloads/aCode-5-2/`. Commit or copy before starting 2b.2 so build agent can read them from the repo.

---

## Sub-step 2b.2 — Capability Tools

**Started:** 2026-05-03

**Branch:** `feature/sub-step-2b-api-surface` (continued from 2b.1)

**Squash commit:** `19cd92c` — 171 Python tests, 0 LLM tests.

### Files delivered

| File | Purpose |
|---|---|
| `scripts/gtd/capture.py` | `capture_gtd` plugin entry point; `_Input(record: dict)`; calls `write()`; OTEL root span `gtd.capture` |
| `scripts/gtd/query_tasks.py` | `query_tasks` plugin entry point; filters context/due_date/waiting_for/limit; Lock 6 envelope |
| `scripts/gtd/query_ideas.py` | `query_ideas` plugin entry point; limit only; Lock 6 envelope |
| `scripts/gtd/query_parking_lot.py` | `query_parking_lot` plugin entry point; limit only; Lock 6 envelope |
| `scripts/gtd/delegation.py` | `delegation` plugin entry point; groups by `waiting_for`; grouped envelope (documented exception to Lock 6) |
| `scripts/gtd/review.py` | `review_gtd` plugin entry point; scaffold only; `review_design_pending` note; design loop deferred |
| `scripts/gtd/migrate_to_simplified_shape.py` | Operator migration script; `--apply`/dry-run; dated backup; idempotent |
| `gtd-workspace/config/gtd.json` | `{"default_query_limit": 10, "max_query_limit": 25}`; operator-tunable |
| `scripts/common.py` | Added `GTDConfig` Pydantic model; `get_gtd_config()` loader; workspace-relative path |
| `scripts/gtd/validate.py` | Simplified to locked shapes (7/4/4 fields for task/idea/parking_lot); removed dropped rules and enums |
| `scripts/gtd/write.py` | Empty-guard replaces `assert_user_match`; no `user_id` or `updated_at` in storage |
| `scripts/gtd/_tools_common.py` | Added `read_jsonl` export; removed dead `assert_user_match` re-export (post-review) |
| `scripts/gtd/tests/test_capture.py` | 15 tests |
| `scripts/gtd/tests/test_query_tasks.py` | 16 tests (14 + 2 null due_date regression tests added post-review) |
| `scripts/gtd/tests/test_query_ideas.py` | 8 tests |
| `scripts/gtd/tests/test_query_parking_lot.py` | 8 tests |
| `scripts/gtd/tests/test_delegation.py` | 10 tests |
| `scripts/gtd/tests/test_review.py` | 5 tests |
| `scripts/gtd/tests/test_migrate_to_simplified_shape.py` | 8 tests (7 + 1 both-fields regression added post-review) |
| `scripts/gtd/tests/test_validate.py` | Scrubbed to 14 tests (was 25); 2 new due_date tests |
| `scripts/gtd/tests/test_write.py` | Scrubbed to 18 tests (was 19); fixtures updated to simplified shapes |
| `scripts/test_common.py` | +5 GTDConfig tests |
| `plugins/gtd-tools/tool-schemas.js` | 6 GTD tool entries added; calendar tools namespaced |
| `plugins/gtd-tools/index.js` | `SCRIPTS` base updated to `gtd-workspace/scripts/` |
| `plugins/gtd-tools/tools.schema.json` | Regenerated; 8 tools (2 calendar + 6 GTD) |
| `Makefile` | 5 new narrow test targets (`test-gtd-capture`, `test-gtd-queries`, etc.) |
| `scripts/gtd/normalize.py` | **Deleted** (D1 lock; LLM does classification natively) |
| `scripts/gtd/tests/test_normalize.py` | **Deleted** (-32 tests) |

### Key design decisions

**D2d — validate.py simplified to locked shapes.** Storage contract and LLM submission contract are now identical. No defaults injection at the capture layer. Fields supporting deferred features (status, priority, energy, updated_at, etc.) removed; return in 2d when update semantics land.

**Q2 — user_id not in stored records.** Directory scoping (`~/agent_data/gtd/{user_id}/...`) is the sole user boundary. No per-record user_id stamping.

**Q1 — empty-guard replaces isolation check.** `write()` raises `GTDError("internal_error", "OPENCLAW_USER_ID not set")` on empty `requesting_user_id`. `isolation_violation` exits the vocabulary for 2b.2; returns in 2d for cross-record identity checks.

**requesting_user_id from env.** All plugin entry points read `OPENCLAW_USER_ID` from env; no LLM-supplied user identity. Aligns with 2c identity model (deferred).

**delegation return shape.** `{groups, total_items, truncated}` — documented exception to Lock 6 standard query envelope. `limit` applies per group, not globally.

**review.py scaffold.** Work function returns `{review_available: false, note: "review_design_pending"}`. Capability prompt design loop deferred to Sub-step 6.

**query.status retired.** Status filter dropped from `query_tasks` (status not in simplified task shape); `query.status` OTEL attribute retired. Inline comment in source documents the decision.

### Gate 2 findings (Gate 2 — 2026-05-03)

Code reviewer: fresh context subagent.

- 1 blocker: B-1 `query.status` OTEL attribute missing from span (resolved as inline comment per supervisor; attribute retired)
- 4 non-blockers: N-1 dead `assert_user_match` re-export (fixed); N-2 null due_date filter behavior undocumented (fixed: docstring + 2 tests); N-3 OTEL exporter test fragility under autouse fixture (scoped to 2b.3); N-4 migrate_parking_lot no test for both-fields edge case (fixed: 1 test)
- 4 observations (no action required)

**Pre-review commit:** `e0745af` — 168 tests.
**Post-review commit:** `a316782` — 171 tests.
**Squash commit:** `19cd92c` — 171 tests.

### Gate 1

- **171 Python tests passing** (`make test-gtd`)
- 0 LLM tests (no capability prompts in 2b.2; plugin entry points only)

**Gate 1:** GREEN — 2026-05-03

### Gate 2

**Gate 2:** GREEN — 2026-05-03

### Gate 3

- Migration run: `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir python migrate_to_simplified_shape.py --user-id 8712103657 --apply`
- Result: 9 tasks + 1 idea migrated; backups at `.bak-2026-05-03`; parking-lot absent (skipped)
- Release smoke: PENDING operator

**Gate 3:** PENDING operator release smoke.

### KNOWN_ISSUES added

- N-3 (OTEL exporter test fragility): scoped to 2b.3.
- Operator runbook note: migration user-id is `8712103657` (Telegram chat ID), not `ranbir`.

### Notes for next session (2b.3)

- 2b.3 scope: exec lockdown (`tools.allow` / `tools.deny` on GTD agent), AGENTS.md edits, `isolate_tracer_provider` fixture design revisit (N-3 from this gate), `test-gtd` Makefile expansion if needed.
- Storage root confirmed: `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir`; verify in plist before Gate 3 smoke.
- Migration user-id: `8712103657`. The `--user-id ranbir` form is incorrect; `ranbir` is the storage root segment, not the user ID.
- `AGENT_ARCHITECTURE.md` updated to current version (`47635c1`) after squash.
- `docs/` still missing `trina-handoff-2026-05-02-v4.md`, `sub-step-2b-api-surface-proposal-2026-05-02-v1.md`, `trina-build-amendment-2026-05-02-v1.md`; supervisor to commit from `~/Downloads` before 2b.3 if build agent needs them.
- Start 2b.2 in a fresh session; this session is at context depth.

---

## Sub-step Z3 — Storage Contract Correction

**Started:** 2026-05-03
**Closed:** 2026-05-04

**Branch:** `feature/sub-step-2b-api-surface` — merged to main.

**Pre-review commit:** `0a9692a` — 192 Python tests, 0 LLM tests.
**Post-review commit:** `7ffbf83` — 194 Python tests (+2: B-2 parking_lot test, N-4 validate_storage assertion).
**Squash commit:** `f915b4e` — `Z3: storage contract split` on main.
**Migration scripts deleted:** `a048369`.

### Review triage (2026-05-04)

- B-1: dynamic `datetime.now(timezone.utc).isoformat()` in `test_review_stale_filter` — FIXED
- B-2: `_migrate_parking_lot` always emits `status="open"`; `test_migrate_z3_parking_lot_done_to_open` added — FIXED
- N-4: `test_migrate_z3_validate_storage_on_migrated_records` asserts all three record types pass `validate_storage` — FIXED
- O-2: misleading comment in `review.py` auto-stamp block — FIXED
- Deferred to 2b.3 cleanup: N-1, N-2, N-3, N-5, N-6, N-7
- Deferred to 2c/2d: O-5 (priority/context enum constraint)

### Gate 1 — FINAL

- **194 Python tests passing** (`make test-gtd`)
- 0 LLM tests (no capability prompts in Z3)

**Gate 1:** GREEN — 2026-05-03

### Gate 2

**Gate 2:** GREEN — 2026-05-04

### Gate 3

**Blocker:** agent attempted capture but called `message` only — never invoked `capture_gtd`. Forensic audit (`10997d89` session): 10 tool calls, all `message`; 0 forbidden, 0 GTD tool calls.

**Root cause:** no SKILL.md / capability prompt instructs the GTD agent to dispatch to plugin tools for specific intents. Agent falls back to conversational handling.

**Gate 3:** PENDING — unblocked after 2b.3 SKILL.md and exec lockdown.

### KNOWN_ISSUES added

- N-3 (OTEL exporter test fragility under autouse fixture): scoped to 2b.3.
- N-1, N-2, N-5, N-6, N-7: deferred to 2b.3 cleanup pass.

### Notes for next session (2b.3)

- **2b.3 primary deliverable:** `SKILL.md` for GTD agent with explicit dispatch rules (`capture this` → `capture_gtd`; `what are my tasks` → `query_tasks`; etc.) and `tools.allow`/`tools.deny` exec lockdown on GTD agent config.
- After SKILL.md: full Gate 3 re-run — capture via Telegram, verify 16 fields on disk, query back, confirm no channel field leaks in response.
- Deferred cleanup to bundle into 2b.3: N-1 (unused `os`/`stat` in test_review.py), N-2 (unused `os` in test_migrate_to_simplified_shape.py), N-3 (OTEL exporter test fragility), N-5 (sentinel encoding), N-6 (test name overclaims), N-7 (no OTEL span tests for validate_submission/validate_storage).
- Storage root confirmed: `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir`.
- Migration user-id: `8712103657` (Telegram chat ID).
- Plist env vars: `GTD_STORAGE_ROOT`, `OPENCLAW_USER_ID`, `GTD_TZ`, `OTEL_EXPORTER_OTLP_ENDPOINT` — verify all present before Gate 3 smoke.
- `.claude/settings.json` hook and permission paths corrected (vlc-openclaw → vlc-openclaw-gtd) in `7ffbf83`; takes effect on next session start.
