# AGENT_ARCHITECTURE.md

Canonical reference for OpenClaw runtime agents. Read at the start of any agent design or build session.

---

## Scope

This document covers **OpenClaw runtime agents only**.

It does not cover:

- **Supervisor chats** running design or build phases; see `supervisor-session` skill and `SUPERVISOR_ROLE.md`.
- **Claude Code build agent** structure or invocation conventions; see `CLAUDE.md`.
- **Code-reviewer subagent** behavior; see `Review.md` and any project review-delta.
- **Chat-side skills** outside OpenClaw.

If a question is about how agents run in production under the OpenClaw runtime, this doc answers it. If it is about how we design, build, or operate them at the chat layer, look elsewhere.

---

## How this fits with the canon

| Document | Owns |
|---|---|
| `SUPERVISOR_ROLE.md` + supervisor-session skill | Design and build phase discipline; gates; phase shifts; session closure |
| `CLAUDE.md` | Repo-wide rules: LLM voice, zero-arithmetic, TDD, commit discipline, test invocation, code standards |
| `agent_api_integration_pattern.md` | Plugin wiring mechanics: file layout, tool-schemas, build steps, spawn modes |
| `Review.md` (+ project deltas) | Code review standards applied at gate 2 |
| **This doc** | OpenClaw runtime architecture: agent shape, file layout, prompt assembly, tool surface, observability, data storage |

When this doc and another disagree, the more specific authority wins for its scope. Build execution defers to supervisor-session skill; LLM voice defers to CLAUDE.md; plugin mechanics defer to `agent_api_integration_pattern.md`.

---

## Operating principles

Six load-bearing concepts. Everything else in this doc derives from these.

1. **The LLM's tool surface is the contract.** Whatever the LLM can see, it will reach for. Surface design is the highest-leverage decision in agent architecture.

2. **Structural prevention beats prompt-based prevention.** Rules in the prompt fail under pressure; tools that do not exist cannot be called. When a behavior must not happen, remove the affordance, not just the instruction.

3. **The LLM is a translator, not a calculator.** Values, dates, and structural facts come from tools; the LLM reads them back. This rule lives in `CLAUDE.md` and applies to every agent.

4. **Capability-shaped, not script-shaped.** The tools the LLM sees match user-visible capabilities, not implementation pipeline stages. Pipeline seams in the tool surface produce drift in long sessions.

5. **Born observable.** OTEL traces from the first sub-step. Observability is not added later; it is part of how the agent is built.

6. **Local first for runtime; sync layers for human I/O.** Runtime data lives on the local filesystem. Cloud-synced storage is for files humans drop in or pick up, not for agent writes.

---

## How OpenClaw wires an agent

OpenClaw assembles the system prompt from the agent's workspace at session start. The workspace is named in the root `openclaw.json` under `agents.list[].workspace`.

### System prompt assembly, in order

**Cached prefix** (stable, injected once, cache-persisted):

1. `AGENTS.md` — startup instructions, hard rules, allowed tools
2. `SOUL.md` — persona, tone, voice
3. `TOOLS.md` — local environment notes (paths, device names)
4. `IDENTITY.md` — name, vibe, emoji
5. `USER.md` — user context (name, timezone, preferences)
6. Available skills block — auto-injected from skill registry

**Dynamic suffix** (below cache boundary, injected fresh each turn):

7. `HEARTBEAT.md` — periodic checks; kept small or empty

### Workspace metadata

The workspace `openclaw.json` carries agent-level metadata. It does **not** define tools (see "Plugins, not workspace tools" below). The required fields:

```json
{
  "name": "<agent>",
  "version": "1.0.0",
  "description": "<one line>",
  "session": {
    "dmScope": "per-channel-peer"
  },
  "env": ["<AGENT>_DATA_ROOT", "<AGENT>_TZ"]
}
```

`session.dmScope: "per-channel-peer"` is required for per-user session isolation in DMs. The `env` array declares which environment variables the agent's tools expect; OpenClaw passes them through to plugin script invocations.

### Session routing

