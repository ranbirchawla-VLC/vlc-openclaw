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

---

## Pre-build Audit — 2b.3 (2026-05-04)

**Session scope:** read-only audit pass before 2b.3 build. No feature branch opened; no code changed.

### Reference docs updated (repo root)

- `agent_api_integration_pattern.md` — updated from `~/Downloads/_aSkills/` (build-time mechanics, code skeletons, OTEL wrapping)
- `AGENT_ARCHITECTURE.md` — updated from `~/Downloads/_aSkills/` (locked patterns 1-10, reference layout, AGENTS.md skeleton)

### Audit reports produced

- `2b3-audit-2026-05-04.md` — plugin and integration state audit (8 gaps identified)
- `2b3-soul-identity-audit-2026-05-04.md` — verbatim content of all 8 workspace prompt files
- Both copied to `~/Downloads/`

### Branch cleanup

- `feature/sub-step-2b-api-surface` squashed and merged to main (`4cc1f58` on main after Z3 + progress.md closure).
- Feature branch requires force-delete: `git branch -D feature/sub-step-2b-api-surface` (blocked by settings deny list; operator runs directly in terminal).

### 8 gaps from 2b3-audit (build order for 2b.3)

1. **`tools.allow` missing GTD tools** — add `capture_gtd`, `query_tasks`, `query_ideas`, `query_parking_lot`, `review_gtd`, `delegation` to agent entry in `~/.openclaw/openclaw.json`. One JSON edit; gateway restart required.
2. **AGENTS.md is v1 legacy** — full replacement per AGENT_ARCHITECTURE skeleton: Hard Rules block, correct Tools Available list, exec/read/write/edit/browser prohibition, On Every Startup block (single-mode: SKILL.md already in context).
3. **SKILL.md not at workspace root** — `gtd-workspace/SKILL.md` does not exist; gateway never loads it. New file needed at workspace root.
4. **Mislocated SKILL.md content is v1** — `gtd-workspace/skills/gtd/SKILL.md` references `gtd_normalize`, `gtd_write`, `gtd_validate`, `gtd_review` (none exist). New SKILL.md at workspace root must reference current plugin tool names.
5. **`index.js` missing `startActiveSpan` + `TRACEPARENT` injection** — locked pattern 2 violation. Add tracer import, `startActiveSpan` per-tool, `TRACEPARENT` in `SPAWN_ENV`.
6. **`index.js` missing `SPAWN_ENV` constant** — replace `env: { ...process.env }` with module-level `SPAWN_ENV = { ...process.env, OTEL_SERVICE_NAME: PLUGIN_TRACER }`.
7. **`package.json` missing `@opentelemetry/api` dependency** — add `"dependencies": { "@opentelemetry/api": "^1.9.0" }`. Run `npm install` after.
8. **`auth-profiles.json` missing from `agentDir`** — `echo '{"version":1,"profiles":{}}' > ~/.openclaw/agents/gtd/agent/auth-profiles.json`.

### Surface state (verbatim from audit)

- Agent ID: `gtd` | Model: `mnemo/claude-sonnet-4-6` | Workspace: `gtd-workspace/`
- Plugin registered and on disk: `gtd-tools` at `plugins/gtd-tools/` — all 8 scripts present
- Live tool surface (last session): `message`, `list_events`, `get_event` only — 6 GTD tools absent
- SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md, BOOTSTRAP.md: present, injected, v1-era content but usable
- TOOLS.md: present, injected, references v1 tool names (`gtd_normalize.py` etc.) — needs update after AGENTS.md/SKILL.md
- AGENTS.md: present, injected, v1 legacy
- SKILL.md: mislocated at `skills/gtd/SKILL.md`, not loaded
- Telegram binding: present, bot token present, `allowFrom: ["8712103657"]`

### Notes for 2b.3 build session

- Start on a fresh branch: `git checkout -b feature/gtd-2b3-wiring`
- Highest-leverage single edit: add GTD tools to `tools.allow` in `openclaw.json` + restart gateway → unblocks Gate 3 smoke immediately
- AGENTS.md and SKILL.md are the capability instruction layer — write these before doing Gate 3 smoke
- TOOLS.md also needs update (references v1 tool names); bundle with AGENTS.md/SKILL.md rewrite
- OTEL gap in `index.js` (gaps 5-7): separate commit; requires `npm install` after `package.json` change
- `auth-profiles.json` (gap 8): one operator command; do before gateway restart
- Z3 cleanup deferred items (N-1, N-2, N-3, N-5, N-6, N-7): bundle into 2b.3 as a cleanup commit alongside the main wiring work
- Gate 3 re-run checklist (after all wiring done): capture task via Telegram → verify `capture_gtd` appears in session audit → verify 16 fields on disk → query back → confirm no channel field leaks

---

## Sub-step 2b.3 — Phase 1: OTEL Plumbing

**Started:** 2026-05-04
**Branch:** `feature/sub-step-2b3-capability-wiring`

**Pre-review commit:** `4f01fce` — 9/9 JS tests, 187/187 Python tests.
**Post-review commit:** `5d8e5e0` — blocker fixed (span.end() in finally); KI-011/012/013 added.

### Files delivered

