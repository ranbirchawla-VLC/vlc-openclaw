# Agent Architecture — Vardalux / OpenClaw Reference Standard

_This is the canonical reference for how all agents in this portfolio are
built, structured, and wired. Use this when building new agents or
refactoring existing ones. Give this doc to Claude and Claude Code at the
start of any agent work._

---

## How OpenClaw Wires an Agent

OpenClaw assembles the system prompt from the agent's **workspace directory**
at session start. The workspace is set in `openclaw.json` (the root config)
under `agents.list[].workspace`.

### System Prompt Assembly (in order)

**Cached prefix (stable — injected once, cache-persisted):**
1. `AGENTS.md` — startup instructions, hard rules, what to load
2. `SOUL.md` — persona, tone, voice
3. `TOOLS.md` — local environment notes (paths, device names, etc.)
4. `IDENTITY.md` — name, creature, vibe, emoji
5. `USER.md` — user context (name, timezone, preferences)
6. Available skills block (auto-injected from skill registry)

**Dynamic suffix (below cache boundary — injected fresh each turn):**
7. `HEARTBEAT.md` — periodic task checklist (keep small)

### Tools

Tools are defined in the workspace's `openclaw.json`. OpenClaw reads this
file, injects tool definitions into the LLM call, and executes tool commands
as child processes when the LLM calls them. The LLM never calls tools
directly — OpenClaw is the executor.

### Session Routing

Each agent gets a dedicated Telegram bot token and `accountId` in the root
`openclaw.json`. A `bindings` entry routes that accountId to the agent.
**No agent rides on `accountId: default`** — that slot is reserved for the
main session (direct conversation with the operator).

---

## Canonical Directory Layout

```
/Users/ranbirchawla/.openclaw/workspace/skills/<agent-name>/
  AGENTS.md               ← REQUIRED: startup + hard rules
  SKILL.md                ← REQUIRED: intent dispatch + capability routing
  SOUL.md                 ← REQUIRED: persona/tone
  TOOLS.md                ← env notes, paths, device names
  IDENTITY.md             ← name, vibe, emoji
  USER.md                 ← user context
  HEARTBEAT.md            ← periodic checks (keep minimal or empty)
  openclaw.json           ← tool definitions for this agent
  scripts/
    common.py             ← shared constants, data root, shared utilities
    <tool_a>.py           ← one file per tool
    <tool_b>.py
  capabilities/           ← capability markdown files (if using dispatch pattern)
    <capability>.md
  memory/                 ← daily memory files (YYYY-MM-DD.md)

/Users/ranbirchawla/agent_data/<agent-name>/<user>/
                          ← ALL runtime data lives here (local filesystem)
                          ← Completely separate from code
                          ← NEVER on Google Drive (sync conflicts, FDA issues)
```

### Notes on Layout
- `skills/` is the workspace root for all agents
- `agent_data/` is the data root — separate from code, local only
- Never mix code and data in the same directory
- `scripts/` not `tools/` — consistent with Python convention
- One `common.py` per agent for shared constants and the data root resolver

---

## openclaw.json — Workspace Tool Config

This file lives in the agent workspace root. It defines the tools the LLM
can call. OpenClaw reads it automatically.

### Template

```json
{
  "name": "<agent-name>",
  "version": "1.0.0",
  "description": "<one line description>",
  "session": {
    "dmScope": "per-channel-peer"
  },
  "tools": [
    {
      "name": "<tool_name>",
      "description": "<what this tool does — LLM reads this to decide when to call it>",
      "command": "python3 /Users/ranbirchawla/.openclaw/workspace/skills/<agent>/scripts/<tool>.py",
      "inputSchema": {
        "type": "object",
        "properties": {
          "<param>": {
            "type": "string",
            "description": "<what this param is>"
          }
        },
        "required": ["<param>"]
      }
    }
  ],
  "env": [
    "<AGENT>_DATA_ROOT",
    "<AGENT>_TZ"
  ]
}
```

