# Trina Build — Master Design

_Source of truth for the gtd agent's transformation into Trina. All sub-step
prompts reference this doc. Update when architecture changes; do not relitigate
locked decisions._

---

## 1. Identity & scope

**Agent id:** `gtd` (unchanged — workspace, registry, OTEL service name all stay `gtd`).
**Persona:** Trina. Surfaced in IDENTITY.md, SOUL.md, AGENTS.md, user-facing copy.
**Tribute:** named for the best admin/partner Ranbir worked with. Sets the standard.

**Phase 1 (this build):** calendar reads, meeting setup with invites, Calendly links (custom + standard) delivered via Telegram, Slack, or email.

**Phase 2 (later):** iMessage and inbound email channels. Bidirectional relay.

---

## 2. Architecture commitments (locked)

- **Plugins, not workspace tools.** Custom tools register in root `openclaw.json` under `plugins.entries`. Workspace `openclaw.json` tools are silently dropped.
- **Exec denied.** `tools.deny: ["exec", "group:runtime"]` mandatory.
- **Data discipline.** Runtime state in `~/agent_data/gtd/ranbir/`. Google Drive only when humans need access to outputs.
- **OTEL native from day one.** Every plugin tool emits spans to `http://localhost:4318/v1/traces`. Collector forwards to Honeycomb.
- **Hybrid model per call site.** Qwen first, Sonnet on validation failure. Not a global flag — per inner-LLM-call configuration.
- **Mnemo bypass for inner calls.** `base_url="https://api.anthropic.com"` for Sonnet leg until Bug 2 fixed. Outer Telegram/Slack turns route through Mnemo as configured.
- **Temperature=0** for all inner calls; pin model as module constant.

---

## 3. Credential model

OAuth 2.0 user flow (3-legged). Two files:

- `client_secrets.json` — OAuth client identity from Google Cloud Console. One-time download.
- `token.json` — authorized user token (access + refresh + scopes). Generated once via `InstalledAppFlow`. Plugin reads at runtime; refresh handled by `google.auth.transport.requests`.

**Env vars (gateway process):**

```
GOOGLE_OAUTH_CLIENT_SECRETS_PATH=/Users/ranbirchawla/.openclaw/secrets/google_client_secrets.json
GOOGLE_OAUTH_TOKEN_PATH=/Users/ranbirchawla/.openclaw/secrets/google_token.json
GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir
GTD_TZ=America/Denver
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=gtd
```

**Phase 1 scopes (bundle in initial auth — scopes baked into token):**

```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/gmail.send
```

Gmail read/modify deferred to Phase 2 inbound relay. Service account rejected — overkill for single-user agent.

**OAuth refresh:** plugin calls `creds.refresh(Request())` when expired. On refresh failure, surface a structured error naming which credential needs re-auth — not a generic "calendar call failed."

---

## 4. OTEL span shape

**Endpoint:** `http://localhost:4318/v1/traces` (OTLP HTTP).

**Trace propagation across OpenClaw → Python boundary:** W3C `traceparent` passed as env var or extra param in spawn. Plugin reads, uses as parent context. If OpenClaw doesn't yet propagate, plugin starts a root span and we fix propagation as a separate sub-step.

**Standard attributes on every plugin tool span:**

- `agent.id` (always `gtd`)
- `user.id`
- `session.id`
- `channel.type` (`telegram`, `slack`, `email`, `imessage`)
- `channel.peer_id`
- `tool.name`
- `request.type` (capability slug)

**Inner-LLM-call additional attributes:**

- `llm.provider` (`qwen`, `claude`)
- `llm.model` (pinned constant — `qwen3:latest`, `claude-sonnet-4-6`)
- `llm.temperature`
- `llm.input_tokens` / `llm.output_tokens` / `llm.cost_usd`
- `llm.attempt` (retry index, 1-based)
- `llm.retry_occurred` (boolean)
- `llm.validation_error` (the actual error text on schema fail, not a generic flag)
- `llm.prompt_template`
- `llm.endpoint` (`api.anthropic.com` direct, `localhost:9999` mnemo, local Qwen URL)
- `llm.chain_position` (0 = qwen, 1 = sonnet)
- `llm.fallthrough_reason` (`validation_failed`, `timeout`, `endpoint_unavailable`)
- `llm.chain_total_duration_ms`
- `llm.chain_total_cost_usd`

**Phase 2 relay additions:** `relay.thread_id`, `relay.state`.

---