| File | Change |
|---|---|
| `plugins/gtd-tools/package.json` | `@opentelemetry/api ^1.9.0` dep; `@opentelemetry/sdk-trace-base ^1.25.0` devDep; `test` script |
| `plugins/gtd-tools/otel-helpers.js` | New: SPAWN_ENV, PLUGIN_TRACER, activeTraceparent, toToolResult (error discipline), executeWithSpan (try/finally span.end) |
| `plugins/gtd-tools/index.js` | Retrofit: imports otel-helpers; TOOLS loop with executeWithSpan; spawnArgv/Stdin accept extraEnv |
| `plugins/gtd-tools/tests/test_index.js` | New: 9 JS unit tests (node:test + InMemorySpanExporter) |
| `gtd-workspace/scripts/otel_common.py` | `attach_parent_trace_context()` context manager added after `extract_parent_context` |
| `gtd-workspace/scripts/test_otel_common.py` | Tests 8-9 appended: attach and noop paths |
| `gtd-workspace/scripts/tests/test_otel_phase1_integration.py` | New: tests 10-11 (in-process cross-process trace ID and parent span ID propagation) |
| `gtd-workspace/scripts/gtd/capture.py` | `attach_parent_trace_context` import + `with attach_parent_trace_context():` in main() |
| `gtd-workspace/scripts/gtd/query_tasks.py` | Same |
| `gtd-workspace/scripts/gtd/query_ideas.py` | Same |
| `gtd-workspace/scripts/gtd/query_parking_lot.py` | Same |
| `gtd-workspace/scripts/gtd/review.py` | Same |
| `gtd-workspace/scripts/calendar/get_events.py` | Replace `extract_parent_context` pattern with `attach_parent_trace_context` in main(); remove `context=parent_ctx` from start_as_current_span |
| `gtd-workspace/scripts/calendar/get_event.py` | Same |
| `~/.openclaw/agents/gtd/agent/auth-profiles.json` | Created: `{"version":1,"profiles":{}}` (not in repo) |
| `.gitignore` | `node_modules/` added |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | KI-010 through KI-013 added |

### Gate 1

- 9/9 JS tests (node:test + @opentelemetry/sdk-trace-base InMemorySpanExporter)
- 187/187 Python tests (183 prior + 4 new: tests 8-11)
- RED confirmed for all 13 new tests before implementation
- Integration test harness: in-process (approach a) per operator-approved fallback

**Gate 1:** GREEN — 2026-05-04

### Gate 2

- 1 blocker: span.end() not in finally in executeWithSpan — fixed in post-review commit
- 3 non-blockers: KI-011 (test 8 assertion gap), KI-012 (narrow Makefile target), KI-013 (SPAWN_ENV snapshot inconsistency across plugins)
- 4 observations: no action required

**Gate 2:** GREEN — 2026-05-04

### Gate 3

Deferred to end of Phase 1+2+3 combined or after Phase 6 naming alignment; full Telegram round-trip requires turn_state dispatcher (Phase 2) to be in place.

### KNOWN_ISSUES added

KI-010 through KI-013 (see `gtd-workspace/docs/KNOWN_ISSUES.md`).

### Notes for next session (Phase 2)

Phase 2 is now IN PROGRESS. See Phase 2 entry below.

---

## Sub-step 2b.3 — Phase 2: turn_state Plugin and Dispatcher

**Started:** 2026-05-04
**Branch:** `feature/sub-step-2b3-capability-wiring`

**Pre-review commit:** `aae91d7` — 206 Python + 27/27 LLM (9 fixtures x 3x) + 9 JS.
**Post-review commit:** `25f7c1c` — 207 Python + 27/27 LLM + 9 JS.
**Tool rename commit:** `faa2ed1` — `turn_state` → `trina_dispatch` (collision with grailzee-eval-tools plugin).

### Files delivered

| File | Change |
|---|---|
| `gtd-workspace/scripts/turn_state.py` | New: three-layer classifier, inner LLM fallback, capability file read, 7 span attrs, 4 error codes |
| `gtd-workspace/scripts/tests/test_turn_state.py` | New: 19 Python unit tests |
| `gtd-workspace/scripts/tests/llm/conftest.py` | New: API key fixture, GTD_CAPABILITIES_DIR, isolate_tracer_provider |
| `gtd-workspace/scripts/tests/llm/run_llm_3x.py` | New: 3x require-all-pass harness |
| `gtd-workspace/scripts/tests/llm/test_turn_state_llm.py` | New: 9 LLM fixtures |
| `gtd-workspace/scripts/tests/llm/fixtures/capabilities/` | New: 7 one-line stub .md files |
| `plugins/gtd-tools/tool-schemas.js` | turn_state added as first entry (_spawn: stdin, user_message param) |
| `plugins/gtd-tools/tools.schema.json` | Regenerated (9 tools) |
| `Makefile` | test-gtd-turn-state, test-gtd-llm targets; test-gtd adds -m "not llm" |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | KI-014 added (capability_dispatched canon drift) |
| `gtd-workspace/docs/sub-step-2b3/` | 11 design docs landed (handoff, classifier-spec, target-arch, negative-path, latency-playbook, turn_state-arch + 5 previously present) |

