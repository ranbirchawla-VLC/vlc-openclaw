# 2b.3 Shared-Tools Plugin: Build Plan

**Date:** 2026-05-06
**Branch:** `feature/sub-step-2b3-capability-wiring` (do not create a new branch)
**Status:** Plan approved; no code written yet. Ready to execute in next session.

---

## Objective

Consolidate `get_today_date` from two separate plugins (`gtd-tools`, `nutriosv2-tools`) into a
new `shared-tools` plugin loaded first in the gateway. The shared plugin resolves the user's
timezone from `profile.json` at execute time and injects `GTD_TZ` into the subprocess
environment. The Python script is self-contained (zero workspace imports). Durable pattern:
every future cross-agent tool lands in `shared-tools`.

---

## Four locked decisions

1. **Gap 1 (user_id):** Option A approved. Add optional `user_id` parameter to `get_today_date`
   schema (`required: []`). Plugin reads `profile.json` when user_id is present; falls back to
   `default_timezone` when absent.

2. **Gap 3 (test count):** Python path. Three net-new tests go in
   `gtd-workspace/scripts/tests/test_shared_get_today_date.py`; included in `make test-gtd` via
   new Makefile target. Target: 209 Python tests. JS tests in
   `shared-tools/tests/test_index.js` are additive; run separately; do not count toward 209.

3. **Gap 5 (nutriosv2 path):** `agent_data_path = /Users/ranbirchawla/agent_data/nutriosv2`.
   Write full entry; no placeholder.

4. **Span name:** `shared-tools.tool.get_today_date`.

---

## File list

### Created outside repo (operator-verified, not committed to this repo)

| Path | Description |
|------|-------------|
| `~/.openclaw/workspace/plugins/shared-tools/package.json` | Mirror gtd-tools: `@opentelemetry/api ^1.9.0` dep; `@opentelemetry/sdk-trace-base ^1.25.0` devDep; `test` script `node --test tests/` |
| `~/.openclaw/workspace/plugins/shared-tools/openclaw.plugin.json` | `id: shared-tools`; configSchema empty (settings live on agent entries, not plugin config) |
| `~/.openclaw/workspace/plugins/shared-tools/tool-schemas.js` | Single entry: `get_today_date`; `_spawn: "argv"`; optional `user_id` parameter; no required |
| `~/.openclaw/workspace/plugins/shared-tools/otel-helpers.js` | Copy of gtd-tools otel-helpers.js with: `PLUGIN_TRACER = "shared-tools"`; `SCRIPTS` pointing to `~/.openclaw/workspace/scripts/shared`; `executeWithSpan` accepts `extraAttrs` for `tz` and `tz_source`; span named `shared-tools.tool.<toolName>` |
| `~/.openclaw/workspace/plugins/shared-tools/index.js` | Reads `~/.openclaw/openclaw.json` at module load; builds `agentId -> {agent_data_path, default_timezone}` map; at execute time uses `process.env.OPENCLAW_AGENT_ID` to look up agent settings; calls `resolveTZ(params, agentDataPath, defaultTz)` (see design below); injects `GTD_TZ` into SPAWN_ENV; passes `tz` + `tz_source` as span attributes |
| `~/.openclaw/workspace/plugins/shared-tools/tests/test_index.js` | JS tests: see test plan below |
| `~/.openclaw/workspace/scripts/shared/get_today_date.py` | Self-contained; inline OTEL setup; reads `GTD_TZ` from env; emits `gtd.get_today_date` span with `tz` attribute; zero workspace imports |

### Modified outside repo

| Path | Change |
|------|--------|
| `~/.openclaw/workspace/plugins/nutriosv2-tools/tool-schemas.js` | Remove `get_today_date` entry |
| `~/.openclaw/workspace/plugins/nutriosv2-tools/tools.schema.json` | Regenerate after removal (11 tools) |
| `~/.openclaw/openclaw.json` | Add `shared-tools` first in `plugins.load.paths`; add `settings` to GTD and nutriosv2 agent entries; see openclaw.json changes below |

### Modified in repo (committed to `feature/sub-step-2b3-capability-wiring`)

