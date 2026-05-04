# Agent API Integration Pattern

Build-time mechanics for OpenClaw agent plugins. Read by Code at build time, not by Chat.

For architectural rules, drift indicators, and halt conditions, see `AGENT_ARCHITECTURE.md`. This doc is the templates, code skeletons, and CLI commands.

---

## Scope

This doc owns:

- Code skeletons (`common.py`, plugin `index.js`, tool-schemas.js, Python tool scripts)
- OTEL plugin wrapping mechanics
- Inner-LLM call mechanics (model pinning, retry loops, key loading, mocking)
- Public API credential patterns (Google service account, launchd plist)
- Build-time CLI commands and registration

This doc does not own (see AGENT_ARCHITECTURE.md):

- Why plugins beat workspace tools (locked pattern 3)
- Why exec is denied (locked pattern 4)
- Capability-shaped vs script-shaped surface rules (locked pattern 5)
- Date sourcing rule (locked pattern 6)
- Local-only data storage (locked pattern 7)
- Multi-mode dispatcher pattern (locked pattern 1)
- OTEL cross-process propagation rule (locked pattern 2)

When this doc and AGENT_ARCH disagree, AGENT_ARCH wins for the rule; this doc wins for the implementation.

---

## File layout for a new plugin

```
plugins/<agent>-tools/
  index.js              plugin entry; registers tools with the SDK
  tool-schemas.js       TOOLS array; one entry per tool
  tools.schema.json     generated artifact; npm run build:schemas
  package.json          plugin metadata; openclaw.extensions
  openclaw.plugin.json  plugin id, name, description
  scripts/
    emit-schemas.js     build script; strips internal fields

skills/<agent>/scripts/
  common.py             shared constants, data root, utilities
  <tool_a>.py           plugin-registered capability tool
  <tool_b>.py
  <agent>/
    <internal_module>.py  internal modules; imported by capability tools
```

---

## common.py skeleton

```python
"""Shared constants and utilities for <Agent Name>."""
from __future__ import annotations
import contextlib, json, os, sys
from datetime import datetime
import zoneinfo

DATA_ROOT = os.environ.get(
    "<AGENT>_DATA_ROOT",
    f"{os.path.expanduser('~')}/agent_data/<agent>/default"
)
AGENT_TZ = os.environ.get("<AGENT>_TZ", "America/Denver")

def today_str(tz: str = AGENT_TZ) -> str:
    return datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")

def read_json(path: str) -> dict:
    if not os.path.exists(path): return {}
    with open(path) as f: return json.load(f)

def write_json(path: str, data: dict, indent: int = 2) -> None:
    """Atomic write with .bak backup."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.replace(path, path + ".bak")
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)

def ok(data) -> None:
    """Print JSON success and exit 0."""
    print(json.dumps({"ok": True, "data": data}))
    sys.exit(0)

def err(message: str) -> None:
    """Print JSON error and exit 1."""
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(1)

@contextlib.contextmanager
def attach_parent_trace_context():
    """Attach OTEL parent context from TRACEPARENT env var.

    Use comma-form before every top-level Python span:
        with attach_parent_trace_context(), tracer.start_as_current_span("name") as span:
            ...
    """
    token = None
    try:
        traceparent = os.environ.get("TRACEPARENT", "").strip()
        if traceparent:
            from opentelemetry.propagate import extract
            from opentelemetry import context as otel_context
            ctx = extract({"traceparent": traceparent})
            token = otel_context.attach(ctx)
    except Exception:
        pass
    try:
        yield
    finally:
        if token is not None:
            from opentelemetry import context as otel_context
            otel_context.detach(token)
```

---

## tool-schemas.js

Defines what tools exist and what they accept.

```javascript
export const TOOLS = [
  {
    _script: "evaluate_deal.py",
    _spawn: "argv",
    name: "evaluate_deal",
    description: "Evaluate a watch deal against pricing and pipeline state. Returns {ok: true, data: {decision, ...}}.",
    parameters: {
      type: "object",
      properties: {
        brand:     { type: "string" },
        reference: { type: "string" },
        price:     { type: "number" }
      },
      required: ["brand", "reference", "price"]
    }
  },
  // ... more tools
];
```

