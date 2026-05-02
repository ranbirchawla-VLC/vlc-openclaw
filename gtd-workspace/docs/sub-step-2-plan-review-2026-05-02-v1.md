# Sub-step 2 — Plan Review (Round 1)

_Supervisor review of Claude Code's Sub-step 2 plan-mode response. Six corrections required; six open questions resolved._

_Date: 2026-05-02_

---

## Corrections required

### 1. Script filename — `get_events.py`, not `list_events.py`

`trina-build.md` §6 names the file `get_events.py` under `scripts/calendar/`. Tool name stays `list_events` (LLM-facing, plugin schema). Test file becomes `test_get_events.py`. Convention locked: §6 owns filenames; plugin schema owns tool names.

### 2. Standard attributes — don't blanket-defer

Set what's available now; defer only what requires OpenClaw propagation:

- `agent.id = "gtd"` — constant, set always
- `tool.name` — constant per script (`"list_events"` or `"get_event"`), set always
- `user.id`, `session.id`, `channel.type`, `channel.peer_id`, `request.type` — read from env vars; set if present, omit if absent

When OpenClaw propagation lands in a later sub-step, attributes start appearing without code changes to Calendar tools.

### 3. `_is_transient_google` lives in `otel_common.py`, not `common.py`

`_is_transient` (httpx) already lives in `otel_common.py`. Both are transient-error detection helpers feeding retry loops. Cohesion wins. `common.py` stays focused on credentials and IO helpers.

Acknowledged scope expansion of a Sub-step 1 file. Approved: right shared location, no Sub-step 1 decision relitigated.

### 4. Retry loop location and `time.sleep` mocking

Per-script retry loop, mirroring the `call_llm` pattern in `agent_api_integration_pattern.md`. Specify in the build.

Test plan must mock `time.sleep` in `test_transient_error_retries_and_succeeds` and `test_transient_error_exhausted_calls_err`. Otherwise the suite accumulates real seconds per retry test. Add to test plan explicitly.

### 5. `GOOGLE_OAUTH_CLIENT_SECRETS_PATH` is setup-time only

At runtime, only `token.json` is read (carries client_id, client_secret, refresh_token). `client_secrets.json` is for initial auth flow only. Plugin scripts must not read `GOOGLE_OAUTH_CLIENT_SECRETS_PATH`. Env var stays documented in §3 for setup completeness; runtime scripts don't touch it.

### 6. Tool name discipline in OTEL attributes

Confirm both:
- Span name: `gtd.calendar.list_events` / `gtd.calendar.get_event` (structural)
- Attribute: `tool.name = "list_events"` / `tool.name = "get_event"` (queryable filter)

Both. Don't drop one.

---

## Open questions — resolved

**Q1, Q2** — confirmed pre-prompt (OAuth artifacts present at env-var paths; OTEL collector forwarding to Honeycomb).

**Q3** — `otel_common.py` (see correction 3).

**Q4** — npm available. Generate `tools.schema.json` and commit it. If `.venv` doesn't have npm, operator runs the build step manually before pre-review commit.

**Q5** — snake_case mapping confirmed:
- `htmlLink` → `html_link`
- Attendees absent → `[]`
- Location/description absent → `null`
- Field set: `id, summary, start, end, attendees, location, description, html_link`

**Q6** — `get_event` returns raw Google API dict (full object). `list_events` returns mapped subset. Caller asking for detail wants detail; caller asking for list wants the LLM to scan it cleanly.

---

## Net deltas to apply

- Rename: `list_events.py` → `get_events.py`; test file matches
- OTEL: `agent.id` and `tool.name` always set; other standard attrs read from env, omit if absent
- Move `_is_transient_google` to `otel_common.py`
- Per-script retry loop mirroring `call_llm`; mock `time.sleep` in retry tests
- Drop `GOOGLE_OAUTH_CLIENT_SECRETS_PATH` from runtime script reads
- Confirm span name and `tool.name` attribute coexist

No build until revised plan returns and clears.
