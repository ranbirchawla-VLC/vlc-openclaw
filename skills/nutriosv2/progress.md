# progress.md — NutriOS v2

**Branch**: `feature/nutrios-v3`

Session-open protocol: read this file, then `KNOWN_ISSUES.md` in this workspace.

---

## Current state (2026-04-28 — end of exec lockdown session)

**All 8 plugin tools registered and verified:**
- `turn_state` — PROVEN
- `get_daily_reconciled_view` — PROVEN
- `write_meal_log` — PROVEN
- `estimate_macros_from_description` — PROVEN
- `compute_candidate_macros` — PROVEN
- `lock_mesocycle` — PROVEN
- `get_active_mesocycle` — PROVEN
- `recompute_macros_with_overrides` — PROVEN

**Exec lockdown: CLOSED** — audit session `b330c2fe`: 9 registered / 0 forbidden / 0 exec

**tools.allow**: `["get_daily_reconciled_view", "turn_state", "message", "write_meal_log", "estimate_macros_from_description", "compute_candidate_macros", "lock_mesocycle", "get_active_mesocycle", "recompute_macros_with_overrides"]`

**Tests**: 226 Python passed / LLM 57/57 (19 tests x 3 runs)

**NB-44 CLOSED** — workspace openclaw.json tools[] removed; plugin is single source of truth

---

## Next actions

1. Squash P3 work on `feature/nutrios-v3` into clean commits
2. Gate-3 re-run on sub-step 1 (mesocycle setup) against new architecture
3. Squash sub-step 2 prep + estimate work
4. Sub-step 2 (today view, check-in, recipes) starts after closure

---

## Pre-existing LLM flakes (not blocking)

| Test | Rate |
|---|---|
| `test_meal_log_donut_change_calories` | ~67% fail |
| `test_weekday_names_in_readback_no_numeric_labels` | intermittent |
| `test_intent_change_deficit_does_not_narrate_arithmetic` | ~33% fail |

---

## Key architectural decisions (locked)

- Plugin path: workspace openclaw.json tool loading silently fails; all tools registered via plugin
- `turn_state` intent_override: slash commands bypass classifier entirely
- Session scope: `dmScope: "per-channel-peer"` — one persistent session per Telegram peer
- `estimate_macros.py` bypasses mnemo proxy (`base_url` hardcoded to api.anthropic.com)
- `NUTRIOS_DATA_ROOT`: `/Users/ranbirchawla/agent_data/nutriosv2` — set in launchd plist
- tool-schemas.js: single source of truth for tool surface; emit-schemas.js regenerates tools.schema.json

---

## Sub-step history

| Sub-step | State | Branch tip |
|---|---|---|
| 0: Foundation | DONE | `384c930` |
| 1: Mesocycle setup (scratch path) | DONE (gate pending squash) | `b03dc4d` |
| 2 prep: Python tools | DONE | `5812119` |
| Z: Architectural fixes (turn_state, session boundary, voice rules) | DONE | `bcd2150` |
| Z2: Customer outcome — mesocycle + meal log | DONE | `457559d` |
| P3.0–P3.4: Plugin tool registration | DONE | `7377606` |
| NB-16: tool-schemas.js single source | DONE | `b088b94` |
| Exec lockdown | DONE | config only (`~/.openclaw/openclaw.json`) |