| Path | Change |
|------|--------|
| `plugins/gtd-tools/tool-schemas.js` | Remove `get_today_date` entry (10 tools -> 9 tools) |
| `plugins/gtd-tools/tools.schema.json` | Remove `get_today_date` entry (already know exact JSON; no emit script needed) |
| `gtd-workspace/scripts/get_today_date.py` | Add superseded comment at top |
| `gtd-workspace/scripts/tests/test_shared_get_today_date.py` | New: 3 Python tests (see test plan) |
| `Makefile` | Add `test-gtd-shared-get-today-date` target; add to `.PHONY`; include in `test-gtd` target |
| `gtd-workspace/AGENTS.md` | Note `get_today_date` is from `shared-tools` plugin, not `gtd-tools` |
| `gtd-workspace/TOOLS.md` | Same note in Date Utility section |
| `gtd-workspace/docs/KNOWN_ISSUES.md` | Mark plugin conflict resolved; add KI-029 |

---

## Key design: index.js profile resolution

```javascript
// At module load: parse openclaw.json; build agentId -> settings map
function loadAgentSettings() {
  try {
    const cfg = JSON.parse(readFileSync(join(homedir(), ".openclaw", "openclaw.json"), "utf8"));
    const map = {};
    for (const agent of (cfg.agents?.list ?? [])) {
      if (agent.settings) map[agent.id] = agent.settings;
    }
    return map;
  } catch {
    return {};
  }
}
const _AGENT_SETTINGS = loadAgentSettings();

// Exported for test injection
export function resolveTZ(params, agentDataPath, defaultTz) {
  const fallback = { tz: defaultTz ?? "America/Denver", tzSource: "fallback" };
  if (!params.user_id || !agentDataPath) return fallback;
  const profilePath = join(agentDataPath, String(params.user_id), "profile.json");
  try {
    const profile = JSON.parse(readFileSync(profilePath, "utf8"));
    if (profile.timezone) return { tz: profile.timezone, tzSource: "profile" };
  } catch {}
  return fallback;
}

// At execute time
async execute(_id, params) {
  const agentId = process.env.OPENCLAW_AGENT_ID ?? "unknown";
  const s = _AGENT_SETTINGS[agentId] ?? {};
  const { tz, tzSource } = resolveTZ(params, s.agent_data_path, s.default_timezone);
  return executeWithSpan(tracer, "get_today_date",
    (p, extraEnv) => spawnArgv("get_today_date.py", p, { ...extraEnv, GTD_TZ: tz }),
    params,
    { tz, tz_source: tzSource }
  );
}
```

`resolveTZ` is exported so JS tests can call it directly without mocking fs.

Note: `OPENCLAW_AGENT_ID` is assumed to be injected by the gateway at execute time. If absent at Gate 3, add it to the plist or gateway env. This is the only unverified assumption in the build.

---

## Shared Python script design

`~/.openclaw/workspace/scripts/shared/get_today_date.py`:
- Inlines OTEL setup: `TracerProvider` + `OTLPSpanExporter` + `SimpleSpanProcessor` + W3C `TraceContextTextMapPropagator`
- `_configure_tracer(exporter=None)` exported for test injection (mirrors otel_common pattern)
- `run_get_today_date(tz_str: str | None = None) -> dict` -- pure; reads `os.environ.get("GTD_TZ", "America/Denver")` when tz_str is None
- `main()` -- attaches TRACEPARENT context; opens `gtd.get_today_date` span; calls `run_get_today_date()`; emits `tz` attribute; writes JSON to stdout via inline `ok()`/`err()`
- Error code: `invalid_timezone`
- No imports from `common`, `otel_common`, or any workspace path

---

## openclaw.json changes

```json
// plugins.load.paths — add shared-tools FIRST:
[
  "/Users/ranbirchawla/.openclaw/workspace/plugins/shared-tools",
  "/Users/ranbirchawla/.openclaw/workspace/plugins/nutriosv2-tools",
  "/Users/ranbirchawla/ai-code/vlc-openclaw/plugins/grailzee-eval-tools",
  "/Users/ranbirchawla/ai-code/vlc-openclaw-gtd/plugins/gtd-tools"
]

// plugins.entries — add:
"shared-tools": { "enabled": true }

// plugins.installs — add:
"shared-tools": {
  "source": "path",
  "sourcePath": "/Users/ranbirchawla/.openclaw/workspace/plugins/shared-tools",
  "installPath": "/Users/ranbirchawla/.openclaw/workspace/plugins/shared-tools",
  "version": "1.0.0",
  "installedAt": "<timestamp at write time>"
}

// agents.list[id=gtd] — add settings field:
"settings": {
  "agent_data_path": "/Users/ranbirchawla/agent_data/gtd-agent/users",
  "default_timezone": "America/Denver"
}

// agents.list[id=nutriosv2] — add settings field:
"settings": {
  "agent_data_path": "/Users/ranbirchawla/agent_data/nutriosv2",
  "default_timezone": "America/Denver"
}

// tools.allow for both agents: no change (get_today_date name unchanged)
```