### Gate 1

- 206 Python passed (187 prior + 19 new); 9 deselected (LLM excluded from test-gtd)
- 27/27 LLM (9 fixtures x 3 runs, temp=0, zero flakes)
- 9/9 JS (unchanged)
- RED confirmed before implementation for all 19 Python tests and all 9 LLM tests

**Gate 1:** GREEN — 2026-05-04

### Gate 2 findings (5 blockers, 7 non-blockers)

**Blockers — all must be fixed in post-review commit:**

- B-1: `turn_state.py:main()` — `ok()` never called; success path produces no stdout; plugin maps to subprocess_nonzero_exit error; tool completely non-functional in production
- B-2: `test_turn_state.py` — no test exercises `main()` CLI entry point; missing `ok()` call passes all 19 tests undetected; add one stdin/stdout round-trip test
- B-3: `turn_state.py:54-57` — module-level `_CAPABILITIES_DIR` is dead code; never referenced; `compute_turn_state()` re-reads env at call time; remove constant; fix test docstrings
- B-4: `turn_state.py:196-217` — retry loop applies to parse failures at temp=0; deterministic at temp=0, retrying wastes 3 API calls + 3s sleep per incident; split except clauses: raise immediately on parse failure, retry only on SDK/network exceptions
- B-5: `test_turn_state_llm.py:test_llm_continuity_turn_valid_result` — claims to assert `continuity_turn=True` on span but never does; dead io/patch imports; add InMemorySpanExporter and assert the attribute

**Non-blockers — route to KNOWN_ISSUES.md:**

- N-1 (P2): conftest `_resolve_api_key()` skips env check; silently skips LLM tests in CI with ANTHROPIC_API_KEY in env but no openclaw.json
- N-2 (P2): `\bevents?\b` and `\bschedule\b` in calendar_read signals too broad; "can we schedule a call" dispatches to calendar_read
- N-3 (P2): `\bi need to\b` in capture signals fires before review; "I need to do my weekly review" routes to capture
- N-4 (P3): `_load_api_key()` duplicated from otel_common.py
- N-5 (P3): test 19 is subset of test 14; no distinct behavior
- N-6 (P3): tests 7-8 assert only intent, not capability_prompt; wrong file could be served silently
- N-7 (P3): conftest module docstring incorrect re: API key resolution order

**Gate 2:** GREEN — 2026-05-05

### Gate 3

Session `db423255`. Tool timeline:
- `trina_dispatch` called first — correct dispatcher, grailzee collision resolved
- Returns `capability_file_missing` — expected; capabilities dir is Phase 3 deliverable
- 0 forbidden calls; 0 exec bypasses

**Gate 3 finding:** `grailzee-eval-tools` plugin also registers a tool named `turn_state` and loads before `gtd-tools` in `plugins.load.paths`. GTD agent was calling grailzee's classifier, which returns `intent: "default"` for all GTD messages. Fixed by renaming GTD's dispatcher to `trina_dispatch` (`faa2ed1`). `tools.allow` in `~/.openclaw/openclaw.json` updated via operator patch script.

**Gate 3:** GREEN (dispatch layer) — 2026-05-05

Full end-to-end pass (capture + query round-trip) deferred to Phase 3 gate after capability files are written.

### Notes for next session (Phase 3)

- Phase 3 deliverable: write `gtd-workspace/capabilities/` with 7 `.md` files: `capture.md`, `query_tasks.md`, `query_ideas.md`, `query_parking_lot.md`, `review.md`, `calendar_read.md`, `unknown.md`
- `capture.md` must include the full task/idea/parking_lot schema; agent must be told to populate `source` and `telegram_chat_id` from conversation metadata (sender_id = Telegram chat ID, source = "telegram")
- Rewrite `AGENTS.md` per AGENT_ARCHITECTURE.md skeleton: correct tools list (trina_dispatch + 8 others + message), Hard Rules block, On Every Startup = read SKILL.md only
- Write `gtd-workspace/SKILL.md` at workspace root (current file is mislocated at `skills/gtd/SKILL.md` and references v1 tool names)
- Update `TOOLS.md` to reference current plugin tool names
- Gate 3 full pass: capture via Telegram → 16 fields on disk → query back → no channel field leaks
- Branch: `feature/sub-step-2b3-capability-wiring`; commits ahead of main: `aae91d7`, `25f7c1c`, `faa2ed1`

---

## Sub-step 2b.3 — Phase 3: Dispatcher Naming + Surface Alignment + Gate 3 Production Fixes

**Started:** 2026-05-05
**Branch:** `feature/sub-step-2b3-capability-wiring`

**Squash commit:** `afb65de` — 209 Python + 27/27 LLM + 9 JS.

### Files delivered

