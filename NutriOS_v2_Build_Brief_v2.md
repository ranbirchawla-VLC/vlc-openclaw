# NutriOS v2 — Build Brief for Claude Code

Prepared: 2026-04-24
Owner: Ranbir Chawla
Runtime: OpenClaw 2026.3.28+, Python 3.12, Mnemo proxy

---

# Part 1 — Purpose, Function, and Execution

## Purpose

NutriOS is Ranbir's daily nutrition operating system. It exists to make food logging, macro tracking, and mesocycle adherence effortless over Telegram, so training and body-comp goals stay on track without the friction of a tracking app. It is the most-used agent in the OpenClaw fleet, which means every design decision optimizes for speed, correctness, and low cost per turn, not for feature breadth.

Three commitments define the product:

- Correct math, every time — macro totals, remaining budgets, and recipe expansions must be exact.
- Correct time, every time — meal slots, "today", and summary windows must match the user's TZ to the second.
- Low friction — a single short message like "2 eggs and coffee" should log cleanly with at most one clarification.

## Users and scope

- Primary user: Ranbir, training in a structured mesocycle with protected protein targets and a fat ceiling for gallbladder reasons.
- Multi-user ready: additional users can be onboarded under the same OpenClaw instance via `per-channel-peer` isolation, each with independent profile, goals, recipes, and logs.
- Out of scope: meal planning, grocery lists, workout logging, barcode scanning, image recognition.

## Functional goals

- Log foods and recipes against the current day with accurate macros and meal slot.
- Resolve aliases and "usual" portions without re-asking the user.
- Look up saved recipes first before treating a mention as a generic food.
- Clarify quantity when missing, never clarify cooking method.
- Produce a daily summary in Telegram plain text with kcal and macro remaining, flags for over/under, and the meal list.
- Manage mesocycle setup, day-pattern defaults, and day-type overrides.
- Enforce protected defaults — the protein target cannot be changed without the exact confirmation phrase.
- Persist all data per user on local disk and in Mnemo, with no cross-user leakage.
- Support edits and deletions via append-only `supersedes` entries, never destructive writes.

## Non-functional goals

- Deterministic math: zero arithmetic errors in a 7-day sample.
- Deterministic time: every timestamp and slot matches `nutrios_time.now()` in user TZ.
- Token efficiency: median turn cost drops materially after prompt cache warms.
- Latency: a log turn completes in under 2 seconds excluding LLM time.
- Isolation: two channel peers produce two fully separate data trees and Mnemo namespaces.
- Recoverability: daily JSONL files are append-only and human-readable for manual repair.
- Observability: every tool call logs `{user_id, intent, tool, tokens_in, tokens_out, ms}` to a local runlog.

## Execution goals

- LLM performs no arithmetic and no date math — ever.
- LLM never constructs paths, user ids, or recipe ids — all resolved in Python.
- Each turn follows a fixed pipeline: resolve time, classify intent, call one Python tool, render the tool's string back.
- Protected-default changes are gated in Python; the prompt cannot be talked past.
- Orchestrator prefix stays byte-stable across turns so Anthropic prompt caching holds.
- Volatile per-user state is fetched by keyed Mnemo lookup, never injected into the prompt.
- Tool outputs are pre-rendered Telegram plain text; the LLM paraphrases at most one framing sentence.
- Failures return a structured error block that the LLM reads verbatim — no improvised apologies or guesses.

## Turn contract

1. Resolve `now` via `nutrios_time.now()` and `user_id` via channel-peer lookup.
2. Classify intent into `log | summary | goals | setup | clarify | smalltalk`.
3. Dispatch to exactly one Python tool with `{user_text, now, user_id}`.
4. Tool fetches needed state from disk or Mnemo, computes in `nutrios_engine`, renders via `nutrios_render`.
5. Tool returns `{display_text, needs_followup, state_delta?}`.
6. LLM emits `display_text` with minimal natural framing.

Any deviation from this contract is a bug, not a feature.

## Success criteria

- 95%+ of turns resolve in a single tool call with no math performed by the LLM.
- 100% of timestamps and slots match user-TZ ground truth.
- Zero protected-default bypasses in adversarial prompt tests.
- Token cost per daily summary at least 40% lower than the current NutriOS build.
- Two-user isolation test passes: separate directories, separate Mnemo keys, no cross-read possible.

## What Claude Code should optimize for

Prefer boring, tested Python over clever prompts; prefer one more pure function over one more rule in a prompt; prefer a rendered string from Python over letting the LLM format numbers. If a behavior can live in code, it must live in code. The prompt layer exists only to classify intent and speak plainly back to the user.

---

# Part 2 — Architectural Spec (Appendix)

Short, build-ready, Python-native.

## Goals

- Deterministic math and time in Python; LLM only for intent and phrasing.
- Mnemo-backed durable state; prompts stay tiny and cache-stable.
- Local disk storage, multi-user safe, no Google Drive dependency.

## Tech choices

- Language: Python 3.12, stdlib first, `pydantic` for schemas, `zoneinfo` for TZ.
- Runtime: OpenClaw 2026.3.28+, tools invoked via `process.argv` JSON contract preserved.
- Memory: Mnemo proxy for durable user facts, keyed reads only.
- Storage: local disk at `NUTRIOS_DATA_ROOT`, per-user directories, JSONL append logs.

## Directory layout