`_spawn` values:

- `"argv"`; params passed as `JSON.stringify(params)` in `sys.argv[1]`. Standard.
- `"stdin"`; params passed via stdin. Use only when argv is unavailable.

---

## index.js: plugin entry with OTEL wrapping

This is the canonical pattern. Every plugin uses this shape. `startActiveSpan` wrapping is mandatory; the rule lives in AGENT_ARCH locked pattern 2.

```javascript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { trace, context, propagation } from "@opentelemetry/api";
import { randomBytes } from "crypto";
import { TOOLS } from "./tool-schemas.js";

const __pluginDir = dirname(fileURLToPath(import.meta.url));
const __workspaceDir = dirname(dirname(__pluginDir));

const PYTHON  = join(__workspaceDir, ".venv", "bin", "python");
const SCRIPTS = join(__workspaceDir, "skills", "<agent>", "scripts");

const PLUGIN_TRACER = "<agent>-tools";

// SPAWN_ENV is a module constant; passed to every spawnSync.
// Add agent-specific vars (e.g. <AGENT>_DATA_ROOT) here.
const SPAWN_ENV = {
  ...process.env,
  OTEL_SERVICE_NAME: PLUGIN_TRACER
};

function activeTraceparent() {
  const carrier = {};
  propagation.inject(context.active(), carrier);
  if (carrier.traceparent) return carrier.traceparent;
  // Fallback when no SDK is registered (tests, pre-init):
  const traceId  = randomBytes(16).toString("hex");
  const parentId = randomBytes(8).toString("hex");
  return `00-${traceId}-${parentId}-01`;
}

function spawnArgv(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...SPAWN_ENV, ...extraEnv } }
  );
}

function spawnStdin(script, params, extraEnv = {}) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`],
    { encoding: "utf8", input: JSON.stringify(params), env: { ...SPAWN_ENV, ...extraEnv } }
  );
}

function toToolResult(result) {
  if (result.error) {
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: result.error.message }) }] };
  }
  const stdout = (result.stdout ?? "").trim();
  if (result.status !== 0 || !stdout) {
    const stderr = (result.stderr ?? "").trim();
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: stderr || "script exited non-zero", status: result.status }) }] };
  }
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: "failed to parse script output", raw: stdout.slice(0, 500) }) }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(parsed) }] };
}

export default definePluginEntry({
  id: "<agent>-tools",
  name: "<Agent> Tools",
  description: "Custom tools for the <Agent> agent",
  register(api) {
    for (const { _script, _spawn, ...schema } of TOOLS) {
      const spawn = _spawn === "stdin" ? spawnStdin : spawnArgv;
      api.registerTool({
        ...schema,
        async execute(_id, params) {
          return trace.getTracer(PLUGIN_TRACER).startActiveSpan(
            `<agent>.tool.${schema.name}`,
            (span) => {
              span.setAttributes({ "tool.name": schema.name });
              const result = toToolResult(
                spawn(_script, params, { TRACEPARENT: activeTraceparent() })
              );
              span.end();
              return result;
            }
          );
        }
      });
    }
  }
});
```

Key points:

- `startActiveSpan` makes the span active in the OTEL context for the duration of the callback. Required so `propagation.inject` sees the live span.
- `activeTraceparent()` is called inside the callback; that's when the span is active.
- `TRACEPARENT` env var is the only thing crossing the process boundary. Python attaches to it via `attach_parent_trace_context()`.
- Per-tool span attributes (e.g., `grailzee.brand`, `grailzee.reference`) can be set on `span` before the spawn. Match the span attribute contract from the design doc.

---

## package.json

```json
{
  "name": "<agent>-tools",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "@opentelemetry/api": "^1.9.0"
  },
  "scripts": {
    "build:schemas": "node scripts/emit-schemas.js"
  },
  "openclaw": {
    "extensions": ["./index.js"],
    "compat": { "gateway": ">=0.1.0" }
  }
}
```

`@opentelemetry/api` shares the SDK instance registered by `diagnostics-otel` via the `globalThis` singleton. Run `npm install` after adding the dependency.

---

## Tool script skeleton (Python)

Standard shape for every plugin-registered tool.

```python
#!/usr/bin/env python3
"""<tool_name>; <one-line description>.

Usage: python3 <tool_name>.py '<json_args>'
Returns {ok: true, data: {...}} or {ok: false, error: "..."}.
"""

