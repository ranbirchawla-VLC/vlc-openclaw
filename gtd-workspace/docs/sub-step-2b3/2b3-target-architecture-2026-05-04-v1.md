# 2b.3 Target Architecture

**Date:** 2026-05-04
**Phase:** Design (Layer 2 closure)
**Status:** Locked
**Inputs:** Layer 1 outcomes (seven user, seven tech; chat-approved 2026-05-04); soul anchor v2 (`2b3-soul-anchor-2026-05-04-v2.md`); audit findings (`2b3-audit-2026-05-04.md`, `2b3-soul-identity-audit-2026-05-04.md`); deal.md capability file template; AGENT_ARCHITECTURE locked patterns 1-10 plus TRIAL set.

**Scope:** The agent shape Trina runs in v2 once 2b.3 closes. Layer 3 (API design detail) opens against this lock.

---

## Mode lock

Multi-mode dispatcher (locked pattern 1). Capability instructions live on disk at `capabilities/<intent>.md`; turn_state plugin tool reads them fresh per turn. The conversion from v1 (single-mode pipeline-style) to v2 (multi-mode dispatcher) is the substantive shape of 2b.3.

## Architectural decisions

### 1. Classifier architecture: Python signal-plus-keyword, inner LLM fallback, empty capability_prompt floor

Three layers in order. Each turn:

1. Python signals and keyword detection in turn_state. Deterministic; cheap; covers the high-confidence cases.
2. On miss: inner LLM classification call at temperature=0. One Sonnet call; structured JSON return; bounded vocabulary (the six intents plus the negative-path token).
3. On miss again, or on negative-path token: empty capability_prompt; LLM produces conversational reply in inward Trina voice. No tool dispatch.

**Pattern lock change.** "Inner LLM role-based routing" promotes from TRIAL to LOCKED for Trina specifically. AGENT_ARCHITECTURE update lands at 2b.3 sub-step close. Doc-level promotion (across all agents) is a separate decision; not bundled.

**Latency posture.** Inner LLM call on classifier-miss turns adds latency. `openclaw-latency-playbook.md` gates the budget review at build. Architecture accepts the cost; user outcome 1 (capture without ceremony) tolerates a small wait on ambiguous turns better than it tolerates dropped captures or wrong dispatch.

### 2. Multi-user data architecture: thin USER.md template plus per-user profile

USER.md at workspace root becomes thin template and schema. Cached prefix; shape is uniform across the family. Per-user truth lives at `agent_data/gtd/<user.id>/profile.json` per locked pattern 7. Fields: name, call_them, pronouns, timezone, gtd_maturity, areas of focus, delegation contacts.

A `user_context` helper (Python; small) reads profile.json on demand. Capabilities import it when they need profile fields; not every capability does. Layer 3 lists which.

USER.md as currently written (Ranbir-specific) is replaced. The schema-and-defaults shape goes in.

### 3. Negative-path enforcement: prompt plus tests, not runtime structural

Prompt-side: PREFLIGHT block enforces "no response before turn_state completes;" empty capability_prompt produces conversational reply with no tool call. Test-side: LLM tests assert zero tool calls across a corpus of negative-path inputs at temperature=0, 3x require-all-pass.

Structural enforcement (dynamic tools.deny on empty intent) considered; rejected. Runtime cost exceeds the determinism win at temperature=0; if determinism breaks, structural enforcement does not save the agent because the broken determinism is itself the bug.

Tech outcome 4 mechanically guaranteed by determinism plus test coverage.

## Smaller decisions confirmed

| Decision | Resolution |
|---|---|
| Tool naming | Rename `capture_gtd` to `capture`; rename `review_gtd` to `review`. Aligns plugin to locks ledger. |
| Delegation | Remove from `tool-schemas.js`; delete `scripts/gtd/delegation.py`. Surface stays clean per D-D. |
| Outward guardrails | Section header in AGENTS.md authored now; inert until outward surface opens. |
| Capability file layout | Six files at `capabilities/<intent>.md`: `capture`, `query_tasks`, `query_ideas`, `query_parking_lot`, `review`, `calendar_read`. |

## Final tool surface