### Hard Rules for openclaw.json
- **Always use absolute paths** in `command` — never relative
- **Never hardcode the data root** in the command string — use an env var
- **`env` array** declares which env vars the tools expect (informational)
- **`session.dmScope: "per-channel-peer"`** — required for per-user session isolation in DMs
- **Runtime is Python 3** — `python3 /absolute/path/to/script.py`
- No Node.js tools in new agents

---

## scripts/common.py — Shared Constants Pattern

Every agent has a `common.py` that owns paths and shared utilities.
The data root always comes from an env var with a local fallback.

```python
"""Shared constants and utilities for <Agent Name>."""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
import zoneinfo

# ─── Data root ────────────────────────────────────────────────────────
# Set <AGENT>_DATA_ROOT in openclaw.json env or shell.
# Default is local agent_data — never Google Drive.

DATA_ROOT = os.environ.get(
    "<AGENT>_DATA_ROOT",
    "/Users/ranbirchawla/agent_data/<agent-name>/ranbir"  # local fallback, never Google Drive
)

AGENT_TZ = os.environ.get("<AGENT>_TZ", "America/Denver")

# ─── Derived paths ────────────────────────────────────────────────────
LOGS_PATH     = f"{DATA_ROOT}/logs"
STATE_PATH    = f"{DATA_ROOT}/state"
# ... add agent-specific paths here

# ─── Shared utilities ─────────────────────────────────────────────────

def today_str(tz: str = AGENT_TZ) -> str:
    """Return today's date as YYYY-MM-DD in the agent timezone."""
    return datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def read_json(path: str) -> dict:
    """Read and parse a JSON file. Returns {} if missing."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: dict, indent: int = 2) -> None:
    """Write JSON atomically with .bak backup."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bak = path + ".bak"
    if os.path.exists(path):
        os.replace(path, bak)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)


def ok(data: dict | list | str) -> None:
    """Print a JSON success response and exit 0."""
    print(json.dumps({"ok": True, "data": data}))
    sys.exit(0)


def err(message: str) -> None:
    """Print a JSON error response and exit 1."""
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(1)
```

### Tool Script Pattern

Each tool script is a standalone Python file. It reads stdin (JSON),
does its work, and prints a JSON result to stdout.

```python
#!/usr/bin/env python3
"""<tool_name> — <one line description>."""

from __future__ import annotations
import json
import sys
import os

# Add workspace scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, ok, err, read_json, write_json

def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        err(f"Invalid JSON input: {e}")
        return

    # ... tool logic here ...

    ok(result)

if __name__ == "__main__":
    main()
```

---

## Root openclaw.json — Agent Registry

Agents are registered in `~/.openclaw/openclaw.json`. Each agent needs:

1. **Entry in `agents.list`** — id, name, workspace, agentDir, model
2. **Entry in `channels.telegram.accounts`** — dedicated bot token
3. **Entry in `bindings`** — routes the accountId to the agent

### Agent Entry
```json
{
  "id": "<agent-name>",
  "name": "<agent-name>",
  "workspace": "/Users/ranbirchawla/.openclaw/workspace/skills/<agent-name>",
  "agentDir": "/Users/ranbirchawla/.openclaw/agents/<agent-name>/agent",
  "model": "claude-sonnet-4-6"
}
```

### Telegram Account Entry
```json
"<agent-name>": {
  "botToken": "<BOT_TOKEN_FROM_BOTFATHER>",
  "dmPolicy": "open",
  "groupPolicy": "allowlist",
  "groups": {
    "<group-id>": { "policy": "allow" }
  }
}
```

### Binding Entry
```json
{
  "type": "route",
  "agentId": "<agent-name>",
  "match": {
    "channel": "telegram",
    "accountId": "<agent-name>"
  }
}
```

### The `default` accountId
The `default` Telegram account (main bot token) **always routes to `main`**.
It is the operator's direct conversation channel. No functional agent should
be bound to it.

---

## Model Selection

| Agent | Model | Rationale |
|-------|-------|-----------|
| main | claude-sonnet-4-6 | Full capability, operator-facing |
| grailzee | claude-sonnet-4-6 | Financial decisions, needs reasoning |
| watch-listing | claude-sonnet-4-6 | Complex multi-step pipeline |
| nutrios | claude-sonnet-4-6 | Health protocol, needs accuracy |
| intake | claude-haiku-4-6 | High volume, simple extraction |
| gtd | claude-haiku-4-6 | High volume, simple routing |

