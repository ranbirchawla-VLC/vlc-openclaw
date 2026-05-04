# AGENT_ARCHITECTURE.md

Canonical reference for OpenClaw runtime agents. Read at the start of any agent design or build session.

## Scope

This doc owns OpenClaw runtime agent architecture: agent shape, file layout, prompt assembly, tool surface, observability, data storage.

It does not own:

- Supervisor chat behavior; see `supervisor-session` skill
- Build agent execution; see `CLAUDE.md`
- Plugin wiring mechanics; see `agent_api_integration_pattern.md`
- Code review standards; see `Review.md`

When this doc and another disagree, the more specific authority wins for its scope.

## Read order

| Phase | Required sections |
|---|---|
| Design (chat, before build) | First decision; Locked patterns 1-10; TRIAL patterns |
| Build (Claude Code) | Locked patterns 1-10; Reference |
| Setup (mechanical) | Reference: setup checklist; Reference: pre-release verification |

## First decision: single-mode or multi-mode

Every new agent is one or the other. This decision precedes every other design decision.

**Single-mode.** One operational mode. Capability instructions live in `SKILL.md`. `SKILL.md` is in context at session start.

**Multi-mode.** Two or more operational modes with distinct instructions. Capability instructions live on disk in `capabilities/<intent>.md`. A dispatcher tool injects the right capability into context at the start of every turn.

Decision rule: if the agent has more than one set of instructions the user can invoke, it is multi-mode. No exceptions.

Drift indicator: a single-mode agent gains a second mode mid-build. Halt; reopen design phase; convert to multi-mode before continuing.

---

## LOCKED PATTERNS

Each pattern: rule, drift indicator, halt action, reference implementation pointer.

### 1. Multi-mode dispatcher (turn_state)

**Rule.** Multi-mode agents use a `turn_state` plugin tool called first on every turn. The tool classifies intent, reads the matching capability file from disk fresh each call, and returns `{intent, capability_prompt}`. The agent follows `capability_prompt`.

**Structural enforcement.** AGENTS.md PREFLIGHT block: "Before every response, call `turn_state` with the verbatim user message. No response before turn_state completes."

**Capability files.** On disk at `capabilities/<intent>.md`. Read fresh every call; no caching. Editing a capability file takes effect on the next turn.

**Classifier strategy.** Slash commands first; signal-based detection second (e.g., `$` for prices); keyword fallback last; everything else returns empty `capability_prompt` and a one-line help reply.

**Drift indicators:**
- Agent responds to a turn without a `turn_state` call in the tool log
- Capability file edits don't take effect; suspect caching
- Agent invokes the wrong capability for an obvious intent; suspect classifier coverage

**Halt action.** Missing dispatcher or weak PREFLIGHT: halt; reopen design phase; do not proceed to capabilities.

**Reference.** `skills/grailzee-eval/scripts/turn_state.py`; `skills/grailzee-eval/AGENTS.md` PREFLIGHT block.

### 2. OTEL cross-process propagation

**Rule.** Every plugin wraps each `execute()` in `tracer.startActiveSpan()`. The span's traceparent is injected into the Python subprocess via `TRACEPARENT` env var in `SPAWN_ENV`. Python scripts attach the parent context with `attach_parent_trace_context()` before starting their top-level span.

**Why structural.** `diagnostics-otel` does not propagate context across the plugin-to-subprocess boundary. It uses passive `startSpan()` with backdated start times; no span is active when `execute()` runs. There is nothing to inherit. Every plugin must create its own active spans.

**Two-process model:**
- Node plugin process emits parent span; service name `openclaw-gateway`
- Python subprocess emits child span; service name from `OTEL_SERVICE_NAME` in `SPAWN_ENV`
- Internal Python modules emit grandchild spans via in-process imports (function imports, not subprocess spawns)

**Span attribute contract.** Decided at design phase; locked in design doc before build opens. Attributes make routing and outcomes queryable in production. Canonical dispatcher attributes: `intent`, `capability_file`, `capability_loaded`.

**Drift indicators:**
- Python span lands as trace root in Honeycomb with "missing parent span" in waterfall
- Plugin uses `startSpan` instead of `startActiveSpan`; traceparent injection returns random fallback bytes
- Trace shows fragmented spans across what should be one tool invocation

**Halt action.** Missing parent context attachment is a build-breaking gap; fix before declaring tool complete. Span attribute set incomplete or wrong shape: halt; revisit design.

**Reference.** `plugins/grailzee-eval-tools/index.js`; `skills/grailzee-eval/scripts/grailzee_common.py` (`attach_parent_trace_context`).

**Note.** Patterns 1 and 2 travel together for multi-mode agents. The dispatcher provides the structural anchor; OTEL provides the verification surface. PREFLIGHT closes the prompt-side gate; span attributes close the observability-side gate.

### 3. Plugin registration

**Rule.** Custom tools must be plugins. Workspace `openclaw.json` tool entries are silently dropped by the gateway. The LLM never sees a tool unless it is registered as a plugin in root `openclaw.json` under `plugins.entries`.

