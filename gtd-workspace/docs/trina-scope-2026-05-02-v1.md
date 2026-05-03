# Trina Build — Scope & Planning Document

_Supervisor reference for next planning session. Captures current state, Gate 3 findings,
legacy tool discovery, and revised sub-step sequence._

_Date: 2026-05-02_

---

## 1. What has shipped (on main)

| Commit | Sub-step | What landed |
|--------|----------|-------------|
| `bd210f4` | Z — Storage migration | Data moved to `~/agent_data/gtd/ranbir/`; plist patched; `GTD_STORAGE_ROOT` env var |
| `ed9f892` | 1 — Shared helpers | `common.py`, `otel_common.py`, `conftest.py`, 37 Python tests |
| `0e9a40b` | docs | `trina-handoff-2026-05-02-v1.md` committed |

Sub-step 2 (calendar read) is **on the feature branch `feature/sub-step-2-calendar-read`**, Gate 3 in progress — see §3.

---

## 2. Sub-step 2 — what was built

**Two plugin tools registered in `plugins/gtd-tools/`:**

| Plugin tool | Script | What it does |
|-------------|--------|--------------|
| `list_events` | `scripts/calendar/get_events.py` | Lists Google Calendar events; optional `calendar_id`, `time_min`, `time_max`, `max_results` |
| `get_event` | `scripts/calendar/get_event.py` | Fetches single event by ID |

Both scripts: inline retry loop (`_MAX_RETRIES=3`) via `_is_transient_google`; `agent.id`/`tool.name` always set on spans; context attrs (`user.id` etc.) read from `OPENCLAW_*` env vars if present.