Use **Haiku** for high-volume, simple extraction/routing tasks.
Use **Sonnet** for anything involving judgment, recommendations, or complex logic.

---

## Data Storage Rules

| Rule | Detail |
|------|--------|
| **Local only** | All runtime data in `~/agent_data/<agent>/<user>/` |
| **No Google Drive for agent data** | Sync conflicts + FDA permission issues make it unreliable |
| **Google Drive for input only** | Reports, photos, invoices that humans drop in — read-only from agents |
| **No hardcoded paths** | Always env var → common.py → scripts |
| **Atomic writes** | Always write to `.bak` then `os.replace()` |
| **No secrets in workspace** | Bot tokens live in root `openclaw.json` only |

---

## Current Agent Inventory & Audit

| Agent | Workspace | Data | Bot Account | Status |
|-------|-----------|------|-------------|--------|
| main | `workspace/` | n/a | default ✅ | ✅ Clean |
| grailzee | `skills/grailzee-eval/` | Google Drive (GrailzeeData) | grailzee ✅ | ⚠️ Non-standard |
| watch-listing | `watch-listing-workspace/` | Google Drive (Photo Pipeline) | watch-listing ✅ | ⚠️ Non-standard |
| intake | `skills/purchase-intake/` | Google Drive (Ops Agent Data) | intake ✅ | ⚠️ Data in workspace |
| gtd | `gtd-workspace/` | Local (`gtd-workspace/storage/`) | gtd ✅ | ⚠️ Data in workspace |
| nutrios | `skills/nutrios/` | Local (`agent_data/nutrios/ranbir/`) | **default** ❌ | 🔧 Rebuild in progress |

### Per-Agent Issues

**GRAILZEE** — Functional, non-standard
- ❌ No `openclaw.json` — uses `exec` tool directly to call Python scripts
- ❌ Data paths hardcoded in `grailzee_common.py`, not env var driven
- ❌ `capabilities/` directory missing from workspace
- Priority: 🟢 Low (works fine, refactor later)

**WATCH-LISTING** — Functional, non-standard
- ❌ Workspace is `watch-listing-workspace/` — should be `skills/watch-listing/`
- ❌ Has a nested `skills/` dir inside the workspace (redundant layer)
- ❌ Tools in `tools/` not `scripts/`
- ✅ Google Drive for input photos is intentional and correct
- Priority: 🟢 Low (works fine, rename workspace later)

**INTAKE** — Functional, minor issue
- ❌ `transactions/` data dir lives inside workspace — should be `agent_data/intake/ranbir/`
- ⚠️ Node.js tools acceptable for Gmail API but not Python standard
- ✅ Writing deals to Google Drive (Ops Agent Data) is intentional for shared access
- Priority: 🟡 Soon (move transactions out of workspace)

**GTD** — Functional, minor issues
- ❌ Workspace is `gtd-workspace/` — should be `skills/gtd/`
- ❌ Data in `gtd-workspace/storage/` — should be `agent_data/gtd/ranbir/`
- ❌ `GTD_STORAGE_ROOT` env var not set in `openclaw.json` — falls back to workspace default
- ❌ Has a nested `skills/gtd/` dir inside workspace (redundant layer)
- ✅ `common.py` with env var pattern is correct — just needs wiring
- Priority: 🟡 Soon

**NUTRIOS** — Rebuild in progress
- ❌ Bot bound to `default` account — should have own token
- ❌ Node.js tools — replacing with Python
- ❌ Old `openclaw.json` still points to Google Drive path
- ✅ Data migrated to `agent_data/nutrios/ranbir/`
- ✅ `openclaw.json.target` ready for new Python build
- Priority: 🔴 Now

---

## Workspace Directory Rationalization

### The Problem
The workspace has grown organically with three different patterns:

```
workspace/
  skills/<agent>/          ← correct pattern (grailzee, nutrios, intake)
  <agent>-workspace/       ← old pattern (watch-listing, gtd)
  <agent>-workspace/
    skills/<agent>/        ← redundant nested skills dir inside workspace
    tools/                 ← should be scripts/
    storage/               ← data mixed with code ❌
  nutrios-workspace/       ← orphan (old Claude Code working dir)
  intake-workspace/        ← orphan (stub, only has AGENTS.md)
  grailzee-cowork/         ← orphan (empty bundle dir)
  listings/                ← orphan (old test listing)
  scripts/                 ← root-level scripts (just a test runner)
  state/                   ← empty
  pipelines/               ← one file, should fold into main workspace
```

### Target State
```
workspace/
  skills/
    grailzee-eval/         ← active agent workspace
    nutrios/               ← active agent workspace (rebuild)
    purchase-intake/       ← active agent workspace
    gtd/                   ← rename from gtd-workspace/
    watch-listing/         ← rename from watch-listing-workspace/
  AGENTS.md, SOUL.md ...   ← main agent workspace files
  AGENT_ARCHITECTURE.md    ← this doc
  memory/                  ← main agent memory
  pipelines/               ← keep (referenced by AGENTS.md)

~/agent_data/
  nutrios/ranbir/          ← ✅ already correct
  gtd/ranbir/              ← needs migration from gtd-workspace/storage/
  intake/ranbir/           ← needs migration from skills/purchase-intake/transactions/
```

### Orphan Dirs to Clean Up
| Directory | Status | Action |
|-----------|--------|--------|
| `nutrios-workspace/` | Old Claude Code working dir, stale Node tools | 🗑️ Delete |
| `intake-workspace/` | Stub, only AGENTS.md, never wired | 🗑️ Delete |
| `grailzee-cowork/` | Empty bundle dir | 🗑️ Delete |
| `listings/` | Old test listing | 🗑️ Delete |
| `state/` | Empty | 🗑️ Delete |
| `scripts/` | Just a test runner script | 🗑️ Fold into root or delete |

### Do NOT Touch Yet
- `gtd-workspace/` — active, rationalize after data migration
- `watch-listing-workspace/` — active, rename after next quiet window

---

### NutriOS Rebuild Checklist
- [ ] New Python scripts in `scripts/`
- [ ] `common.py` with `NUTRIOS_DATA_ROOT` env var
- [ ] Updated `openclaw.json` — absolute paths, Python runtime
- [ ] New bot token via BotFather
- [ ] Root `openclaw.json` — add `nutrios` account + binding
- [ ] Remove NutriOS binding from `default`
- [ ] Restart gateway

### GTD Migration Checklist
- [ ] Move `gtd-workspace/storage/` → `agent_data/gtd/ranbir/`
- [ ] Set `GTD_STORAGE_ROOT=/Users/ranbirchawla/agent_data/gtd/ranbir` in `gtd-workspace/openclaw.json`
- [ ] Rename `gtd-workspace/` → `skills/gtd/`
- [ ] Update root `openclaw.json` agent workspace path
- [ ] Restart gateway

### Intake Migration Checklist
- [ ] Move `skills/purchase-intake/transactions/` → `agent_data/intake/ranbir/`
- [ ] Update any paths in intake SKILL.md or tools
- [ ] Restart gateway

---

## AGENTS.md Boilerplate

Every agent workspace needs an `AGENTS.md` that tells the agent what to
load on startup and what its hard rules are.

```markdown
# AGENTS.md — <Agent Name>

## On Every Startup

Read ONE file only: `SKILL.md`

That file contains the full dispatch logic, capability routing, and all
tool paths. Do not load anything else until SKILL.md directs you to.

## Identity

You are <description>. You respond only to <users>.

## Hard Rules

- Never calculate metrics yourself — always call the Python scripts
- Never make recommendations without running the relevant script first
- Three response types only: result, question, error
- No filler, no preamble, no "I'll now run the script"
- Never expose raw stack traces — surface clean error messages only
```

---

_Last updated: 2026-04-25_
_Owner: main agent — update this doc when architecture changes._