---

## Test plan

### Python (3 new tests -- test_shared_get_today_date.py)

Imports the shared script by path via `importlib.util.spec_from_file_location`. Confirms RED
before implementation (shared script doesn't exist yet).

1. `test_profile_tz_used_when_gtd_tz_set`: set `GTD_TZ="Europe/London"` in env; call
   `run_get_today_date()`; assert date is London date. Guards: GTD_TZ injected by plugin from
   profile is honored by the script.

2. `test_default_tz_used_when_gtd_tz_unset`: unset `GTD_TZ` from env; call
   `run_get_today_date()`; assert date matches `datetime.now(ZoneInfo("America/Denver"))`.
   Guards: fallback path (plugin used default_timezone) produces correct date.

3. `test_main_span_has_tz_attribute`: inject `InMemorySpanExporter` via `_configure_tracer()`;
   call `main()`; assert span name `gtd.get_today_date`; assert `tz` attribute non-empty string.
   Guards: span contract v1 honored by shared script.

### JS (additive, in shared-tools/tests/test_index.js, not counted in 209)

1. `resolveTZ` -- user_id present + real profile.json written to temp dir → returns profile tz
2. `resolveTZ` -- user_id present + profile.json missing → returns fallback
3. `resolveTZ` -- user_id present + profile.json has no `timezone` field → returns fallback
4. `resolveTZ` -- user_id absent → returns fallback immediately
5. `executeWithSpan` -- span carries `tz` and `tz_source` attributes
6. `executeWithSpan` -- `GTD_TZ` present in extraEnv passed to spawn
7. Span name is `shared-tools.tool.get_today_date`
8. SPAWN_ENV.OTEL_SERVICE_NAME is `"shared-tools"`
9. TRACEPARENT injected in subprocess env with valid W3C format

---

## TDD execution order

1. Write `test_shared_get_today_date.py` (Python, 3 tests) -- confirm RED (shared script absent)
2. Write `~/.openclaw/workspace/scripts/shared/get_today_date.py` -- confirm GREEN
3. Write `shared-tools/tests/test_index.js` (JS, 9 tests) -- confirm RED
4. Write `shared-tools/otel-helpers.js` -- partial GREEN
5. Write `shared-tools/index.js` (includes `resolveTZ`) -- full GREEN
6. Write remaining shared-tools files (package.json, openclaw.plugin.json, tool-schemas.js)
7. Run `npm install` in `~/.openclaw/workspace/plugins/shared-tools/`
8. Remove `get_today_date` from `gtd-tools/tool-schemas.js`; regenerate `tools.schema.json`
9. Remove `get_today_date` from `nutriosv2-tools/tool-schemas.js`; regenerate
10. Update `openclaw.json`
11. Add superseded comment to `gtd-workspace/scripts/get_today_date.py`
12. Update `Makefile` (add target, add to `test-gtd`, add to `.PHONY`)
13. Update `AGENTS.md`, `TOOLS.md`, `KNOWN_ISSUES.md`
14. `make test-gtd` -- confirm 209
15. `npm test` in `shared-tools/` -- confirm 9/9 JS

---

## KI-029 (new, add to KNOWN_ISSUES.md)

`conftest.py` files in `gtd-workspace/scripts/` and subdirectories use `sys.path.insert` for
test discovery. This pattern is fragile when test files are added in new subdirectories outside
the existing `sys.path` insertion points. Resolution: consolidate path setup to a single
top-level `conftest.py` or adopt `pyproject.toml` `pythonpath` setting. Priority: P3. Target:
next sub-step touching test infrastructure.

---

## Session-open reading order for executor

1. `gtd-workspace/progress.md` (this section)
2. `gtd-workspace/docs/sub-step-2b3/2b3-shared-tools-plan-2026-05-06.md` (this file)
3. `plugins/gtd-tools/index.js` + `otel-helpers.js` (reference for shared plugin structure)
4. `gtd-workspace/scripts/get_today_date.py` + `tests/test_get_today_date.py` (reference for script + test pattern)
5. `~/.openclaw/openclaw.json` (verify current state before editing)
