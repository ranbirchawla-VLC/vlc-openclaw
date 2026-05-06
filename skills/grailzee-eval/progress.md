# progress.md — Grailzee Eval v2

**Working root**: `/Users/ranbirchawla/ai-code/vlc-openclaw-gtd`
**Canonical state doc**: `GRAILZEE_SYSTEM_STATE.md` at repo root. Read that first.

Session-open protocol: read `GRAILZEE_SYSTEM_STATE.md`, then this file.

---

## Active tracks

### Track 1 — Shape K (ACTIVE — 2026-05-05)

**Branch**: `feature/grailzee-eval-v2`
**Tip**: `0c3d78b` (pushed to origin)

#### Session 2026-05-05 — what happened

**turn_state dispatch tool built and /ledger gate CLEARED**

Root cause of prior gate failure: AGENTS.md said "Read one file: SKILL.md"
but no `read` tool in tools.allow. SKILL.md never landed in context.

Fix: `turn_state.py` (stdin-dispatched) classifies message, reads matching
capability file from disk, returns `{intent, capability_prompt}`. AGENTS.md
PREFLIGHT forces it before every response.

Second failure: `GRAILZEE_ROOT` not in gateway environment. Fix: injected
as `SPAWN_ENV` constant in `index.js` with production Drive path as fallback.

**Uncommitted work (ready to stage):**
- `skills/grailzee-eval/scripts/turn_state.py` (new)
- `skills/grailzee-eval/tests/test_turn_state.py` (new, 50 tests)
- `plugins/grailzee-eval-tools/index.js` — turn_state registration + SPAWN_ENV
- `skills/grailzee-eval/AGENTS.md` — PREFLIGHT replaces "Read one file"
- `skills/grailzee-eval/tests/test_plugin_shape.py` — turn_state assertions
- `Makefile` — test-grailzee-eval-turn-state target
- `update_openclaw_config.py` — one-time config script (already run; idempotent)

**Test baseline**: 1441 passed / 71 skipped (all green)

**Operator gate: CLEARED — /ledger worked on Telegram 2026-05-05**

**Remaining commit chain:**
- Commit: turn_state + AGENTS.md + SPAWN_ENV + tests (ready now)
- C — capabilities/eval.md (replaces capabilities/deal.md)
- D — capabilities/report.md rewrite
- F — tools.allow lockdown + audit gate

**Resume doc**: `~/Downloads/aBuilds-5-2/Grailzee_ShapeK_Resume_2026-05-02.md`

#### Session 2026-05-04 — commits landed (all pushed)

- `7ff23e9` G — report_pipeline plugin dispatch layer
- `0d73691` H — ingest_sales plugin dispatch layer + tool registration
- `2852144` E — capabilities/ledger.md rewrite
- `ce4be04` A — AGENTS.md rewrite (design §7)
- `70b1164` B.1 — SKILL.md rewrite (design §6)
- `25be64b` B.2 — remove cross-cutting rule duplication from ledger.md
- `0c3d78b` fix — ingest_sales sys.path.insert for spawnArgv invocation

**Model switch**: `ollama/qwen3.5:latest` → `mnemo/claude-sonnet-4-6`

**Shape K status:**

| Item | State |
|---|---|
| 1a GRAILZEE_ROOT env-var | DONE |
| 1b agent surface lockdown | DONE |
| 1c plugin scaffold + register evaluate_deal | DONE |
| 1c.5 spec-drift fixup | DONE |
| turn_state dispatch tool | DONE |
| 1b.5 stdin dispatch: report_pipeline + ledger_manager | NEXT |
| 1d report_pipeline plugin registration | NOT STARTED |
| 1e update_name_cache plugin registration | NOT STARTED |
| 1f AGENTS.md final pass + SKILL.md hard rules | NOT STARTED |

---

### Track 3 — OTEL Instrumentation (SHIPPED — merged main `1b3536e`, 2026-05-06)

**Tests at close**: 1475 passed / 71 skipped

- turn_state span with `intent`, `capability_file`, `capability_loaded` attributes
- SPAWN_ENV injects OTLP endpoint, protocol, service name
- W3C trace propagation: `newTraceparent()` in Node.js; `attach_parent_trace_context()` in Python
- Real Node.js spans per tool call via `startActiveSpan`; full parent-child tree in Honeycomb confirmed

**Gate PASSED — Honeycomb (2026-05-06):**
```
grailzee.tool.evaluate_deal   (openclaw-gateway, 235.1ms)
  └── evaluate_deal           (grailzee-eval-tools, 31.73ms)
```

---

### Track 2 — Ledger Redo Phase 1 (SHIPPED 2026-04-29)

**Branch tip**: `1256dfd` — durability artifacts
**Tests**: ledger 332 / eval 1366 / 71 skipped / cowork 235
**Production ledger**: `$GRAILZEE_ROOT/state/trade_ledger.csv` — 16 rows, NR=11, RES=5

**Gate 3 (2026-04-29)**: PASSED — files_processed=1, rows_added=19, rows_pruned=3, idempotency confirmed

| Sub-step | State | Tip |
|---|---|---|
| 1.1 schema + dataclasses | DONE | `3f963af` |
| 1.2 transform_jsonl | DONE | `66fe0ec` |
| 1.3 lockfile + atomic write | DONE | `43c47d0` |
| 1.4 Rule Y dedup-and-update | DONE | `5d5d47f` |
| 1.5 pruning + nullability | DONE | `30cfd7f` |
| 1.6 archive move | DONE | `61f6f6a` |
| 1.7 orchestrator | DONE | `8d73c35` |
| Phase 1 Gate 3 + cutover | DONE | `ae80d3a` |
| Phase 1 durability + closeout | DONE | `1256dfd` |

---

## Pointers

- State truth: `GRAILZEE_SYSTEM_STATE.md` (repo root)
- Decision locks: `docs/decisions/`
- ADRs: `docs/decisions/ADR-0001` through `ADR-0007`
- Root OpenClaw config: `~/.openclaw/openclaw.json` (outside repo)
- Production ledger backup: `$GRAILZEE_ROOT/state/trade_ledger.csv.pre-redo-2026-04-29.bak`
- Full prior build log: `.claude/progress-v0.md`