| File | Change |
|---|---|
| `AGENT_ARCHITECTURE.md` | Replaced stale 760-line verbose version with compact `_aSkills` version (LOCKED PATTERNS 1-10). Pattern 1 rewritten: dispatcher name is per-agent unique; convention `<agent>_dispatch`; collision risk in flat plugin namespace documented; Trina as canonical reference; grailzee-eval flagged as legacy (KI-018). |
| `gtd-workspace/AGENTS.md` | Full rewrite from v1 legacy to architecture skeleton. PREFLIGHT block added citing `trina_dispatch`. Tools Available: 9 registered plugin tools + `message`. Identity line preserved verbatim from v1. |
| `gtd-workspace/TOOLS.md` | Replaced v1 Python tool table and stale LLM Skills section with live 9-tool plugin surface. Paths block corrected. `capture_gtd` return shape corrected (post-review: `{captured: {...}}` not `{id, record_type}`). |
| `gtd-workspace/scripts/gtd/tests/test_capture_user_pathing.py` | New: Pattern 7 characterization test; group-chat scenario (alpha + beta in same chat → separate per-user directories; chat ID never appears as directory component). |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | KI-018 through KI-027 added: Pattern 1 naming crystallization, handoff path drift, handoff envelope claim drift, GTD_STORAGE_ROOT vs DATA_ROOT divergence, path segment divergence from Pattern 7, dual test tree gap, bounded-autonomy enforcement gap, Gate 2 N-1/N-2/N-3. |
| `plugins/gtd-tools/tool-schemas.js` | `capture_gtd` description corrected to actual return shape. `user_id` added as required parameter to all 6 GTD tools. Schema regenerated. |
| `plugins/gtd-tools/tools.schema.json` | Regenerated (twice: once for description fix, once for user_id parameter). |
| `plugins/gtd-tools/otel-helpers.js` | SPAWN_ENV changed from module-load-time `process.env` snapshot to static OTEL overrides only. `process.env` now spread at call time in spawnArgv/spawnStdin. |
| `plugins/gtd-tools/index.js` | `spawnArgv` and `spawnStdin` updated: `{ ...process.env, ...SPAWN_ENV, ...extraEnv }` — live process.env at call time picks up gateway per-request injections. |
| `gtd-workspace/scripts/gtd/capture.py` | `_Input` gains `user_id: str`. `main()` reads from `inp.user_id`. `source` hardcoded `"telegram"`. `telegram_chat_id = inp.user_id` (DM pattern). |
| `gtd-workspace/scripts/gtd/query_tasks.py` | `_Input` gains `user_id: str`. `main()` reads from `inp.user_id`. |
| `gtd-workspace/scripts/gtd/query_ideas.py` | Same. |
| `gtd-workspace/scripts/gtd/query_parking_lot.py` | Same. |
| `gtd-workspace/scripts/gtd/review.py` | Same. |
| `gtd-workspace/scripts/gtd/delegation.py` | Same. |
| `gtd-workspace/scripts/gtd/tests/test_capture.py` | `test_capture_persists_channel_fields` updated: env monkeypatching removed; `user_id` in args JSON; assertions updated for hardcoded source and user-derived chat_id. |
| `gtd-workspace/scripts/gtd/tests/test_capture_user_pathing.py` | Updated: `_args_json` includes `user_id`; `_invoke` drops OPENCLAW_ env vars; `telegram_chat_id` assertion updated to match user_id. |

### Gate 1

- 209/209 Python (unchanged count; all tests green after each change)
- 27/27 LLM (9 fixtures × 3 runs, temp=0, zero flakes)
- 9/9 JS (all green after SPAWN_ENV fix)

**Gate 1:** GREEN — 2026-05-05

### Gate 2 findings (1 blocker, 3 non-blockers, 3 observations)

- B-1: `capture_gtd` return shape wrong in TOOLS.md and tool-schemas.js (`{id, record_type}` described; actual is `{captured: {...}}`). Fixed.
- N-1 (P2, KI-025): Pattern 7 mismatch in TOOLS.md without flagging deviation.
- N-2 (P3, KI-026): TOOLS.md Paths block omits default storage_root fallback.
- N-3 (P3, KI-027): test_capture_user_pathing.py missing record_type absence assertion.

**Gate 2:** GREEN — 2026-05-05

### Gate 3 production fixes

Three issues found and fixed during smoke testing:

1. **SPAWN_ENV snapshot** — `otel-helpers.js` captured `process.env` at module load time. Gateway per-request env injections (OPENCLAW_USER_ID etc.) never reached subprocesses. Fixed: `process.env` spread at call time.

2. **User identity mechanism** — Gateway passes sender context as conversation metadata (JSON block in user message), NOT as `process.env.OPENCLAW_USER_ID`. All 6 GTD tool scripts were reading from env (always empty). Fixed: `user_id` as explicit tool parameter; LLM reads `sender_id` from message metadata and passes it. Matches nutriosv2 pattern.

3. **Gate 3 result** — Session `fa207e8d`: `capture_gtd` returned `{ok: true, data: {captured: {...}}}` with `user_id: "8712103657"` correctly threaded from Telegram → LLM → tool parameter → storage path. 0 forbidden calls, 0 exec bypasses.

**Gate 3:** PARTIAL — dispatch layer (capture) cleared 2026-05-05. `trina_dispatch` still returns `capability_file_missing`; capabilities directory is Phase 3 remaining deliverable.

### KNOWN_ISSUES added

KI-018 through KI-027 (see `gtd-workspace/docs/KNOWN_ISSUES.md`).

### Notes for next session (Phase 3 continued — capability files)