Each agent gets a dedicated Telegram bot token and `accountId` in root `openclaw.json`. A `bindings` entry routes that accountId to the agent. The `default` accountId always routes to the `main` agent (operator's direct conversation channel); no other agent is bound to it.

---

## Plugins, not workspace tools (the load-bearing wiring rule)

**Custom tools must be plugins. Workspace `openclaw.json` tool entries are silently dropped by the gateway.** The LLM never sees workspace tool entries unless they are also registered as plugins in root `openclaw.json` under `plugins.entries`.

Plugin registration is the only mechanism that puts a custom tool on the LLM's surface. An agent built without plugins falls back to whatever general-purpose tools remain on its surface, defeating the entire architecture.

### Where the plugin lives

A plugin has its own directory, separate from the agent workspace:

```
plugins/<agent>-tools/
  index.js              ← plugin entry point; registers tools with the SDK
  tool-schemas.js       ← TOOLS array; one entry per tool (name, description, params, _script)
  tools.schema.json     ← generated artifact; run npm run build:schemas
  package.json          ← plugin metadata; declares openclaw.extensions
  openclaw.plugin.json  ← plugin id, name, description
  scripts/
    emit-schemas.js     ← build script

skills/<agent>/scripts/
  <tool_a>.py           ← Python implementation, one file per tool
  <tool_b>.py
  common.py             ← shared constants, data root resolver, utilities
```

Python implementations live in the agent workspace under `skills/<agent>/scripts/`. The plugin directory is the wiring layer only.

### What goes in root openclaw.json

```json
{
  "plugins": {
    "entries": [
      { "id": "<agent>-tools", "path": "plugins/<agent>-tools" }
    ]
  },
  "agents": {
    "list": [
      {
        "id": "<agent>",
        "tools": {
          "deny": ["exec", "group:runtime"]
        }
      }
    ]
  }
}
```

For full plugin mechanics (`_spawn` modes, schema generation, build steps, error patterns), see `agent_api_integration_pattern.md`. That doc is the source of truth for plugin implementation.

---

## Tool surface defense hierarchy

Six layers. Each fails on its own in long sessions; together they hold.

```
1. plugins.entries (root openclaw.json)   ← only mechanism that surfaces tools to the LLM
2. tools.deny in agent entry              ← removes built-ins from the surface (LOCKED default)
3. tools.allow in agent entry             ← optional further narrowing
4. AGENTS.md hard rules                   ← loaded first; sets the frame
5. SKILL.md hard rules                    ← reinforces before dispatch
6. Capability file rules                  ← reinforces at point of use
7. Forensic audit of session logs         ← verifies it all held
```

### tools.deny is the locked default

**Status: LOCKED.** Every new agent has `tools.deny: ["exec", "group:runtime"]` in its agent entry. This removes `exec` and runtime built-ins from the LLM's tool surface entirely.

```json
{
  "id": "<agent>",
  "tools": {
    "deny": ["exec", "group:runtime"]
  }
}
```

The `main` agent is the only exception (operator-supervised; needs general-purpose tools). Every other agent denies exec.

### Why this is structural, not advisory

Capable LLMs are problem-solvers. When given general-purpose execution and a goal they cannot reach cleanly through registered tools, they will use it. Prompt rules alone do not prevent this in long sessions; the LLM drifts, hits an error, reaches for the tool that always works.

The pattern: tool-surface narrowing is a structural fix; prompt-rule reinforcement is at best a complement and at worst a false sense of safety.

### Forensic audit of session logs

Every gate that confirms an agent's behavior also confirms which tools actually fired. A passing test suite with zero registered tool calls in the session log means the agent ran untested code paths. Bot output can look correct while the agent bypassed every registered tool underneath.

A portfolio-level forensic tool reads the agent's session JSONL, classifies each tool call (registered, forbidden, bypass), and outputs a timeline. The supervisor-session skill governs **when** the audit fires (gate 3 release check; every test session; whenever behavior seems off). What matters here: forbidden calls fail the gate regardless of bot output.

---

## Canonical directory layout

```
~/.openclaw/workspace/skills/<agent>/
  AGENTS.md               ← REQUIRED: startup + hard rules + allowed tools
  SKILL.md                ← REQUIRED: intent dispatch + capability routing + hard rules
  SOUL.md                 ← REQUIRED: persona, tone
  TOOLS.md                ← env notes, paths, device names
  IDENTITY.md             ← name, vibe, emoji
  USER.md                 ← user context
  HEARTBEAT.md            ← periodic checks; minimal or empty
  openclaw.json           ← workspace metadata (NOT tool definitions)
  scripts/
    common.py             ← shared constants, data root, utilities
    <capability>.py       ← plugin-registered capability tools (LLM-visible)
    <agent>/              ← internal modules, grouped by domain (NOT plugin-registered)
      <module_a>.py
      <module_b>.py
  capabilities/           ← capability markdown files, if dispatch pattern used
  memory/                 ← daily memory files, YYYY-MM-DD.md

~/agent_data/<agent>/<user.id>/[<identity.id>/]
                          ← ALL runtime data
                          ← Local filesystem only (NEVER cloud-synced storage)
                          ← Identity scoping is a TRIAL pattern; see Multi-identity below

~/.openclaw/agents/<agent>/agent/
  models.json             ← copied from existing agent on setup
  auth-profiles.json      ← '{"version":1,"profiles":{}}'

~/.openclaw/agents/<agent>/sessions/
  sessions.json           ← '{}'
  *.jsonl                 ← session logs; cleared on agent rebuild
```

Notes:

- `skills/` is the workspace root for all agents.
- `agent_data/` is the data root; separate from code.
- Never mix code and data in the same directory.
- `scripts/` not `tools/` (Python convention).
- One `common.py` per agent for shared constants.

---

## Capability-shaped tool surfaces, not script-shaped

**Status: LOCKED.**

The plugin tools the LLM sees match user-visible capabilities, not internal pipeline steps.

**Wrong (script-shaped):** plugin tools mirror the implementation. Imagine a notes agent exposing `parse_input`, `validate_record`, `store_to_disk`. The LLM sees pipeline seams and picks individual stages, bypassing design constraints (calling `store_to_disk` and skipping `validate_record`).

**Right (capability-shaped):** plugin tools match what the user does. The same notes agent exposes `add_note`, `find_notes`, `summarize_notes`. The pipeline (`parse_input`, `validate_record`, `store_to_disk`) becomes Python modules under `scripts/<agent>/`, imported by the capability tools.

### File layout

```
scripts/
  common.py
  add_note.py             ← plugin entry; LLM-visible
  find_notes.py           ← plugin entry; LLM-visible
  summarize_notes.py      ← plugin entry; LLM-visible
  <agent>/                ← internal modules; not plugin-registered
    parse.py
    validate.py
    store.py
```

Internal modules are imported by capability scripts. They are not registered as plugins; they never appear on the LLM's tool surface; they run in-process (preserves OTEL span continuity vs subprocess fragmentation).

### Why this is locked

Tool-choice ambiguity in long sessions produces drift. The smaller and more obvious the LLM's surface, the more reliably it picks the right tool. Capability shape is also where capability gaps go visible: if a legacy implementation lacks an operation and its surface migrates as-is, the gap ships invisibly. Designing the capability surface forces gaps into the open.

---

## scripts/common.py — shared constants pattern

Every agent has a `common.py` that owns paths, the data root, and shared utilities. The data root always comes from an env var with a local fallback.

```python
"""Shared constants and utilities for <Agent Name>."""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime
import zoneinfo

# Data root. Set <AGENT>_DATA_ROOT in openclaw.json env or shell.
# Default is local agent_data; never cloud-synced storage.
DATA_ROOT = os.environ.get(
    "<AGENT>_DATA_ROOT",
    f"{os.path.expanduser('~')}/agent_data/<agent>/default"
)

AGENT_TZ = os.environ.get("<AGENT>_TZ", "America/Denver")

# Derived paths
LOGS_PATH  = f"{DATA_ROOT}/logs"
STATE_PATH = f"{DATA_ROOT}/state"

def today_str(tz: str = AGENT_TZ) -> str:
    """Return today's date as YYYY-MM-DD in the agent timezone."""
    return datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")

def read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def write_json(path: str, data: dict, indent: int = 2) -> None:
    """Atomic write with .bak backup."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bak = path + ".bak"
    if os.path.exists(path):
        os.replace(path, bak)
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
```

### Tool script pattern (Python implementation)

```python
#!/usr/bin/env python3
"""<tool_name> — <one line description>."""

from __future__ import annotations
import json, sys, os

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, ok, err, read_json, write_json

def main():
    try:
        params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        err(f"Invalid JSON input: {e}")
        return

    # ... tool logic ...

    ok(result)

if __name__ == "__main__":
    main()
```

For `_spawn: argv` (standard) the script reads `sys.argv[1]`; for `_spawn: stdin` (rare) it reads stdin. See `agent_api_integration_pattern.md` for spawn mode selection.

---

## Date sourcing pattern

Every agent that reasons about "today" needs the date in the user's timezone, sourced consistently and on demand.

### The primitive

`common.today_str(tz=AGENT_TZ)` returns `YYYY-MM-DD` in the agent timezone. Every date-related tool calls this utility. No agent code calls `datetime.now()` or instantiates `ZoneInfo` directly outside `common.py`.

### The plugin tool

A no-input plugin tool wraps `today_str()`:

```python
#!/usr/bin/env python3
"""get_today_date — today's date in agent timezone."""
from __future__ import annotations
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from common import ok, today_str

def main():
    ok({"date": today_str()})

if __name__ == "__main__":
    main()
```

Registered in `tool-schemas.js` with empty params (timezone is environment-driven, not user-supplied).

### The rule for capability prompts

Every capability that needs a date calls `get_today_date` every turn that needs one. The capability prompt makes this explicit:

- Never cache a date across turns.
- Never infer a date from message context, prior responses, or what the LLM remembers from earlier in the session.
- Never compute a date by adding days to a known date.
- Tool failure surfaces to the user as a tool failure. No inferred fallback; no estimation; no best guess.

This rule lives in the *Hard Rules* section of any capability that touches dates, as the lead no-fabrication entry.

### Why this is absolute

Date fabrication is among the most expensive single errors an agent can make. Downstream calculations, reconciliations, and "what's left for today" answers all anchor on the date. A wrong date silently corrupts every subsequent answer until the user notices. The cost is paid by the human, not by the agent.

### Wiring checklist

For any new agent that reasons about today:

- [ ] `today_str()` and `AGENT_TZ` in `common.py`
- [ ] `scripts/get_today_date.py` wrapping `today_str()`
- [ ] `tool-schemas.js` entry registering the plugin tool
- [ ] Capability prompt rule: every date-needing capability includes the no-cache, no-infer, no-compute rule
- [ ] Tests: clock-mocked unit tests on `today_str()`; functional tests on the plugin tool

---

## Root openclaw.json — agent registry

Every new agent needs three entries.

### 1. Agent entry in `agents.list`

```json
{
  "id": "<agent>",
  "name": "<agent>",
  "workspace": "~/.openclaw/workspace/skills/<agent>",
  "agentDir": "~/.openclaw/agents/<agent>/agent",
  "model": "<production-sonnet-model>",
  "tools": {
    "deny": ["exec", "group:runtime"]
  }
}
```

The exact model string is configuration; it lives here, not in this doc. Update at the agent registry when the production model line advances.

### 2. Telegram account in `channels.telegram.accounts`

```json
"<agent>": {
  "botToken": "<BOT_TOKEN_FROM_BOTFATHER>",
  "dmPolicy": "open",
  "groupPolicy": "allowlist",
  "groups": {
    "<group-id>": { "policy": "allow", "requireMention": false }
  }
}
```

`requireMention: false` is the correct field for groups, not `mentionOnly`. Group IDs go under `groups`, not `groupAllowFrom`.

### 3. Binding in `bindings`

```json
{
  "type": "route",
  "agentId": "<agent>",
  "match": { "channel": "telegram", "accountId": "<agent>" }
}
```

### The `default` accountId

The `default` Telegram account always routes to `main` (operator's direct conversation channel). No functional agent is bound to it.

### Group ID gotcha

When a bot is made admin in a Telegram group, the group upgrades to a supergroup and gets a new chat ID (negative; starts with `-100`). Re-allowlist the new ID. A bot added to a group with default permissions has no access to messages; admin or explicit read access is required.

---

## Model selection

### Outer model

The outer LLM (the agent itself) runs the production strong-general-purpose model by default. Use a smaller model only for high-volume, simple extraction or routing where judgment is not required.

| Use case | Outer model class |
|---|---|
| Judgment, recommendations, complex logic | Strong general-purpose (e.g., Sonnet) |
| High-volume routing, simple extraction | Smaller fast model (e.g., Haiku) |

Exact model strings live in the agent registry config. They update when the production model line advances. The doc names classes; the registry names versions.

### Inner model role-based routing — TRIAL

**Status: TRIAL.**

When a capability tool calls an inner LLM (for classification, normalization, structured extraction inside the tool's execution), the inner call uses a smaller or open-weight model with a strong-model fallback on validation failure.

| Layer | Primary model class | Fallback |
|---|---|---|
| Outer (agent) | Strong general-purpose | none |
| Inner (capability internals) | Smaller / open-weight | Strong general-purpose on validation failure |

**Promotion criteria:** a second agent with inner LLM calls confirms the outer/inner split works without surprises and the smaller primary holds quality at temperature=0.

### Temperature=0 for inner calls

**Status: LOCKED.** All inner LLM calls run at temperature=0 for determinism. LLM tests pin model and temperature to match production (see CLAUDE.md §Test conditions match production conditions). Tests run 3x with require-all-pass; flakiness at temperature=0 indicates an undertested capability or a brittle assertion.

---

## Observability — OTEL native day-one

**Status: LOCKED.**

Every new agent emits OpenTelemetry traces from the first sub-step. Observability is not added later; agents are born observable.

### Configuration

- **Processor:** `SimpleSpanProcessor`. Not `BatchSpanProcessor`. Latency hides bugs in development; deterministic flush is required.
- **Endpoint:** local OTEL collector on the development host (default OTLP/HTTP endpoint). The collector forwards to the project's chosen tracing backend; the backend choice is configuration, not architecture.
- **Service name:** matches the agent id.

### Span hierarchy

Capability tools emit a parent span. Internal modules called by the capability emit child spans under it.

```
<capability_tool> (parent)
├── <internal_module_a> (child)
├── <internal_module_b> (child)
└── <internal_module_c> (child)
```

This is why internal modules are function imports, not subprocesses; subprocess invocation fragments the trace.

### What gets attributed

Standard span attributes per capability tool, agreed at design phase:

- `agent.id`, `user.id`, `identity.id` (where applicable)
- Capability-specific inputs and outputs (truncated for PII)
- Inner LLM call metadata (model, latency, validation result) when applicable

Span attribute conventions are agreed at design phase and locked into the design doc before build opens.

---

## Multi-identity model — TRIAL

**Status: TRIAL.** Pattern applies only to agents that touch services authenticated against multiple credentials per user (multiple email accounts, multiple OAuth tokens). Single-credential agents do not need this.

### The two-level model

```
~/agent_data/<agent>/<user.id>/<identity.id>/
                                              storage, state, logs
```

- **User-level data** (records, lists, content) lives at `<user.id>/`. One human, one set of records. Identity does not split user data.
- **Identity-level credentials** (OAuth tokens, per-account state) live at `<identity.id>/`. One token per credential domain.

Identity slugs are short, lowercase strings naming the credential domain (e.g., `work`, `personal`).

When a service is single-account-per-human (one account per user, regardless of identity), it stays user-level and its tools take no `identity` parameter.

**Promotion criteria:** a second agent demonstrates real multi-identity need (more than one OAuth token per user); the two-level model holds without surprise.

---

## Memory proxy bypass for inner LLM calls — TRIAL (workaround)

**Status: TRIAL, workaround.** When the agent runs behind a memory-proxy layer (persistent LLM memory between agent and provider API), inner LLM calls bypass the proxy until proxy-side inner-call routing is reliable.

```
Outer call:  agent → memory proxy → provider API
Inner call:  agent → provider API   (proxy bypassed)
```

**Promotion criteria:** the underlying proxy issue is resolved; bypass is no longer needed; pattern restates as "all calls through the memory proxy."

---

## Data storage rules

| Rule | Detail |
|---|---|
| **Local only for runtime** | All runtime data in `~/agent_data/<agent>/<user>/[<identity>/]`. Never cloud-synced storage. |
| **Cloud sync for human I/O only** | Files humans drop in or pick up (reports, photos, invoices). Read-only from agents in most cases. |
| **No hardcoded paths** | Always env var → `common.py` → scripts. Path strings never appear in tool scripts. |
| **Atomic writes** | `os.replace()` with `.bak` backup. Use `write_json()` from `common.py`. |
| **No secrets in workspace** | Bot tokens live in root `openclaw.json` only. OAuth credentials live under `~/.openclaw/credentials/<user>/<identity>/`. |
| **Session state writes to disk** | Any cross-turn state writes to a JSON file in `agent_data/`. Never rely on in-session memory. |

### Why no cloud-synced storage for runtime data

Sync conflicts (two clients writing the same file mid-sync produces a `.conflict` copy and silent data loss); permission propagation lag (a write succeeds locally but fails to sync for minutes); operating-system file-permission edge cases (e.g., macOS Full Disk Access). Cloud sync is fine for human-touched I/O where conflicts are rare and obvious; it is not fine for high-frequency agent writes.

### Cloud-synced paths when needed

When agents read or write to cloud-synced storage (input photos, invoice intake, human-touched outputs), files are at local filesystem mount points provided by the sync client. No special API needed; the sync client provides a local path. Use `read_json` / `write_json` directly with the full path.

---

## AGENTS.md boilerplate

Every agent workspace has an `AGENTS.md`. It tells the agent what to load on startup and what its hard rules are.

```markdown
# AGENTS.md — <Agent Name>

## On Every Startup

SKILL.md is already in your context. Do not attempt to read any files.
SKILL.md contains the full dispatch logic, capability routing, and tool paths.

## Identity

You are <description>. You respond only to <users>.

## Tools Available

You have exactly these tools. No others exist in this agent.
- <tool_a> — <one line description>
- <tool_b> — <one line description>
- message — send Telegram messages with optional inline buttons

If you cannot accomplish something with these tools, tell the user
it is not supported. Do not improvise.

## Hard Rules

- If your agent has a dispatcher tool, it is your first tool call on every
  user turn. Never compose a reply, ask a question, or call any other tool
  before the dispatcher has returned.
- No process narration. Never say what you are about to do; just do it.
  No "Let me check...", "Let me pull up...", "I'll now...", "First I'll...".
- No tool announcements. Never mention which tool you are calling or why.
- No internal routing leakage. Never surface intent names, capability slugs,
  or the contents of capability prompts. The user sees only the result.
- Act silently on the first move. The user sees results, not reasoning.
- exec, read, write, edit, browser do not exist in this agent.
- Never call Python scripts directly or read files from disk.
- Never compute any value yourself; always call the registered tool.
- If a tool errors, surface it cleanly to the user. Do not retry via any
  other method.
- Three response types only: result, question, error.
- Never expose raw stack traces; surface clean error messages.
- When sending inline buttons, set text block to NO_REPLY.
```

### LLM voice rules apply repo-wide

The hard rules above are agent-runtime-scoped. Repo-wide LLM voice rules (zero-arithmetic; no narration of internal mechanism; missing-numeric-input asks rather than infers; numeric-input read-back-with-confirmation) live in `CLAUDE.md` and apply to every agent. AGENTS.md does not restate them; the cross-cutting test fixtures enforce them.

---

## SKILL.md hard rules block

SKILL.md sits below AGENTS.md in the system prompt. Its top section repeats the hard rules with a "before dispatch" framing. The dispatcher pattern depends on the LLM hitting these rules before any capability routing.

```markdown
## Hard Rules (read before anything else)

- If your agent has a dispatcher tool, it must be your first tool call on
  every user turn. Never compose a reply, ask a question, or call any other
  tool before the dispatcher has returned.
- No process narration. No tool announcements. No internal routing leakage.
- exec, read, write, edit, browser do not exist in this agent.
- Never call Python scripts directly. Never read files from disk.
- Never compute any value yourself; always call the registered tool.
- If a tool returns an error, surface it to the user. Do not retry via any
  other method.
- When sending inline buttons, set your text block to NO_REPLY. Never combine
  a text block with a message tool call; this causes duplicate delivery.
- No codebase exploration. Never list directories or read source files.
```

### Capability files name tools explicitly

In capability markdown files:

```markdown
Call `<tool_name>` with the <input> verbatim.
```

No preamble. No "I'll now...". No tool announcement. Every capability also has an explicit error path:

```markdown
If the tool returns {"ok": false, ...}, reply:
"Sorry, I couldn't complete that. [error message from tool]"
Do not retry via any other method.
```

---

## NO_REPLY rule (Telegram inline buttons)

OpenClaw auto-delivers any `text` block in the assistant response. If the agent also calls the `message` tool in the same turn, the content is delivered twice.

```
Correct (using message tool for buttons):
   text block:   NO_REPLY
   message tool: "<reply text>" + buttons

Wrong (causes duplicate):
   text block:   "<reply text>"   ← auto-delivered
   message tool: "<reply text>"   ← also delivered
```

Rule: when the `message` tool delivers the reply, the text block is `NO_REPLY`.

---

## New agent setup checklist

For each new agent. Setup is mechanical; supervisor does not run it (the chat builds the prompt; Code executes).

- [ ] Create `~/.openclaw/agents/<agent>/agent/` directory
- [ ] Copy `models.json` from an existing agent
- [ ] Create `auth-profiles.json`: `echo '{"version":1,"profiles":{}}' > ~/.openclaw/agents/<agent>/agent/auth-profiles.json`
- [ ] Create `~/.openclaw/agents/<agent>/sessions/` with `echo '{}' > sessions.json`
- [ ] Create workspace at `~/.openclaw/workspace/skills/<agent>/` with focused `AGENTS.md`, `SKILL.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, workspace `openclaw.json` (metadata only)
- [ ] Create plugin directory at `plugins/<agent>-tools/` per `agent_api_integration_pattern.md`
- [ ] Add agent to `agents.list` in root `openclaw.json` with `tools.deny: ["exec", "group:runtime"]`
- [ ] Add plugin to `plugins.entries` in root `openclaw.json`
- [ ] Add Telegram account to `channels.telegram.accounts` (new bot token from BotFather)
- [ ] Add binding in `bindings`
- [ ] Add group IDs to `groups` if group chat is in scope
- [ ] Clear stale sessions: `rm -f ~/.openclaw/agents/<agent>/sessions/*.jsonl`
- [ ] Restart gateway

---

## Verification before any agent goes to real users

- [ ] Plugin registered in root `openclaw.json` under `plugins.entries`
- [ ] `tools.deny: ["exec", "group:runtime"]` in agent entry
- [ ] Dedicated bot token; binding routes accountId to agent (not `default`)
- [ ] `auth-profiles.json` exists in agent directory; sessions cleared
- [ ] Unit tests pass (`make test-<agent>`)
- [ ] LLM tests pass (`make test-<agent>-llm`)
- [ ] Bot output looks correct in manual smoke test
- [ ] Forensic audit of latest session shows zero forbidden calls
- [ ] Every expected registered tool appears in the audit timeline
- [ ] OTEL traces visible in the tracing backend with parent-child span structure intact

---

## Pattern lock status summary

| Pattern | Status | Promotion criteria |
|---|---|---|
| Plugin registration over workspace tool entries | LOCKED | n/a |
| `tools.deny: ["exec", "group:runtime"]` default | LOCKED | n/a |
| Capability-shaped tool surfaces | LOCKED | n/a |
| Temperature=0 for inner LLM calls | LOCKED | n/a |
| OTEL native day-one (SimpleSpanProcessor) | LOCKED | n/a |
| Date sourcing via `get_today_date` plugin tool | LOCKED | n/a |
| Atomic writes via `common.write_json` | LOCKED | n/a |
| NO_REPLY rule for Telegram inline buttons | LOCKED | n/a |
| Two-level multi-identity model (`<user.id>/<identity.id>`) | TRIAL | Second agent demonstrates real multi-identity need; model holds without surprise |
| Role-based outer/inner model routing with strong-model fallback | TRIAL | Second agent with inner LLM calls confirms split works at temperature=0 |
| Memory proxy bypass for inner LLM calls | TRIAL (workaround) | Underlying proxy issue resolved; bypass removed; pattern restates as "all calls through the memory proxy" |

---

_Owner: this doc updates when architecture canon changes. Trial patterns elevate to LOCKED via supervisor session decision-reasoning doc; the lock entry replaces the trial entry in the table above._
