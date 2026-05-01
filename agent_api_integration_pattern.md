# Agent API Integration Pattern

How to add external API capabilities (Gmail, Google Calendar, etc.) to an
OpenClaw agent without using `exec`. The canonical reference implementation
is `plugins/nutriosv2-tools/`.

---

## Why plugins, not workspace tools

Workspace `openclaw.json` tool entries are **silently dropped** by the gateway.
The LLM never sees them. Only tools registered as plugins in the root
`openclaw.json` under `plugins.entries` appear in the LLM's tool surface.

This was confirmed 2026-04-27 during the NutriOS v2 build: every agent in
the portfolio was falling back to `exec` bypasses because workspace tools
were defined but never plugin-registered. The fix — and the mandatory pattern
going forward — is plugins.

See `AGENT_ARCHITECTURE.md` §"CRITICAL: Custom Tools Must Be Plugins" for the
full incident and defense hierarchy.

---

## File layout for a new plugin

```
plugins/<agent>-tools/
  index.js              <- plugin entry point; registers tools with the SDK
  tool-schemas.js       <- TOOLS array; one entry per tool
  tools.schema.json     <- generated artifact; run `npm run build:schemas`
  package.json          <- plugin metadata; declares openclaw.extensions
  openclaw.plugin.json  <- plugin id/name/description
  scripts/
    emit-schemas.js     <- build script; strips internal fields, writes tools.schema.json

skills/<agent>/scripts/
  <tool_a>.py           <- one Python file per tool; reads argv[1] as JSON, prints JSON
  <tool_b>.py
  common.py             <- shared constants (DATA_ROOT, ok(), err(), etc.)
```

Python scripts live in the agent workspace (`skills/`), not inside the plugin
directory. The plugin is the wiring layer only.

---

## The three files every builder needs

### 1. `plugins/<agent>-tools/tool-schemas.js`

Defines what tools exist and what they accept. Each entry:

```js
export const TOOLS = [
  {
    _script: "get_calendar_events.py",   // Python script filename under skills/.../scripts/
    _spawn: "argv",                       // "argv" or "stdin" — see below
    name: "get_calendar_events",          // LLM-facing tool name
    description: "Fetch upcoming events from Google Calendar for a user. Returns {ok: true, data: {events: [...]}}.",
    parameters: {
      type: "object",
      properties: {
        user_id:    { type: "integer", description: "Telegram user ID" },
        days_ahead: { type: "integer", description: "How many days to look ahead (default 7)" },
      },
      required: ["user_id"],
    },
  },
  // ... more tools
];
```

**`_spawn` values:**
- `"argv"` — params passed as `JSON.stringify(params)` in `sys.argv[1]`. Use for
  all tools that take structured input. This is the standard pattern.
- `"stdin"` — params passed via stdin. Use only when argv is unavailable (rare).

### 2. `plugins/<agent>-tools/index.js`

Wires the TOOLS array into the OpenClaw SDK. Copy this verbatim and change
the agent name and paths:

```js
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { TOOLS } from "./tool-schemas.js";

const __pluginDir = dirname(fileURLToPath(import.meta.url));
const __workspaceDir = dirname(dirname(__pluginDir));  // plugins/<agent>-tools/ -> plugins/ -> workspace/

const PYTHON = join(__workspaceDir, ".venv", "bin", "python");
const SCRIPTS = join(__workspaceDir, "skills", "<agent>", "scripts");

function spawnArgv(script, params) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`, JSON.stringify(params)],
    { encoding: "utf8", env: { ...process.env } }
  );
}