- Write `gtd-workspace/capabilities/` — 7 files: `capture.md`, `query_tasks.md`, `query_ideas.md`, `query_parking_lot.md`, `review.md`, `calendar_read.md`, `unknown.md`
- `capture.md`: schema per type (task/idea/parking_lot); instruct LLM to read `sender_id` from conversation metadata and pass as `user_id`; `source` is always `"telegram"` (hardcoded in capture.py)
- Write `gtd-workspace/SKILL.md` at workspace root (current at `skills/gtd/SKILL.md` references v1 tool names)
- Gate 3 full pass: capture via Telegram → `trina_dispatch` returns capability_prompt → `capture_gtd` called with user_id → record on disk → query back
- Branch: `feature/sub-step-2b3-capability-wiring`; squash commit: `afb65de`

---

## Sub-step 2b.3 — Phase 3b: get_today_date plugin tool

**Started:** 2026-05-05
**Branch:** `feature/sub-step-2b3-capability-wiring`
**Status:** Gate 1 GREEN — awaiting Gate 2 (code-reviewer subagent)

### Files delivered

| File | Change |
|---|---|
| `gtd-workspace/scripts/get_today_date.py` | New: `run_get_today_date(tz_str=None)` pure computation; `main()` with OTEL span `gtd.get_today_date`; reads `GTD_TZ` from `common.TZ`; error code `invalid_timezone` on bad tz string |
| `gtd-workspace/scripts/tests/test_get_today_date.py` | New: 7 tests (shape, ISO format, Denver midnight boundary, explicit tz_str override, invalid timezone GTDError, span emission with tz attribute, main() CLI round-trip) |
| `plugins/gtd-tools/tool-schemas.js` | `get_today_date` entry added after `trina_dispatch`; `_spawn: "argv"`; no parameters |
| `plugins/gtd-tools/tools.schema.json` | Regenerated; 10 tools |
| `Makefile` | `test-gtd-get-today-date` target added; added to `.PHONY` |

### Design decisions

- `run_get_today_date(tz_str=None)` accepts explicit tz for testability; defaults to `common.TZ` (`GTD_TZ` env var, fallback `America/Denver`).
- OTEL span in `main()` only; `run_get_today_date` is pure. Success attr: `tz`. Error attrs: full error span discipline per Layer 3.3.
- `_spawn: "argv"` — no parameters; consistent with nutriosv2 reference registration.
- Phase 7 extension (per-user profile timezone) noted in module docstring; deferred.

### Gate 1

- 7/7 new tests GREEN (`make test-gtd-get-today-date`)
- 216/216 Python full suite GREEN (`make test-gtd`); no regressions
- RED confirmed before implementation: `ModuleNotFoundError: No module named 'get_today_date'`

**Gate 1:** GREEN — 2026-05-05

### Operator step (after Gate 2)

Add `get_today_date` to `tools.allow` for the GTD agent in `~/.openclaw/openclaw.json` and restart gateway.

### Notes for next session (capability files)

Session-open reading order:
1. `gtd-workspace/progress.md` (this file)
2. `gtd-workspace/docs/sub-step-2b3/2b3-handoff-2026-05-04-v3.md` (latest handoff; v4 does not exist)
3. `gtd-workspace/docs/sub-step-2b3/2b3-soul-anchor-2026-05-04-v2.md`
4. `gtd-workspace/docs/sub-step-2b3/2b3-capability-shape-2026-05-04-v1.md` (per-capability sketches)
5. `gtd-workspace/docs/sub-step-2b3/2b3-negative-path-2026-05-04-v2.md`
6. `gtd-workspace/docs/sub-step-2b3/2b3-outcomes-lock-2026-05-04-v1.md`
7. `gtd-workspace/docs/sub-step-2b3/2b3-decision-reasoning-2026-05-04-v1.md`

Capability authoring prerequisites confirmed complete:
- `trina_dispatch` — registered and live
- `get_today_date` — script + tests + registration done; operator tools.allow step pending
- AGENTS.md, TOOLS.md — rewritten to current surface
- capture_gtd user_id wiring — confirmed live (Gate 3 session fa207e8d)

Remaining scope for Phase 3:
- 7 capability files at `gtd-workspace/capabilities/`
- `gtd-workspace/SKILL.md` at workspace root
- Phase 6 renames: `capture_gtd` → `capture`, `review_gtd` → `review`, remove `delegation`
- Read query/review Python scripts before authoring query/review capability files (exact field names for verbatim render rule)
- Full Gate 3 sweep after capabilities land

---

## Sub-step 2b.3 — Phase 6: Tool Renames + Surface Alignment

**Commit:** `2228447`
**Branch:** `feature/sub-step-2b3-capability-wiring`

- `capture_gtd` → `capture` in `tool-schemas.js`, `tools.schema.json`, `AGENTS.md`, `TOOLS.md`
- `review_gtd` → `review` — same files
- `delegation` entry removed from `tool-schemas.js`; `delegation.py` and `test_delegation.py` deleted
- `tools.schema.json` regenerated (10 tools → 9 tools)
- **make test-gtd:** 206 passed, 9 deselected

---