```
$NUTRIOS_DATA_ROOT/
  users/
    {user_id}/
      profile.json         # tz, units, display prefs
      goals.json           # active mesocycle, day patterns, protected flags
      recipes.json         # saved recipes, recipe-first lookup source
      aliases.json         # "shake" -> recipe_id
      portions.json        # "usual" defaults per food
      log/
        2026-04-24.jsonl   # one line per entry, append-only
        2026-04-23.jsonl
      mesocycles/
        {cycle_id}.json    # historical cycles
      state.json           # last_entry_id, counters
  _index/
    users.json             # channel_peer -> user_id mapping
```

One directory per user, never cross-read; channel-peer to user_id mapping is the only multi-user gate. Log files are daily JSONL so appends are O(1) and reads are bounded.

## User isolation

- `session.dmScope: "per-channel-peer"` in `openclaw.json` is the outer gate.
- Every tool call receives `NUTRIOS_USER_ID` resolved from the channel peer via `_index/users.json`.
- File paths are constructed as `data_root / "users" / user_id / ...` — no path from the LLM is trusted.
- Mnemo keys are namespaced `user:{user_id}:*` so retrieval cannot bleed across users.

## Python modules

All modules live under `~/.openclaw/skills/nutriOS/lib/`.

| Module | Role |
|---|---|
| `nutrios_time.py` | `now()`, `meal_slot()`, `window()`, `parse()` — authoritative TZ math |
| `nutrios_store.py` | Disk I/O, per-user path resolution, JSONL append/read, atomic writes |
| `nutrios_engine.py` | Pure math: totals, remaining, recipe expansion, day-type apply, protected gate |
| `nutrios_mnemo.py` | Thin Mnemo client, keyed get/set/search, user-namespaced |
| `nutrios_render.py` | Telegram plain-text formatters for summary, confirm, error |

## Tool shims (replace the three .js files)

Each tool is a Python entrypoint invoked by OpenClaw with a single JSON argv; same contract as before.

- `nutrios_read.py` — `{scope, key?, date?, query?}` -> structured read via `store` or `mnemo`.
- `nutrios_write.py` — `{scope, payload, confirm?}` -> validated write, runs `protected_default_gate` before mutating goals.
- `nutrios_log.py` — `{user_text, now?}` -> resolves alias, recipe-first lookup, quantity clarify flag, computes macros, appends JSONL, returns rendered confirm string.

Tools never do math or time inference inline — they call `engine` and `time`.

## Prompt layout

Short, stable, cache-friendly.

- `prompts/orchestrator.md` — intent router only: `log | summary | goals | setup | clarify | smalltalk`. Calls one tool, reads back rendered string. No rules, no formulas.
- `prompts/module-log.md` — phrasing rules for logging and clarification; no math.
- `prompts/module-goals.md` — phrasing rules for mesocycle and day patterns; confirmation phrases defined, enforcement lives in Python.
- `prompts/module-setup.md` — A-D flow phrasing only.

Target size: each prompt under 60 lines. The orchestrator prefix must not contain user-specific data so prompt caching holds.

## Data contracts

Minimal Pydantic models, one source of truth.

- `LogEntry`: `id, ts_iso, meal_slot, source(manual|recipe|alias), name, qty, unit, kcal, protein_g, carbs_g, fat_g, recipe_id?`
- `Goals`: `cycle_id, start_date, end_date, kcal, protein_g, carbs_g, fat_g, protected{protein_g:bool}, day_patterns[]`
- `Recipe`: `id, name, servings, ingredients[], macros_per_serving`
- `Profile`: `user_id, tz, units, display`

Writes are validated through models before touching disk.

## Non-negotiables

- LLM never performs arithmetic or date math.
- LLM never constructs file paths or user ids.
- Protected defaults gate runs in Python, not in prompt.
- All timestamps stored UTC ISO8601, rendered in user TZ.
- JSONL log files are append-only; edits write a new entry with `supersedes: <id>`.

## Build order for Claude Code

1. `nutrios_time.py` + unit tests.
2. `nutrios_store.py` with per-user path resolver and atomic JSONL append.
3. `nutrios_engine.py` pure functions + tests covering totals, remaining, recipe expansion, protected gate.
4. `nutrios_mnemo.py` thin client.
5. `nutrios_render.py` Telegram formatters.
6. Port `read/write/log` tools to Python shims, preserve argv JSON contract.
7. Slim `orchestrator.md` + three module prompts.
8. `scaffold.sh` updated to create the new local tree under `NUTRIOS_DATA_ROOT`.
9. `INSTALL.md` updated: env vars, `openclaw channels add`, `dmScope: per-channel-peer`, `openclaw doctor`.

Stop after step 3 for review.

## Env vars

- `NUTRIOS_DATA_ROOT` — local path, e.g. `~/NutriOS` or `/Users/ranbirchawla/NutriOS`.
- `NUTRIOS_TZ` — IANA zone, e.g. `America/Denver`.
- `NUTRIOS_MNEMO_URL` — default `http://127.0.0.1:9999`.
- `NUTRIOS_USER_ID` — resolved per turn from channel peer, not hardcoded.

## Success criteria (architectural)

- Median turn token usage drops significantly vs. current build after prompt cache warms.
- Zero LLM-authored arithmetic in logs over a 7-day sample.
- All times in confirmations match `nutrios_time.now()` to the second.
- Multi-user isolation verified by running two channel peers against the same agent and confirming separate directories and Mnemo namespaces.

---

End of brief. Hand this document to Claude Code as the build supervisor reference.
