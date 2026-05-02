# Trina Build — Session Handoff Note

_For the next supervisor session: what's locked, what's in flight, what's queued, what to read first._

_Last updated: 2026-05-02 v1 (Sub-step 1 closed)_

---

## Read first, in order

1. `gtd-workspace/docs/trina-build.md` — master design. All architectural decisions live here.
2. `CLAUDE.md`, `AGENT_ARCHITECTURE.md`, `agent_api_integration_pattern.md`, `SUPERVISOR_ROLE.md`, `SKILL_LESSONS.md` — process, architecture, lessons. Already in project knowledge.
3. This doc — current state and what's next.
4. `gtd-workspace/docs/sub-step-*.md` — per-sub-step records, in order.

## Operating model

- **Roles:** Ranbir = supervisor + architect. Claude (chat) = supervisor's working partner. Claude Code = build agent. Chat does not write production code; chat writes design docs and prompts that drive Claude Code.
- **Plan-mode gate:** every sub-step prompt requires Claude Code to enter plan-mode after setup, return the plan, and stop. Supervisor reviews, clears or returns findings. Only after plan-mode clears does Claude Code build.
- **Three-gate discipline:** Gate 1 automated tests (Python + LLM where applicable) → Gate 2 code-reviewer subagent in fresh context → Gate 3 release check. Two-commit pattern: pre-review then post-review fixes. Squash on long-lived branch after Gate 3 passes.
- **Token economy:** chat side keeps responses dense. No preamble, no recap of settled state. Half as long is the bar.
- **Filename convention for handoff/durable artifacts:** `<name>-YYYY-MM-DD-vN.md`.

## Architectural commitments (locked, do not relitigate)

- Workspace path: `gtd-workspace/`. Agent id: `gtd`. OTEL service name: `gtd`. Persona: Trina (in IDENTITY/SOUL/AGENTS only).
- Plugins, not workspace tools. `tools.deny: ["exec", "group:runtime"]` mandatory.
- Data: runtime state in `~/agent_data/gtd/ranbir/`. Google Drive only when humans need access to outputs.
- OTEL native from day one. Endpoint `http://localhost:4318/v1/traces`. Local collector forwards to Honeycomb.
- **Model routing is role-based, not chain-based.** Outer (user-facing) = Sonnet only, no fallback. Inner (extraction/classification inside Python) = Qwen primary, Sonnet fallback on validation failure. ValidationError raises immediately on either role; transient errors get retry budget within the same provider.
- OAuth 2.0 user flow for Google. Two files: `client_secrets.json` and `token.json`. Phase 1 scopes bundled at initial auth: calendar, calendar.events, gmail.send.
- Mnemo bypass for inner LLM calls (`base_url="https://api.anthropic.com"`) until Bug 2 fixed. Outer turns route through Mnemo as configured.
- Temperature=0 for all inner calls; pin model as module constant.

## Sub-step status

| # | Name | State | Commit | Notes |
|---|------|-------|--------|-------|
| Z | Storage migration | **Closed** | `bd210f4` on main | Migration ran clean, plist patched, smoke test green. |
| 1 | Shared helpers foundation | **Closed** | `ed9f892` on main | 37 Python tests passing. Branch deleted. |
| 2 | Calendar read | **Queued — next** | — | First plugin tool. Validates OAuth + OTEL helpers against live Google APIs. Real Gate 3 here (real spans landing in Honeycomb). |
| 3 | Calendar write | Queued | — | Create event with attendees, sends invites. |
| 4 | Calendly | Queued | — | Custom + standard links, channel-routed delivery. |
| 5 | Gmail send | Queued | — | Phase 1 send only. `gmail.send` scope. |
| 6 | Persona surface | Queued | — | IDENTITY/SOUL/AGENTS to "Trina." Capability prompts. Also: KNOWN_ISSUES carry-forward (pointer in `agent_api_integration_pattern.md` to `trina-build.md` §3 for OAuth user-flow agents). |
| 7 | Slack channel | Deferred | — | Bot wiring + send tools. Operator says when. |
| 8+ | Phase 2 inbound + relay | Future | — | iMessage Apple ID, Gmail read scope, relay state machine. |

## Sub-step 1 — what shipped

Foundation files every Phase 1 plugin tool depends on. All on main as of `ed9f892`.