## Sub-step 2b.3 — Phase 4-5: Capability Files + SKILL.md

**Commits:** `2a83654` (Phase 4-5), `ae4dcb0` (post-review)
**Branch:** `feature/sub-step-2b3-capability-wiring`

### Files delivered

| File | Change |
|---|---|
| `gtd-workspace/capabilities/capture.md` | New: 8-section capability; submission contracts; branch B/C prose; D-3 drift correction (actual error codes) |
| `gtd-workspace/capabilities/query_tasks.md` | New: 13-field VRR; overdue get_today_date wiring; 3 branches |
| `gtd-workspace/capabilities/query_ideas.md` | New: 9-field VRR; Branch C filter-unavailable handling |
| `gtd-workspace/capabilities/query_parking_lot.md` | New: 8-field VRR; Branch C completed-status unavailable |
| `gtd-workspace/capabilities/review.md` | New: actual return shape (`by_type`); D-2 drift correction inline |
| `gtd-workspace/capabilities/calendar_read.md` | New: decision-helping/decision-making table; conflict definition; tight-stretch qualitative rule |
| `gtd-workspace/capabilities/unknown.md` | New: 4 branches; 6 hard prohibitions verbatim; discovery surface allowed/not-allowed |
| `gtd-workspace/SKILL.md` | New: dispatch rule; capabilities index; empty-prompt fallback (no enumeration) |
| `gtd-workspace/skills/gtd/SKILL.md` | Deleted (v1; mislocated; never loaded) |
| `gtd-workspace/AGENTS.md` | PREFLIGHT fallback updated to match SKILL.md; all em-dashes removed (9 pre-existing) |
| `gtd-workspace/TOOLS.md` | Date Utility section added; review row corrected; 2 em-dashes removed |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | KI-028 added (guardrail outcomes citations missing, P3) |
| `plugins/gtd-tools/tool-schemas.js` | `review` entry: D-1 `limit` → `limit_per_type`; expose `record_types`, `stale_for_days`; D-2 description rewrite |
| `gtd-workspace/scripts/gtd/capture.py` | D-4: `tool.name` span attribute `capture_gtd` → `capture` |
| `gtd-workspace/scripts/gtd/review.py` | D-4: `tool.name` span attribute `review_gtd` → `review` |
| `gtd-workspace/scripts/gtd/tests/test_review.py` | D-4: assertion updated to match |

### Gate 1

- **209 Python tests passing** (`make test-gtd`)
- 9 deselected (LLM)

**Gate 1:** GREEN — 2026-05-05

### Gate 2

Code-reviewer subagent findings:
- 1 blocker: AGENTS.md PREFLIGHT fallback contradicted SKILL.md (fixed in `ae4dcb0`)
- 3 non-blockers: get_today_date separator (P3); review.md VRR path shorthand (fixed); guardrail outcome citations missing → KI-028

**Gate 2:** GREEN — 2026-05-05

### Gate 3

Session `6fd93d6b`: `trina_dispatch` → `capture` pipeline live. Task "Call Chris Westerhold" captured ok:true; confirmed on disk. Two bugs found and fixed:

1. **AGENTS.md PREFLIGHT fallback** contradicted SKILL.md (`ae4dcb0`).
2. **Storage root misdirection** — writes went to wrong path (`gtd/ranbir`) due to `GTD_STORAGE_ROOT` plist env var being passed through subprocess env and overriding `tools/common.py`'s default. See Storage Root Fix section below.

**Verbatim Render Rule violation noted:** Trina composed capture confirmation from user input with em-dash rather than rendering from `data.captured`. Pipeline works; voice is wrong. LLM test gap; deferred to capability test session.

**`get_today_date` tool name conflict:** `nutriosv2-tools` plugin also registers `get_today_date`; logged as "plugin tool name conflict" at gateway startup. Tool still callable by GTD agent (allow-listed); conflict resolution unclear. Recommend rename to `gtd_get_today_date` before next production sweep.

**Gate 3:** PARTIAL — dispatch + capture + storage path now verified correct.

---

## Storage Root Config Fix