**Drift indicator.** Tool defined in workspace `openclaw.json` and not in root; LLM never calls it; agent falls back to general-purpose tools.

**Halt action.** Move tool definition to plugin; register in root; verify via session log.

### 4. Tool surface deny defaults

**Rule.** Every agent except `main` has `tools.deny: ["exec", "group:runtime"]` in its agent entry. This removes general-purpose execution from the LLM's surface.

**Drift indicator.** Agent succeeds via exec when registered tools should have been used; session log shows exec bypass. Canonical failure: NutriOS v2 incident, 45 exec bypasses in one session.

**Halt action.** Add deny; restart gateway; re-test.

### 5. Capability-shaped tool surfaces

**Rule.** Plugin tools match user-visible capabilities, not pipeline stages. `add_note`, `find_notes`, `summarize_notes`; not `parse_input`, `validate_record`, `store_to_disk`. Pipeline implementation lives in internal Python modules under `scripts/<agent>/`, imported by capability scripts.

**Drift indicator.** Tool name names a verb-on-data step rather than a user action. LLM picks individual stages and bypasses design constraints.

**Halt action.** Halt; redesign tool surface; capabilities first, internals second.

### 6. Date sourcing

**Rule.** Every agent that reasons about "today" calls `get_today_date` plugin tool every turn that needs a date. No caching across turns; no inferring from message context; no computing by adding days; no fallback estimation.

**Drift indicator.** Capability prompt missing the no-cache/no-infer/no-compute block; tool log shows date used without a `get_today_date` call.

**Halt action.** Add the rule to capability prompt; add `get_today_date.py` and registration; re-test.

### 7. Local-only runtime data

**Rule.** All runtime data lives at `~/agent_data/<agent>/<user.id>/[<identity.id>/]` on local filesystem. Cloud-synced storage is for human-touched I/O only (files dropped in or picked up).

**Drift indicator.** Agent writes high-frequency state to a cloud-synced path; sync conflicts produce `.conflict` files and silent data loss.

**Halt action.** Move runtime data to local path; restore from `.bak` if available; add to KNOWN_ISSUES if data was lost.

### 8. Atomic writes

**Rule.** All JSON writes go through `common.write_json()` which uses `os.replace()` and writes a `.bak` copy. Direct file writes are not permitted.

### 9. Temperature=0 for inner LLM calls

**Rule.** All inner LLM calls (capability internals; classification; structured extraction) run at temperature=0. Tests pin model and temperature to match production. Tests run 3x with require-all-pass.

### 10. NO_REPLY for Telegram inline buttons

**Rule.** When the `message` tool delivers content with inline buttons, the assistant text block is `NO_REPLY`. OpenClaw auto-delivers the text block; combining a text block with a `message` tool call causes duplicate delivery.

---

## TRIAL PATTERNS

Not yet authority. Do not recommend in design without explicit operator approval. Promotion to LOCKED requires a supervisor session decision-reasoning doc.

### Multi-identity model

Two-level data path: `~/agent_data/<agent>/<user.id>/<identity.id>/`. Applies only to agents touching multiple credentials per user (multiple email accounts, multiple OAuth tokens). Single-credential services stay user-level and take no `identity` parameter.

Promotion: a second agent demonstrates real multi-identity need; model holds without surprise.

### Inner LLM role-based routing

Outer model strong general-purpose; inner model smaller or open-weight with strong-model fallback on validation failure.

Promotion: a second agent with inner LLM calls confirms the split holds quality at temperature=0.

### Memory proxy bypass for inner calls

Inner LLM calls bypass the memory proxy until proxy-side inner-call routing is reliable.

Promotion: underlying proxy issue resolved; bypass removed; pattern restates as "all calls through the memory proxy."

---

## REFERENCE

### Directory layout

```
~/.openclaw/workspace/skills/<agent>/
  AGENTS.md
  SKILL.md
  SOUL.md, IDENTITY.md, USER.md, TOOLS.md, HEARTBEAT.md
  openclaw.json                 (workspace metadata; not tool definitions)
  scripts/
    common.py
    <capability>.py             (plugin-registered; LLM-visible)
    <agent>/
      <internal_module>.py      (imported by capability scripts; not plugin-registered)
  capabilities/<intent>.md      (multi-mode only)
  memory/YYYY-MM-DD.md

~/agent_data/<agent>/<user.id>/[<identity.id>/]
                                Local only; never cloud-synced

~/.openclaw/agents/<agent>/agent/
  models.json
  auth-profiles.json

~/.openclaw/agents/<agent>/sessions/
  sessions.json
  *.jsonl
```

### System prompt assembly order

Cached prefix (stable, injected once): AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, available skills block.
Dynamic suffix (fresh each turn): HEARTBEAT.md (small or empty).

### AGENTS.md skeleton