**otel_common.py additions (extends sub-step 1):**
- `_is_transient_google(exc)` — True for `HttpError >= 500` and connection errors
- `BatchSpanProcessor` → `SimpleSpanProcessor` for production (fix: batch processor's 5s flush window outlives short-lived plugin scripts; spans were silently dropped)

**common.py change (extends sub-step 1):**
- `GOOGLE_OAUTH_CREDENTIALS` replaces `GOOGLE_OAUTH_TOKEN_PATH`; `GOOGLE_OAUTH_CLIENT_SECRETS_PATH` removed (setup-time only)

**58 Python tests passing. 0 LLM tests (no capability prompts this sub-step).**

**KNOWN_ISSUES.md created** at `gtd-workspace/docs/KNOWN_ISSUES.md` (KI-001 through KI-009).

---

## 3. Gate 3 findings — what we learned

### 3.1 OAuth and Google API work

Credentials loaded, token refresh works, Google Calendar API returns real data. The infrastructure is correct.

### 3.2 OTEL spans were not reaching Honeycomb (fixed)

`BatchSpanProcessor` has a 5-second default flush delay. Plugin scripts exit in ~1 second via `sys.exit(0)` in `ok()`. Spans died with the process. Fixed by switching to `SimpleSpanProcessor` for production. **No restart required — scripts are spawned fresh per call.**

### 3.3 Test spans were contaminating Honeycomb

`otel_common.py` calls `configure_tracer_provider()` with the real OTLP exporter at import time. Tests that don't call `_make_exporter()` emit real spans — including mock-stack-trace error spans from `test_oauth_credential_failure_calls_err`. Root cause: no autouse fixture swapping to InMemory before each test.

**Fix not yet applied.** Add to `scripts/conftest.py`:
```python
@pytest.fixture(autouse=True)
def isolate_tracer_provider():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    try:
        import otel_common
        otel_common.configure_tracer_provider(InMemorySpanExporter())
    except ImportError:
        pass
    yield
```

### 3.4 MCP server conflict — our plugin tools were never called

`~/.openclaw/openclaw.json` has a `google-calendar` MCP server (`@cocal/google-calendar-mcp`) that exposes `google-calendar__list-events`, `google-calendar__get-current-time`, etc. Without SKILL.md instructions telling the agent which tool to call, Sonnet reached for the MCP tools. Our plugin `list_events` was never invoked. No OTEL spans from our scripts.

The agent returned correct calendar data — but via MCP, not our pipeline.

**This is the SKILL.md problem, not a plugin problem.** Without capability prompts and dispatch rules, the agent picks whatever tool best matches its training intuition. With MCP and our plugin both on the surface, MCP wins.

### 3.5 Model was wrong

Agent was configured as `ollama/qwen3.5:latest`. Qwen is not capable enough for tool orchestration on outer turns. Switched to `mnemo/claude-sonnet-4-6` in `~/.openclaw/openclaw.json`. Per trina-build.md §5: outer turns are Sonnet only, no fallback.

### 3.6 Plist was missing env vars

`GOOGLE_OAUTH_CREDENTIALS`, `GTD_TZ`, `OTEL_EXPORTER_OTLP_ENDPOINT` were not in the gateway plist. Added manually. Note: `OTEL_SERVICE_NAME` was intentionally NOT added — scripts default to `"gtd"` via `os.environ.get("OTEL_SERVICE_NAME", "gtd")`; setting it globally in the plist would stomp every other agent's service name.

### 3.7 Gate 3 status

| Check | Result |
|-------|--------|
| Plugin registered (`openclaw plugins inspect gtd-tools`) | GREEN |
| OAuth + Google Calendar API | GREEN |
| `list_events` fires as registered tool | RED — MCP intercepts |
| 0 forbidden calls | GREEN (but via MCP, not our plugin) |
| Honeycomb span from our scripts | RED — deferred to Sub-step 6 (SKILL.md required) |

**Gate 3 is deferred. Unblocked by Sub-step 6 skill wiring.** The infrastructure is correct; the agent needs dispatch instructions to call the right tool.

---

## 4. Legacy tool discovery

Seven legacy Python scripts in `gtd-workspace/tools/`:

| Script | What it does | Exec-based? |
|--------|-------------|-------------|
| `common.py` | Schema loading, path resolution, JSONL I/O, shared enums | Shared lib |
| `gtd_normalize.py` | Classifies raw input (task/idea/parking_lot) via regex; no LLM | Yes |
| `gtd_router.py` | Routes normalizer output to correct branch; deterministic only | Yes |
| `gtd_validate.py` | Validates candidate records against data contract | Yes |
| `gtd_write.py` | Persists validated records to JSONL storage | Yes |
| `gtd_query.py` | Retrieves/ranks task records by filter criteria | Yes |
| `gtd_review.py` | Structured review scan (stale tasks, overdue ideas, delegation) | Yes |
| `gtd_delegation.py` | Grouped view of delegated/waiting items | Yes |

**Current AGENTS.md explicitly lists `exec`, `read`, `write`, `edit` as tools.** This is the pre-Trina workspace. `tools.deny: ["exec", "group:runtime"]` has NOT been applied to the gtd agent. The agent can currently bypass all registered tools via exec.

The legacy scripts do NOT use `otel_common.py`. No OTEL coverage on any GTD task pipeline operation.

`tools/common.py` is a separate file from `scripts/common.py`. They coexist intentionally: `tools/common.py` is the JSONL/enum layer for the legacy pipeline; `scripts/common.py` is the plugin-layer helper built in sub-step 1.

---

## 5. Revised sub-step sequence

The original sequence from `trina-build.md` §7 needs two insertions:

| # | Name | Net-new | Status |
|---|------|---------|--------|
| Z | Storage migration | Data migration, plist, env var | **Closed** `bd210f4` |
| 1 | Shared helpers | `common.py`, `otel_common.py`, tests | **Closed** `ed9f892` |
| 2 | Calendar read | `get_events.py`, `get_event.py`, plugin wiring, OTEL | **Branch open** — Gate 3 deferred to Sub-step 6 |
| **2b** | **Legacy tool migration + exec lockdown** | Migrate `tools/*.py` to plugins in `gtd-tools/`; add OTEL to each; apply `tools.deny: ["exec", "group:runtime"]`; retire exec from AGENTS.md | **New — required before Sub-step 6** |
| 3 | Calendar write | `create_event.py` with attendees, invites | Queued |
| 4 | Calendly | `generate_link.py`, channel-routed delivery | Queued |
| 5 | Gmail send | `send_message.py` | Queued |
| **5b** | **Plugin-utils extraction** | Extract `toToolResult` shared helper before third plugin (KI-003); decide pattern at Sub-step 5 prep | **New — KI-003 target** |
| 6 | Persona surface + SKILL.md | IDENTITY/SOUL/AGENTS → "Trina"; capability prompts for all tools; MCP server decision; Gate 3 re-run for Sub-step 2 | Queued |
| 7 | Slack channel | Bot wiring + send tools | Deferred |
| 8+ | Phase 2 inbound | iMessage, Gmail read, relay | Future |

---

## 6. Sub-step 2b — legacy tool migration scope

**Goal:** Every GTD tool reachable via registered plugin call; exec denied; OTEL on all operations.

**Work items:**
1. Wrap each of the 7 legacy tools as a plugin entry in `plugins/gtd-tools/tool-schemas.js`
2. Add `otel_common.py` span instrumentation to each script (same pattern as calendar tools)
3. Update `tools.allow` in `~/.openclaw/openclaw.json` to include all 7 tools + `list_events` + `get_event` + `message`
4. Apply `tools.deny: ["exec", "group:runtime"]`
5. Update AGENTS.md to remove `exec`, `read`, `write`, `edit` from tool surface; list only registered plugin tools
6. Forensic audit (`audit_session.py --latest gtd`) confirms 0 forbidden calls on a full GTD capture → review flow

**Decision needed:** The legacy tools use `sys.argv` with a different calling convention (some use `argparse` with positional args, not JSON string in `argv[1]`). All need to be normalized to the `_spawn: "argv"` pattern (JSON string in `argv[1]`) before plugin registration. This may require light refactoring of each script's `main()`.

**Test plan:** Each migrated tool needs Python unit tests (TDD) and a forensic audit confirming no exec bypasses. No LLM tests (no capability prompts touch these tools directly).

---

## 7. Open decisions for supervisor

**D-1: MCP server disposition.** The `google-calendar` MCP server in `~/.openclaw/openclaw.json` provides overlapping calendar tools. Options:
- Remove it entirely (our plugin is the single source of truth)
- Keep it but add dispatch rules in SKILL.md to route to our tools explicitly
- Keep it as a fallback for capabilities our tools don't yet cover

**D-2: Legacy tool refactor depth.** The 7 legacy tools work and have no obvious bugs. The question is whether to migrate them as-is (minimal refactor, just add plugin wiring + OTEL) or take the opportunity to modernize their interfaces (Pydantic models, typed returns). Minimal refactor is faster; modernization makes them consistent with calendar tools. Recommend: migrate as-is in Sub-step 2b; modernize opportunistically in later passes if a tool needs changes anyway.

**D-3: OTEL service name per plugin call.** Currently `_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "gtd")`. All plugin scripts for this agent use service name `"gtd"`. If we ever want per-tool service differentiation, this needs to change. For now, `"gtd"` is correct.

**D-4: Test contamination fix (KI from Gate 3).** The `isolate_tracer_provider` autouse fixture (§3.3 above) should be applied before Sub-step 2b begins, so test runs from that sub-step don't pollute Honeycomb. Low effort; high value for clean observability.

---

## 8. Immediate next actions (before next sub-step starts)

1. **Close Sub-step 2:** squash `9e0e45b` + `bb4145a` on `feature/sub-step-2-calendar-read`, merge to main. Update `progress.md`.
2. **Apply `isolate_tracer_provider` fixture** to `scripts/conftest.py` (§3.3). Commit to main directly or as part of Sub-step 2 squash.
3. **Supervisor decision on D-1** (MCP server) before writing Sub-step 6 SKILL.md — the capability prompts need to know whether to reference our tools explicitly or let the agent choose.
4. **Sub-step 2b plan-mode prompt** — write the migration spec for the 7 legacy tools before starting.

---

_Last updated: 2026-05-02. Owner: supervisor (Ranbir)._