**Commit:** (today's commit, this session)
**Branch:** `feature/sub-step-2b3-capability-wiring`

### Root cause

`tools/common.py`'s `storage_root()` read `GTD_STORAGE_ROOT` env var and fell back to `gtd-workspace/storage/` (legacy default). The plist had `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir` which flowed through `{ ...process.env, ...SPAWN_ENV }` into every Python subprocess. When the plist entry was removed, the fallback was `gtd-workspace/storage/`, not the production path. The real data (`~/agent_data/gtd-agent/users/8712103657/`) was never reached by the new pipeline.

### Fix

`gtd-workspace/config/gtd.json` gains `storage_root: /Users/ranbirchawla/agent_data`. Both `tools/common.py` (write layer) and `scripts/common.py` (constants layer) now check the config file when `GTD_STORAGE_ROOT` is unset. Config file takes precedence after env var. Legacy default (`gtd-workspace/storage/`) is last resort only.

`~/Library/LaunchAgents/ai.openclaw.gateway.plist`: `GTD_STORAGE_ROOT` entry removed entirely.

### Files changed

| File | Change |
|---|---|
| `gtd-workspace/config/gtd.json` | `storage_root: /Users/ranbirchawla/agent_data` added |
| `gtd-workspace/tools/common.py` | `storage_root()` reads config file before legacy default |
| `gtd-workspace/scripts/common.py` | `_resolve_data_root()` added; `DATA_ROOT` uses config file fallback |
| `gtd-workspace/scripts/test_common.py` | 3 new tests for `_resolve_data_root()` (env precedence, config fallback, neither-set error) |
| `gtd-workspace/scripts/patch_openclaw_tools_allow.py` | New operator script: patches GTD agent `tools.allow` in `~/.openclaw/openclaw.json` |
| `Makefile` | `test-gtd-get-today-date` target (Phase 3b carry) |

### Gate 1

- **209 Python tests passing** (`make test-gtd`); no regressions

**Gate 1:** GREEN — 2026-05-05

### Verified

Probe write with `GTD_STORAGE_ROOT` unset → record landed at `~/agent_data/gtd-agent/users/8712103657/tasks.jsonl`. Live Telegram capture ("Call Mom") confirmed in same file immediately after gateway restart.

**Gate 3 (storage path):** GREEN — 2026-05-05

### KNOWN_ISSUES

- `get_today_date` tool name conflict with `nutriosv2-tools`. Does not block current operation but may cause wrong tool to be called in edge cases. **Fix is the shared-tools plugin build below.**
- Test probe record (`95f2b085 - test probe write 2`) in production tasks.jsonl; operator marking done in morning.
- `gtd-workspace/storage/` directory may contain stale probe records from this debug session; safe to delete entire directory.

---

## Sub-step 2b.3 — Phase 7: shared-tools plugin (get_today_date consolidation)

**Started:** 2026-05-06
**Branch:** `feature/sub-step-2b3-capability-wiring` (same branch; do not create a new branch)

**Plan doc:** `gtd-workspace/docs/sub-step-2b3/2b3-shared-tools-plan-2026-05-06.md`

### Files delivered

#### Created outside repo

| Path | Description |
|------|-------------|
| `~/.openclaw/workspace/scripts/shared/get_today_date.py` | Self-contained; inline OTEL; reads GTD_TZ from env; `_configure_tracer()` for test injection; zero workspace imports; span `gtd.get_today_date` with `tz` attribute |
| `~/.openclaw/workspace/plugins/shared-tools/agent-settings.json` | Agent ID to `{agent_data_path, default_timezone}` map; operator-managed; read at plugin module load. gateway schema rejects `settings` on agent entries; mapping lives here instead |
| `~/.openclaw/workspace/plugins/shared-tools/package.json` | `@opentelemetry/api ^1.9.0` dep; `@opentelemetry/sdk-trace-base ^1.25.0` devDep |
| `~/.openclaw/workspace/plugins/shared-tools/openclaw.plugin.json` | `id: shared-tools`; `configSchema: {}` required by gateway schema validator |
| `~/.openclaw/workspace/plugins/shared-tools/tool-schemas.js` | Single `get_today_date` entry; optional `user_id` parameter |
| `~/.openclaw/workspace/plugins/shared-tools/tools.schema.json` | Manually generated |
| `~/.openclaw/workspace/plugins/shared-tools/otel-helpers.js` | `PLUGIN_TRACER="shared-tools"`; `resolveTZ()` exported pure function; `executeWithSpan()` accepts `extraAttrs`; span `shared-tools.tool.<toolName>` |
| `~/.openclaw/workspace/plugins/shared-tools/index.js` | Factory pattern: `api.registerTool((ctx) => ({...}))` — `ctx.agentId` identifies calling agent at execute time; injects `GTD_TZ` + `agent_id` span attr |
| `~/.openclaw/workspace/plugins/shared-tools/tests/test_index.js` | 9 JS tests (resolveTZ 4 cases, executeWithSpan extraAttrs, GTD_TZ injection, span name, SPAWN_ENV, TRACEPARENT) |

#### Modified outside repo

| Path | Change |
|------|--------|
| `~/.openclaw/workspace/plugins/nutriosv2-tools/tool-schemas.js` | `get_today_date` entry removed |
| `~/.openclaw/workspace/plugins/nutriosv2-tools/tools.schema.json` | `get_today_date` entry removed |
| `~/.openclaw/openclaw.json` | `shared-tools` first in `plugins.load.paths`; `shared-tools` in `plugins.entries` + `plugins.installs` |
| `~/Library/LaunchAgents/ai.openclaw.gateway.plist` | `OPENCLAW_PYTHON_BIN=/Users/ranbirchawla/ai-code/vlc-openclaw-gtd/.venv/bin/python` added; fixes `ModuleNotFoundError: opentelemetry` when shared script spawned via system python3 |

#### Modified in repo

| Path | Change |
|------|--------|
| `plugins/gtd-tools/tool-schemas.js` | `get_today_date` entry removed |
| `plugins/gtd-tools/tools.schema.json` | `get_today_date` entry removed |
| `plugins/nutriosv2-tools/tool-schemas.js` | `get_today_date` entry removed (post-review B-1 fix) |
| `plugins/nutriosv2-tools/tools.schema.json` | `get_today_date` entry removed (post-review B-1 fix) |
| `gtd-workspace/scripts/get_today_date.py` | **Deleted** (dead code; superseded by shared-tools) |
| `gtd-workspace/scripts/tests/test_get_today_date.py` | **Deleted** (imported deleted script) |
| `gtd-workspace/scripts/tests/test_shared_get_today_date.py` | New: 3 Python tests (GTD_TZ honored, fallback, span tz attr) |
| `Makefile` | `test-gtd-shared-get-today-date` added; `test-gtd-get-today-date` removed; `.PHONY` updated |
| `gtd-workspace/AGENTS.md` | `get_today_date` description notes shared-tools plugin |
| `gtd-workspace/TOOLS.md` | Date Utility updated: user_id param, shared-tools registration noted |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | KI-029 added (conftest sys.path fragility) |

### Key design deviations from plan

1. **`agents.list.N.settings` rejected by gateway schema.** Plan put `agent_data_path` + `default_timezone` on agent entries in `openclaw.json`. Gateway validator rejected unknown keys. Pivoted to `agent-settings.json` in plugin directory; `index.js` reads it at module load.

2. **`OPENCLAW_AGENT_ID` does not exist.** Plan assumed gateway injected this env var. Exhaustive grep of gateway dist confirmed it is never set. Gateway source revealed the factory pattern: `api.registerTool((ctx) => toolObject)` receives `ctx.agentId` = session-resolved agent ID (parsed from session key format `agent:<agentId>:<rest>`). `index.js` updated to factory pattern; `agent_id` added as span attribute.

3. **`OPENCLAW_PYTHON_BIN` not set; system python3 lacks opentelemetry.** Shared script spawned by the gateway process uses system python3 (`/opt/homebrew/bin/python3`) which has no opentelemetry packages. Added `OPENCLAW_PYTHON_BIN` to plist pointing to the GTD venv. All plugins in this gateway use the same Python.

### Gate 1

- **205/205 Python tests** (`make test-gtd`; 212 initial − 7 from deleted test file)
- **9/9 JS tests** (`node --test tests/` in `~/.openclaw/workspace/plugins/shared-tools/`)

**Gate 1:** GREEN — 2026-05-06

### Gate 2

Code-reviewer subagent run twice (initial build + factory pattern change).

**B-1 (FIXED):** `plugins/nutriosv2-tools/` repo copy still registered `get_today_date`. Removed from both `tool-schemas.js` and `tools.schema.json`.

**B-2 (WAIVED):** `tools.allow` cross-plugin resolution concern. Allow-list is name-based and resolved globally across all loaded plugins; confirmed by gateway source.

**B-3 (FIXED):** Superseded `get_today_date.py` retained as dead code. Deleted per CLAUDE.md; test file deleted with it.

**N-1 (open, P2):** Factory registration path not directly tested. `ctx.agentId` → `_AGENT_SETTINGS` lookup exercised only by Gate 3, not by unit tests.

**Gate 2:** GREEN — 2026-05-06

### Gate 3

**Session `a59f7a84` (2026-05-06, first post-restart smoke):**
- `trina_dispatch` → `capture` intent — correct
- `get_today_date` called with `user_id: "8712103657"` — **dispatch and user_id wiring correct**
- `get_today_date` returned `ok: false` — `ModuleNotFoundError: No module named 'opentelemetry'` — system python3 used; no otel packages
- Agent fell back to conversation metadata timestamp; `capture` succeeded
- **Root cause fixed:** `OPENCLAW_PYTHON_BIN` added to plist; gateway restarted

**Gate 3:** PENDING — one more smoke test required to confirm `get_today_date` returns `ok: true` with correct `tz`, `tz_source`, `agent_id` span attributes.

### KNOWN_ISSUES added

KI-029 (conftest sys.path fragility)

### Notes for next session

**Gate 3 completion (top priority):**
- Send a capture to Trina that uses "today" (e.g. "add X due today")
- Confirm `get_today_date` returns `ok: true` in session audit
- In Honeycomb, confirm span `shared-tools.tool.get_today_date` with `agent_id: "gtd"`, `tz: "America/Denver"`, `tz_source: "fallback"`

**After Gate 3 GREEN:**
- Squash branch and merge to main (final 2b.3 close-out)
- Branch: `feature/sub-step-2b3-capability-wiring`
- Next sub-step: 2c (identity model) or 2d (update semantics); see `gtd-workspace/docs/trina-scope-2026-05-02-v1.md`

**System state as of session close:**
- Gateway: running with `OPENCLAW_PYTHON_BIN` set; `shared-tools` loaded first in plugin chain
- `get_today_date` registered in `shared-tools` only; removed from `gtd-tools` and `nutriosv2-tools`
- `index.js` uses `(ctx) => ({...})` factory; `ctx.agentId` identifies calling agent
- `agent-settings.json` keys: `"gtd"` → `gtd-agent/users`, `"nutriosv2"` → `agent_data/nutriosv2`
- Plist: `OPENCLAW_PYTHON_BIN=/Users/ranbirchawla/ai-code/vlc-openclaw-gtd/.venv/bin/python`
- Test suite: 205 Python GREEN, 9 JS GREEN