## 5. Hybrid model fallback chain

Per inner-LLM-call file:

```python
_MODEL_CHAIN = [
    {"provider": "qwen",   "model": "qwen3:latest",     "endpoint": "http://localhost:11434"},
    {"provider": "claude", "model": "claude-sonnet-4-6", "endpoint": "https://api.anthropic.com"},
]
_TEMPERATURE = 0
_MAX_TOKENS = 1024
_MAX_RETRIES = 3
```

Validation failure on Qwen → fall through to Sonnet (don't raise). Distinguish:

- `qwen_validation_failed` — fell through, expected, informational
- `chain_exhausted` — Sonnet also failed, surface to user

**Endpoint health cache:** 30-second TTL on Qwen endpoint check. If Qwen has been down for 30s, skip straight to Sonnet without per-request timeout penalty.

**Cost tracking query (build early):** "cumulative cost saved this month = qwen_success_count × estimated_sonnet_cost_per_call." That number is the ROI argument.

---

## 6. File layout

```
gtd-workspace/
  docs/
    trina-build.md                    ← this file
    sub-step-Z-migration.md           ← per-sub-step specs added as built
  AGENTS.md, SKILL.md, IDENTITY.md, SOUL.md, USER.md, TOOLS.md
  openclaw.json                       ← tool schemas; declares env vars
  scripts/
    common.py                         ← DATA_ROOT, TZ, ok(), err(), get_google_credentials()
    otel_common.py                    ← exporter, tracer, traceparent helper, @traced_llm_call
    migrate_storage.py                ← Sub-step Z one-shot
    test_*.py                         ← pytest tests colocated
    calendar/
      get_events.py
      create_event.py
    calendly/
      generate_link.py
    gmail/
      send_message.py
    inner_skills/                     ← Phase 1 may have none; structure ready
  capabilities/
    <capability>.md                   ← capability dispatch markdown

plugins/gtd-tools/
  index.js                            ← plugin wiring per agent_api_integration_pattern.md
  tool-schemas.js
  tools.schema.json                   ← generated; commit alongside
  package.json
  openclaw.plugin.json
  scripts/emit-schemas.js

~/agent_data/gtd/ranbir/              ← runtime data, post-migration
```

---

## 7. Sub-step sequence

| # | Name | Net-new |
|---|------|---------|
| Z | Storage migration | `migrate_storage.py` + tests + env var + cutover |
| 1 | Shared helpers foundation | `common.py` Google creds helper + `otel_common.py` (exporter, tracer, traceparent, `@traced_llm_call` with chain) + tests |
| 2 | Calendar read | `get_events.py` + plugin wiring + LLM tests + OTEL spans verified in Honeycomb |
| 3 | Calendar write | `create_event.py` (with attendees → invites) + tests |
| 4 | Calendly | `generate_link.py` (custom + standard, channel-routed) + tests |
| 5 | Gmail send | `send_message.py` + tests |
| 6 | Persona surface | IDENTITY.md/SOUL.md/AGENTS.md updates to "Trina"; capability prompts |
| 7 | Slack channel | bot wiring + send tools (deferred until you say go) |
| 8+ | Phase 2 inbound + relay | iMessage Apple ID, Gmail read scope, relay state machine |

Each sub-step: Gate 1 (Python tests + LLM tests where applicable) → Gate 2 (code-reviewer subagent fresh context) → Gate 3 (release check). Two commits, squash on green.

---

## 8. Standing rules (apply to every sub-step)

- TDD: failing test before implementation.
- Test conditions match production conditions. New test that closes a bug must fail against unfixed code first.
- LLM tests pin model + temperature=0; run 3x with require-all-pass.
- Forensic audit (`audit_session.py --latest gtd`) at every Gate 3. Forbidden calls = gate fails regardless of bot output.
- Two-commit pattern: pre-review (Gate 1 green) → code-reviewer subagent → post-review (review fixes only) → squash.
- Scope locked at sub-step open. Drift surfaces back to operator before action; supervisor confirms changes explicitly. Carry-forwards to KNOWN_ISSUES.md.
- LLM voice: zero arithmetic, no process narration, no tool announcements, no internal routing leakage. Standard CLAUDE.md rules.
- Plugin tool dispatcher (per Lessons doc §2 capability prompt freshness) is first tool call on every user turn — never compose reply, ask question, or call other tool before dispatcher returns.

---

_Last updated: 2026-05-02. Owner: supervisor (Ranbir). Update when locked decisions change._