- `gtd-workspace/scripts/common.py` — `DATA_ROOT` (required env var, no fallback), `TZ`, `ok()`/`err()` (canonical `sys.exit` semantics), `get_google_credentials(scopes)` with structured error surfaces naming missing env vars, missing files, insufficient scopes, refresh failures, malformed tokens.
- `gtd-workspace/scripts/otel_common.py` — OTLP exporter init, `get_tracer`, `extract_parent_context` (W3C `traceparent` from env), `@traced_llm_call(role, prompt_template)` decorator, `LLMClient` protocol with `AnthropicLLMClient` and `OllamaLLMClient`, `ValidationError` and `ChainExhausted` exception classes, Qwen health cache with 30s TTL, `_is_transient` enumerating httpx exception classes explicitly.
- `gtd-workspace/scripts/test_common.py` — 8 cases (7 + `creds.scopes is None`).
- `gtd-workspace/scripts/test_otel_common.py` — 11+ cases (10 baseline + `_is_transient` direct unit + Qwen 5xx).
- `gtd-workspace/scripts/conftest.py` — sys.path injection, autouse fixture resetting Qwen health cache between tests.
- `gtd-workspace/pyproject.toml` — deps declared (google-auth, google-auth-oauthlib, google-api-python-client, opentelemetry-api/sdk/exporter-otlp-proto-http, anthropic, httpx).
- `gtd-workspace/docs/sub-step-1-shared-helpers.md` — brief sub-step doc + lessons section.
- Makefile — `test-gtd-common`, `test-gtd-otel`, `test-gtd-helpers` targets.

**Lessons captured (Sub-step 1):**
- `httpx.ConnectError` and `httpx.TimeoutException` do not inherit from Python builtins (`ConnectionError`, `TimeoutError`). Transient-error checks must enumerate httpx exception classes explicitly. Calendar/Gmail/Calendly plugins will hit this otherwise.
- The `ok()`/`err()` helpers exit via `sys.exit`; tests catch `SystemExit` via `pytest.raises(SystemExit)` and inspect stdout. Matches canonical pattern; preserves dispatcher's dual-signal failure detection.

**Deferred to Sub-step 2:**
- Real OTEL span verification in Honeycomb (Sub-step 1 Gate 3 was light: `make test-gtd` + clean import).
- LLM tests (`tests/llm/`) — not required for Sub-step 1; helpers are not LLM-prompted surface. Become required when capability prompts use them.
- `llm.cost_usd` for Anthropic — emitted as 0.0 for Qwen, omitted for Anthropic until pricing table is wired. Cost queries in Honeycomb use `llm.input_tokens` + `llm.output_tokens` and apply pricing in the query layer.

## Open prerequisites for Sub-step 2

Before writing the Sub-step 2 plan-mode prompt, confirm:

- OAuth `client_secrets.json` and `token.json` are produced and present at the env-var paths in `trina-build.md` §3. Operator was working on this in parallel with Sub-step 1.
- Local OTEL collector is forwarding to Honeycomb (collector running confirmed at end of Sub-step 1; "spans landing in Honeycomb" is the Sub-step 2 Gate 3 verification).
- Qwen still serving at `http://localhost:11434`.

## Open carry-forwards

- KNOWN_ISSUES (priority low): `agent_api_integration_pattern.md` should add a pointer to `trina-build.md` §3 for OAuth user-flow agents. Address in Sub-step 6 or standalone docs cleanup.
- Mnemo Bug 2 (inner-call routing) still live. When fixed, the inner-call `base_url` override comes out and inner calls route through Mnemo for context caching benefits.

## Decisions queued (not yet locked)

None at handoff. All open questions resolved before Sub-step 1 plan-mode cleared.

## Things the next session should not do

- Do not start Sub-step 2 cold without re-reading `trina-build.md`. The role-based routing rule is the easiest thing to forget and the most expensive to get wrong.
- Do not add Mnemo to the inner-call path until Bug 2 is fixed and the operator confirms the change.
- Do not relitigate workspace path naming, agent id, or persona placement. Locked.
- Do not let LLM voice rules drift in capability prompts. Zero arithmetic, no process narration, no tool announcements, no internal routing leakage. Standard from CLAUDE.md.

---

_Update at session close. Replace the closing sub-step's "what shipped" section; update sub-step status table; add anything net-new to commitments, lessons, or carry-forwards._