function spawnStdin(script, params) {
  return spawnSync(
    PYTHON,
    [`${SCRIPTS}/${script}`],
    { encoding: "utf8", input: JSON.stringify(params), env: { ...process.env } }
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
          return toToolResult(spawn(_script, params));
        },
      });
    }
  },
});
```

### 3. `plugins/<agent>-tools/package.json`

```json
{
  "name": "<agent>-tools",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build:schemas": "node scripts/emit-schemas.js"
  },
  "openclaw": {
    "extensions": ["./index.js"],
    "compat": { "gateway": ">=0.1.0" }
  }
}
```

---

## Python script pattern

Each tool is a standalone Python script. Standard shape:

```python
"""<tool_name>; <one-line description>.

Usage: python3 <tool_name>.py '<json_args>'
Returns {ok: true, data: {...}} or {ok: false, error: "..."}.
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import ok, err

from pydantic import BaseModel


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
    result = run_<tool_name>(inp.user_id, ...)
    ok(result)


if __name__ == "__main__":
    main()
```

`ok(data)` prints `{"ok": true, "data": data}` and exits 0.
`err(message)` prints `{"ok": false, "error": message}` and exits 1.
Both are in `common.py`.

---

## Inner LLM calls from plugin tools

Some tools need to call Claude themselves — macro estimation, semantic matching, structured extraction. These are inner LLM calls made from within a Python plugin script. The configuration below is production-verified across `batch_estimate.py`, `semantic_match.py`, and `estimate_macros.py`.

### Configuration constants

```python
import anthropic
import time

_MODEL = "claude-sonnet-4-6"   # pin the model; never leave it as a variable
_TEMPERATURE = 0                # deterministic output; required for retry logic and LLM tests
_MAX_TOKENS = 1024              # size to your expected output; don't over-allocate
_MAX_RETRIES = 3                # 3 retries + 1 initial = 4 total attempts
```

Pin `_MODEL` as a module-level constant. A variable model string is a production incident waiting to happen — it will drift in tests, drift in prod, and be invisible until behavior changes.

`_TEMPERATURE = 0` is mandatory for any tool that has a retry loop. Non-zero temperature means each retry gets a different (potentially worse) response. Zero temperature means retrying on a transient failure gives the same good response once the failure clears.

### API key loading

```python
import json
import os
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

### Base URL

```python
client = anthropic.Anthropic(
    api_key=_load_api_key(),
    base_url="https://api.anthropic.com",  # bypass mnemo proxy — see note below
)
```

**Why direct to `api.anthropic.com`:** mnemo 0.1.0 has a request-body truncation bug (Bug 2) that silently drops Python SDK requests routed through the proxy. Inner skill calls must bypass mnemo until this is fixed. The fix is a one-line `base_url` swap per script once Bug 2 is resolved.

Outer LLM calls (Telegram turns) still route through mnemo normally.

### Retry loop

The nested try/except pattern is fragile and doesn't scale past one retry. Use a loop:

```python
from dataclasses import dataclass

@dataclass
class MyResult:
    data: list
    retry_occurred: bool  # caller can append a system-level warning when True


def call_llm(descriptions: list[str]) -> MyResult:
    client = anthropic.Anthropic(api_key=_load_api_key(), base_url="https://api.anthropic.com")
    prompt = _build_prompt(descriptions)
    raw = ""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(1)          # 1-second pause between attempts; mock this in tests
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

`retry_occurred` on the result lets `log_meal_items` (or any orchestrating caller) append a system-level warning without parsing strings.

Initialize `raw = ""` and `last_exc: Exception | None = None` before the loop. Both are always set by the first iteration, but the explicit init keeps type checkers and readers happy.

### Mocking in tests

`time.sleep` must be mocked in any test that exercises the retry path — otherwise your test suite accumulates 3 seconds per exhaustion test:

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

### Reference implementations

All three are in `skills/nutriosv2/scripts/inner_skills/`:

| File | What it does | Key complexity |
|---|---|---|
| `batch_estimate.py` | Estimates per-unit macros for a list of food descriptions | Batch JSON array validation; `round()` on float returns |
| `semantic_match.py` | Matches colloquial food references to named recipes | Verbatim-match validation against a recipe name set; null-safe |
| `estimate_macros.py` | Single-item macro estimate (used by v1 capability) | Simpler; single-object schema |

---

## For public API integrations (Gmail, Google Calendar, etc.)

The Python script is responsible for:
1. Loading credentials (service account JSON or OAuth token) from a known path
   or environment variable — never hardcode secrets.
2. Calling the API using the official Python SDK (`google-api-python-client`,
   `google-auth`, etc.).
3. Returning structured data via `ok()`.

Credential pattern:

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

Add `GOOGLE_CREDS_PATH` (or per-API equivalents) to the launchd plist so the
gateway process inherits it. Do not put it in the workspace or plugin directory.

Dependencies go in the agent workspace `pyproject.toml` under `[project.optional-dependencies]`
or `[project.dependencies]`, then `pip install -e ./skills/<agent>[dev]` reinstalls.

---

## Operator-handled wiring (not in-repo)

After building the plugin, two steps are required that live outside the repo:

**1. Install the plugin:**
```bash
openclaw plugins install --link --dangerously-force-unsafe-install \
  /Users/ranbirchawla/.openclaw/workspace/plugins/<agent>-tools
```

**2. Register in `~/.openclaw/openclaw.json`:**
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

`tools.deny: ["exec", "group:runtime"]` is mandatory. Without it the LLM can
bypass registered tools via exec. This was the root cause of the NutriOS v2
P0 incident (2026-04-27).

Restart gateway after any change to root `openclaw.json` or the plugin JS files.
Python script changes take effect immediately (scripts are spawned fresh per call).

---

## Generating `tools.schema.json`

After editing `tool-schemas.js`, regenerate the committed artifact:

```bash
cd plugins/<agent>-tools && npm run build:schemas
```

Commit `tools.schema.json` alongside `tool-schemas.js`. The LLM test harness
reads from this file; the gateway reads from the plugin JS. Both must stay in sync.

---

## Reference implementation

`plugins/nutriosv2-tools/` — 11 tools, production-verified. Read it as the
authoritative example. Specifically:

- `index.js` — complete wiring pattern
- `tool-schemas.js` — real tool definitions at various schema complexities
  (no-input tools like `get_today_date`, nested object schemas like `lock_mesocycle`,
  array inputs like `log_meal_items`)
- `scripts/emit-schemas.js` — schema emission build step

---

_Created: 2026-05-01. Update when plugin SDK changes or a new integration
pattern is established._