from __future__ import annotations
import json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from common import ok, err, attach_parent_trace_context

from opentelemetry import trace
from pydantic import BaseModel

tracer = trace.get_tracer(__name__)


class _Input(BaseModel):
    user_id: int
    # ... other fields


def run_<tool_name>(user_id: int, ...) -> dict:
    # do the work; call the external API
    return {"field": value}


def main() -> None:
    if len(sys.argv) < 2:
        err("missing args: expected JSON string as sys.argv[1]")
        return
    try:
        raw = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        err(f"invalid JSON args: {e}")
        return
    try:
        inp = _Input(**raw)
    except Exception as e:
        err(f"invalid input: {e}")
        return

    with attach_parent_trace_context(), tracer.start_as_current_span("<tool_name>.run") as span:
        # Set span attributes per design doc contract
        span.set_attribute("user.id", inp.user_id)
        result = run_<tool_name>(inp.user_id, ...)
        ok(result)


if __name__ == "__main__":
    main()
```

The comma-form `with attach_parent_trace_context(), tracer.start_as_current_span(...)` is mandatory. `attach_parent_trace_context` runs first and attaches the parent context; `start_as_current_span` then creates the span as a child of the Node parent. Without this comma-form, the Python span lands as a trace root and you'll see "missing parent span" in the Honeycomb waterfall.

---

## Inner LLM calls from plugin tools

Some tools call Claude themselves (classification, structured extraction, semantic matching). Production-verified configuration below.

### Configuration constants

```python
import anthropic
import time

_MODEL = "claude-sonnet-4-6"   # pin the model; never leave it as a variable
_TEMPERATURE = 0                # required for retry logic and LLM tests
_MAX_TOKENS = 1024              # size to your expected output
_MAX_RETRIES = 3                # 3 retries + 1 initial = 4 total attempts
```

Pin `_MODEL` as a module-level constant. A variable model string drifts in tests, drifts in prod, and is invisible until behavior changes.

`_TEMPERATURE = 0` is mandatory for any tool with a retry loop. Non-zero temperature means each retry gets a different response. Zero means retrying on a transient failure gives the same good response once the failure clears.

### API key loading

```python
import json, os
from pathlib import Path

def _load_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        try:
            return config["models"]["providers"]["mnemo"]["apiKey"]
        except KeyError:
            pass
    raise RuntimeError(
        "ANTHROPIC_API_KEY not set and no key found at ~/.openclaw/openclaw.json"
    )
```

### Base URL (mnemo bypass; TRIAL workaround)

```python
client = anthropic.Anthropic(
    api_key=_load_api_key(),
    base_url="https://api.anthropic.com",  # bypass mnemo proxy
)
```

Inner LLM calls bypass the memory proxy until the underlying mnemo request-body truncation is resolved. Status: TRIAL workaround in AGENT_ARCH; promotion criteria: proxy issue resolved, bypass removed, all calls route through mnemo. Outer LLM calls (Telegram turns) continue through mnemo normally.

### Retry loop

```python
from dataclasses import dataclass

@dataclass
class MyResult:
    data: list
    retry_occurred: bool

def call_llm(descriptions: list[str]) -> MyResult:
    client = anthropic.Anthropic(api_key=_load_api_key(), base_url="https://api.anthropic.com")
    prompt = _build_prompt(descriptions)
    raw = ""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(1)          # mock this in tests
        raw = _call_llm(client, prompt)
        try:
            data = _validate(raw, len(descriptions))
            return MyResult(data=data, retry_occurred=attempt > 0)
        except (json.JSONDecodeError, ValueError) as e:
            last_exc = e

    raise ValueError(
        f"<tool_name>: schema validation failed after {_MAX_RETRIES} retries: {last_exc}; "
        f"last response: {raw!r}"
    ) from last_exc