```markdown
# AGENTS.md: <Agent Name>

## On Every Startup

SKILL.md is already in your context. Do not attempt to read any files.

## Identity

<one line>

## Tools Available

- <tool_a>
- <tool_b>
- message

## Hard Rules

- exec, read, write, edit, browser do not exist in this agent
- Never call Python scripts directly or read files from disk
- Never compute any value yourself; always call the registered tool
- Three response types only: result, question, error
- When sending inline buttons, set text block to NO_REPLY
- No process narration, no tool announcements, no internal routing leakage
```

### Multi-mode addition: PREFLIGHT block

```markdown
## PREFLIGHT

Before every response, call `turn_state` with the verbatim user message.
Read `capability_prompt` from the response. If non-empty, it contains your
complete instructions for this turn. Follow them exactly. If empty, reply
with one line naming the available commands.

No response before turn_state completes.
```

### Code skeletons

Code skeletons live in `agent_api_integration_pattern.md`:

- `common.py` (DATA_ROOT, AGENT_TZ, today_str, read_json, write_json, ok, err, `attach_parent_trace_context`)
- Plugin entry (`index.js`) with OTEL `startActiveSpan` wrapping, `SPAWN_ENV`, `TRACEPARENT` injection
- Python tool script shape with `attach_parent_trace_context` comma-form

Build prompts cite that doc for Code; chat does not load it.

### Root openclaw.json entries

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
        "workspace": "~/.openclaw/workspace/skills/<agent>",
        "agentDir": "~/.openclaw/agents/<agent>/agent",
        "model": "<production-sonnet-model>",
        "tools": { "deny": ["exec", "group:runtime"] }
      }
    ]
  },
  "channels": {
    "telegram": {
      "accounts": {
        "<agent>": {
          "botToken": "<BOT_TOKEN>",
          "dmPolicy": "open",
          "groupPolicy": "allowlist",
          "groups": {
            "<group-id>": { "policy": "allow", "requireMention": false }
          }
        }
      }
    }
  },
  "bindings": [
    { "type": "route", "agentId": "<agent>",
      "match": { "channel": "telegram", "accountId": "<agent>" }}
  ]
}
```

The `default` accountId always routes to `main`. No functional agent is bound to it.

### Setup checklist

- [ ] Create `~/.openclaw/agents/<agent>/agent/` directory
- [ ] Copy `models.json` from existing agent
- [ ] Create `auth-profiles.json`: `echo '{"version":1,"profiles":{}}' > ...`
- [ ] Create `~/.openclaw/agents/<agent>/sessions/` with `echo '{}' > sessions.json`
- [ ] Create workspace at `~/.openclaw/workspace/skills/<agent>/` with focused AGENTS.md, SKILL.md, SOUL.md, IDENTITY.md, USER.md, TOOLS.md, workspace `openclaw.json`
- [ ] Create plugin directory at `plugins/<agent>-tools/`
- [ ] Add agent to `agents.list` in root `openclaw.json` with `tools.deny`
- [ ] Add plugin to `plugins.entries`
- [ ] Add Telegram account; new bot token from BotFather
- [ ] Add binding
- [ ] Add group IDs to `groups` if group chat is in scope
- [ ] Clear stale sessions: `rm -f ~/.openclaw/agents/<agent>/sessions/*.jsonl`
- [ ] Restart gateway

### Pre-release verification

- [ ] Plugin registered in root `openclaw.json` under `plugins.entries`
- [ ] `tools.deny: ["exec", "group:runtime"]` in agent entry
- [ ] Dedicated bot token; binding routes accountId to agent (not `default`)
- [ ] `auth-profiles.json` exists; sessions cleared
- [ ] Unit tests pass (`make test-<agent>`)
- [ ] LLM tests pass (`make test-<agent>-llm`)
- [ ] Manual smoke test passes
- [ ] Forensic audit shows zero forbidden calls
- [ ] Every expected registered tool appears in audit timeline
- [ ] Honeycomb shows complete parent-child trace with required span attributes

### Group ID gotcha

When a bot becomes group admin, the group upgrades to a supergroup with a new chat ID (negative; starts with `-100`). Re-allowlist the new ID. Bots without admin or explicit read access cannot read group messages.

---

## PATTERN LOCK STATUS

| Pattern | Status |
|---|---|
| 1. Multi-mode dispatcher (turn_state) | LOCKED |
| 2. OTEL cross-process propagation | LOCKED |
| 3. Plugin registration | LOCKED |
| 4. Tool surface deny defaults | LOCKED |
| 5. Capability-shaped surfaces | LOCKED |
| 6. Date sourcing via plugin tool | LOCKED |
| 7. Local-only runtime data | LOCKED |
| 8. Atomic writes via common.write_json | LOCKED |
| 9. Temperature=0 inner calls | LOCKED |
| 10. NO_REPLY for inline buttons | LOCKED |
| Multi-identity model | TRIAL |
| Inner LLM role-based routing | TRIAL |
| Memory proxy bypass | TRIAL (workaround) |

Trial patterns elevate to LOCKED via supervisor session decision-reasoning doc; the lock entry replaces the trial entry.

---

_Owner: this doc updates when architecture canon changes._
