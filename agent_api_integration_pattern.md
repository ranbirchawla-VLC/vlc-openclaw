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