```

`retry_occurred` lets an orchestrating caller append a system-level warning without parsing strings. Initialize `raw = ""` and `last_exc: Exception | None = None` before the loop; both are always set by the first iteration, but explicit init keeps type checkers happy.

### Mocking in tests

`time.sleep` must be mocked in any test that exercises the retry path; otherwise the suite accumulates 3 seconds per exhaustion test.

```python
from unittest.mock import patch

def test_exhaustion_raises() -> None:
    bad_responses = ["not json"] * (_MAX_RETRIES + 1)
    client = _make_mock_client(bad_responses)
    with patch("inner_skills.my_tool.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.my_tool._load_api_key", return_value="test-key"), \
         patch("inner_skills.my_tool.time.sleep") as mock_sleep:
        with pytest.raises(ValueError, match="schema validation failed"):
            call_llm(["item"])

    assert client.messages.create.call_count == _MAX_RETRIES + 1
    assert mock_sleep.call_count == _MAX_RETRIES
```

### Reference implementations (inner LLM)

In `skills/nutriosv2/scripts/inner_skills/`:

| File | What it does |
|---|---|
| `batch_estimate.py` | Per-unit macros for a list of food descriptions; batch JSON array validation |
| `semantic_match.py` | Match colloquial food references to named recipes; verbatim-match validation |
| `estimate_macros.py` | Single-item macro estimate; simpler single-object schema |

---

## Public API integrations (Gmail, Calendar, etc.)

The Python script loads credentials from a known path or env var, calls the API via the official SDK, returns structured data via `ok()`.

```python
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

_CREDS_PATH = os.environ.get(
    "GOOGLE_CREDS_PATH",
    "/Users/ranbirchawla/.openclaw/secrets/google_service_account.json"
)

def _get_service(api: str, version: str):
    creds = service_account.Credentials.from_service_account_file(
        _CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    return build(api, version, credentials=creds)
```

Add `GOOGLE_CREDS_PATH` (or per-API equivalents) to the launchd plist so the gateway process inherits it. Do not put it in the workspace or plugin directory. Never hardcode secrets.

Dependencies go in the agent workspace `pyproject.toml` under `[project.dependencies]`, then `pip install -e ./skills/<agent>[dev]`.

---

## Operator-handled wiring

Two steps after building the plugin.

### 1. Install the plugin

```bash
openclaw plugins install --link --dangerously-force-unsafe-install \
  /Users/ranbirchawla/.openclaw/workspace/plugins/<agent>-tools
```

### 2. Register in `~/.openclaw/openclaw.json`

```json
{
  "plugins": {
    "entries": {
      "<agent>-tools": { "enabled": true }
    },
    "load": {
      "paths": [
        "/Users/ranbirchawla/.openclaw/workspace/plugins/<agent>-tools"
      ]
    }
  },
  "agents": {
    "list": [
      {
        "id": "<agent>",
        "tools": {
          "allow": ["<tool_a>", "<tool_b>", "message"],
          "deny":  ["exec", "group:runtime"]
        }
      }
    ]
  }
}
```

`tools.deny` is required; AGENT_ARCH locked pattern 4. Restart gateway after any change to root `openclaw.json` or plugin JS files. Python script changes take effect immediately (scripts are spawned fresh per call).

---

## Generating tools.schema.json

After editing `tool-schemas.js`:

```bash
cd plugins/<agent>-tools && npm run build:schemas
```

Commit `tools.schema.json` alongside `tool-schemas.js`. The LLM test harness reads from this file; the gateway reads from the plugin JS. Both must stay in sync.

---

## Reference implementations

| Plugin | What's worth reading |
|---|---|
| `plugins/grailzee-eval-tools/` | Canonical OTEL wrapping; `startActiveSpan` per tool; `SPAWN_ENV` with `OTEL_SERVICE_NAME`; turn_state dispatcher |
| `plugins/nutriosv2-tools/` | 11 tools across schema complexities (no-input `get_today_date`, nested objects, array inputs); inner LLM calls under `skills/nutriosv2/scripts/inner_skills/` |

Read `grailzee-eval-tools/index.js` for the OTEL wrapping; read `nutriosv2-tools/tool-schemas.js` for the schema variety.

---

_Updated 2026-05-04. Rewrite to absorb code skeletons from AGENT_ARCH; add OTEL plugin wrapping; remove redundant architectural prose now owned by AGENT_ARCH._