| Tool | Source | tools.allow | Capability file |
|---|---|---|---|
| `turn_state` | new plugin tool, `scripts/turn_state.py` | yes | (dispatcher; not a capability) |
| `capture` | renamed from `capture_gtd` | yes | `capture.md` |
| `query_tasks` | existing | yes | `query_tasks.md` |
| `query_ideas` | existing | yes | `query_ideas.md` |
| `query_parking_lot` | existing | yes | `query_parking_lot.md` |
| `review` | renamed from `review_gtd` | yes | `review.md` |
| `list_events` | existing | yes (already) | `calendar_read.md` |
| `get_event` | existing | yes (already) | `calendar_read.md` |
| `message` | existing | yes (already) | (not a capability; used by all) |
| `delegation` | removed | (n/a) | (n/a) |

## v1-to-v2 transition map

**Survives untouched:** `list_events`, `get_event`, calendar tool plumbing, the data layer (Z3 contracts, validate.py, write.py, JSONL resilience, OTEL on the data path).

**Survives reshaped:** `tools.allow` (expanded to GTD tools); SOUL.md (existing content plus three additions); IDENTITY.md (locked as-is, footnote intact); plugin `index.js` (OTEL retrofit per pattern 2: `startActiveSpan`, `SPAWN_ENV`, TRACEPARENT injection); `package.json` (`@opentelemetry/api` dependency added).

**Newly authored:** `scripts/turn_state.py`; `capabilities/capture.md`, `capabilities/query_tasks.md`, `capabilities/query_ideas.md`, `capabilities/query_parking_lot.md`, `capabilities/review.md`, `capabilities/calendar_read.md`; AGENTS.md (full replacement against AGENT_ARCHITECTURE skeleton plus PREFLIGHT plus outward guardrails section); workspace-root SKILL.md; `agent_data/gtd/<user.id>/profile.json` template; user_context helper; `auth-profiles.json` at agentDir.

**Removed:** v1 AGENTS.md content; v1 TOOLS.md content; `gtd-workspace/skills/gtd/SKILL.md`; `scripts/gtd/delegation.py`; `delegation` plugin tool registration.

**De-injected:** BOOTSTRAP.md drops from `injectedWorkspaceFiles`; stays on disk.

## Pattern compliance check

| Pattern | Status against target architecture |
|---|---|
| 1. Multi-mode dispatcher | Met. turn_state authored; PREFLIGHT block in AGENTS.md; capability files on disk. |
| 2. OTEL cross-process propagation | Met. index.js retrofit; span attribute contract locked at Layer 3. |
| 3. Plugin registration | Met. turn_state added to plugins.entries; gtd-tools entries unchanged shape. |
| 4. Tool surface deny defaults | Met. tools.deny retained; tools.allow expanded. |
| 5. Capability-shaped surfaces | Met. Six capability tools match user-visible capabilities; pipeline internals stay in `scripts/gtd/` modules. |
| 6. Date sourcing | Audit did not surface this; assumed not yet present; Layer 3 confirms which capabilities need `get_today_date` and adds the plugin tool. |
| 7. Local-only runtime data | Met. profile.json at `agent_data/gtd/<user.id>/profile.json`. |
| 8. Atomic writes | Met (Z3 lock). |
| 9. Temperature=0 inner calls | Met. Inner classifier and capability calls all temp=0. |
| 10. NO_REPLY for inline buttons | Carry-forward; capability files specify NO_REPLY where they emit inline buttons. |

**Gap surfaced:** pattern 6 (date sourcing). The audit did not check for `get_today_date`; reasonable assumption is the plugin tool does not exist yet for Trina. Several capabilities will reason about "today" (capture priority/due, query overdue, review window). Layer 3 confirms scope and adds to build.

## What Layer 2 does not do

Does not author capability prompt content. Does not enumerate Python signal patterns. Does not lock span attribute contract. Does not draft negative-path reply text. Does not write the build prompt for Code. All are Layer 3 work.

Does not promote "Inner LLM role-based routing" or "Memory proxy bypass" at the AGENT_ARCHITECTURE doc level. Trina-scoped lock change; doc-level lock is a separate sub-step close decision.

---

_Architecture locked. Layer 3 opens against this._
