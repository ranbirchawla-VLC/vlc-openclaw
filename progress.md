# NutriOS v3 — Build Progress

Branch: `feature/nutrios-v3`

---

## Sub-step 0: Foundation
- Started: 2026-04-25
- Pre-review commit: 384c930
- Test count: 10
- Review findings: 0 blockers / 7 non-blockers
- Post-review commit: n/a (no blockers)
- Squash commit on feature/nutrios-v3: 384c930
- Customer outcome demonstrated: @ranbir_nutrition_bot replied "Hey Ranbir! Ready when you are. What are we tracking today?"
- KNOWN_ISSUES added: NB-1 through NB-7 (5 cleared in sub-step 1 pre-scope)
- Notes: python3.11 used (python3.12 not installed); anthropic SDK works against real API, not mnemo proxy (proxy has body-read bug at current version)

---

## Sub-step 1: Mesocycle setup (scratch path)
- Started: 2026-04-25
- Pre-review commit: b80753a, 45 Python + 4 LLM = 49 tests
- Review findings: 1 blocker / 9 non-blockers
- Post-review commit: 8d60fdf
- Squash commit on feature/nutrios-v3: b03dc4d
- Customer outcome demonstrated: PENDING — gate 3 release check deferred to morning
  - Required: name "maintenance", weekly deficit 1850, TDEE 2350, protein 175, fat 65
  - Expected: daily target ~2086 cal, no fabrication narration, no script description
  - Then: restart Telegram, "what's my cycle" reads back correctly
- KNOWN_ISSUES added: NB-1 through NB-9 (B-1 cleared post-review)
- Notes:
  - Weekly deficit bug fixed: target_deficit_kcal is weekly; tool divides by 7 (2350 - 1850/7 = 2086)
  - LLM test harness built at scripts/tests/llm/ using real Anthropic API (bypass mnemo)
  - Makefile now has make test-fast / make test-llm / make lint per standing rules
  - Two-commit pattern: pre-review commit = current push; post-review commit = morning after gate 1 clears
  - NB-6/NB-7/NB-9 are quick fixes — do these first thing in the morning before Telegram demo

---

## Sub-step 2 prep: Python tools (partial gate)

Branch: `feature/nutrios-v3-substep2-py` (off `feature/nutrios-v3` at f53eb11)

- Started: 2026-04-25
- Scope: Python-only — no LLM tools, no capability prompt, no Telegram. estimate_macros_from_description OUT OF SCOPE (next session).
- Pre-review commit: 73d2d97 (4 commits), 99 Python tests (was 49; +50)
- Review findings: 2 blockers / 5 non-blockers
- Post-review commit 1 (blockers): daf3012 — B-1 atomic-failure test fix, B-2 CorruptStateError consistency
- Post-review commit 2 (non-blockers): 5812119 — NB-12 datetime import, NB-14 match/case validators, NB-15 timezone validation in main(), NB-16 return type annotation
- Test count post-review: 100 Python passed, 4 LLM skipped (no key in env)
- Gate 3 (Telegram release check): DEFERRED — requires estimate_macros_from_description + capability prompt + LLM tests (next session, desktop AM)
- KNOWN_ISSUES added: NB-10, NB-11 (design decisions); NB-12 through NB-17 (review findings; NB-12/14/15/16 resolved in-pass, NB-13/17 deferred)
- Notes:
  - Dose offset formula confirmed: `(date.weekday() - dose_weekday) % 7`
  - Expired cycle: target returned with `is_expired: bool` flag; sub-step 9 handles transition
  - NB-13 deferred: os.path → Pathlib migration is a full-codebase sweep, not piecemeal
  - NB-17 deferred: append_jsonl partial-line recovery (trailing-line skip in _load_meal_logs)
  - AM desktop: pull `feature/nutrios-v3-substep2-py`, `make setup`, `make test-nutriosv2` green, then build estimate_macros_from_description + capability prompt + LLM tests + gate 3 Telegram smoke test
  - After AM session: squash sub-step 2 prep + new estimate work into one final sub-step 2 commit on feature/nutrios-v3

---

## Environment: venv migration (2026-04-25)
- Trigger: `make test-nutriosv2` failed — pytest missing from homebrew `python3.11` site-packages (likely wiped by a homebrew upgrade since sub-step 1 ran green)
- Created `.venv/` at repo root via `python3.11 -m venv .venv` + `pip install -e ./skills/nutriosv2[dev]`
- Pins now in `.venv`: pytest 9.0.3, pydantic 2.13.3, anthropic 0.97.0
- Makefile: `PYTHON = .venv/bin/python`, `PYTEST = $(PYTHON) -m pytest`; added `setup` target (idempotent) and `test-nutriosv2-llm` target
- Conftest at `skills/nutriosv2/scripts/tests/llm/conftest.py`: API key precedence is `ANTHROPIC_API_KEY` env var → `~/.openclaw/openclaw.json` (legacy) → skip with NB-9 message
- CLAUDE.md: added `make setup` first-run note and the LLM key requirement under Test invocation goes through Make
- `.gitignore` already excluded `.venv/` — no change
- Verified green: `make test-nutriosv2` 49/49 (45 Python + 4 LLM, 13.57s) with `ANTHROPIC_API_KEY` set
- Desktop pull tomorrow: `make setup` then `export ANTHROPIC_API_KEY=…` then `make test-nutriosv2` before gate 3 Telegram smoke test

---

---

## Sub-step 1 follow-up work (gate 3 rounds 1–4)

### What was built

**Follow-up #1 (carbs/weekday names) — landed in follow-up #2 commit ef3c16e:**
- `dose_offset_to_weekday` utility + 8 unit tests (common.py)
- Capability prompt: step 6 weekday-name labeling + explicit Sunday example; step 7 carbs required; "never use word offset" rule
- LLM tests: carbs in read-back; weekday names in table; no +N/day-N/offset-N patterns

**Follow-up #2 (recompute tool) — ef3c16e, 2026-04-26:**
- `recompute_macros_with_overrides.py`: pure redistribution; floor-division rounding; raises ValueError on budget overflow or constraint violations (9 unit tests)
- `openclaw.json`: tool registered
- Capability prompt: adjustment-flow section; three HARD RULES for tool-only redistribution
- LLM tests: recompute called for override; constraint surfaced for infeasible override
- KNOWN_ISSUES: NB-19 (reallocation lacked Python contract), NB-20 (HARD RULES did not cover recomputes)
- Gate 1 at commit: 125 passed (116 Python + 8 LLM)
- Gate 2 at commit: 1 blocker fixed (em-dash in openclaw.json), NB-C addressed (verbatim arg assertions)

**Follow-up #3 (zero-arithmetic rule) — 6821d3d, 2026-04-26:**
- CLAUDE.md: "LLM emits zero arithmetic" added to Core Principle
- `llm_test_utils.py`: `assert_no_llm_arithmetic` with N op N = N regex (ASCII + Unicode); auto-runs on every assistant turn
- Capability prompt: three adjustment HARD RULES replaced with "Zero arithmetic" + "Recompute on intent change" + error-handling rule
- LLM tests: intent-change deficit triggers recompute; arithmetic narration test
- KNOWN_ISSUES: NB-21 (no recompute on intent change), NB-22 (arithmetic narration persisted), NB-23 (per-capability HARD RULES insufficient for cross-cutting rules)
- Gate 1 at commit: 127 passed (117 Python + 10 LLM)
- Gate 2 at commit: 0 blockers; NB-A (deleted verbatim assertions) and NB-B (constant vs literal) fixed before commit

### Gate 3 rounds

| Round | Date/time | Outcome | Root cause |
|-------|-----------|---------|------------|
| 1 | 2026-04-26 AM | RED | Carbs missing in read-back; numeric day labels |
| 2 | 2026-04-26 mid | RED | Arithmetic narration + wrong baseline (12,100 instead of 12,600) |
| 3 | 2026-04-26 mid | RED | Same arithmetic narration; "12,100" on 3,500-deficit calculation |
| 4 | 2026-04-26 ~16:49 | RED | Arithmetic narration: "3,800/week off 2,300 TDEE = 12,300... (12,300 - 1,550) ÷ 6 = 1,792" |

### Diagnostic findings (2026-04-26 post round 4)

**Session scope.** OpenClaw's `dmScope: "per-channel-peer"` maintains ONE persistent session for the nutriosv2 bot DM with Ranbir. All gate 3 attempts today are in the same JSONL (172 messages total). There is no per-setup-conversation reset.

**Capability prompt not loaded at rounds 2–4.** The agent loaded SKILL.md and mesocycle_setup.md exactly once — at session start, turn [6], 00:56 AM. All subsequent setup attempts (rounds 2–4) used the stale capability prompt from that first load without re-reading. The capability prompt loaded at 00:56 AM is the pre-follow-up original (no HARD RULES section, no zero-arithmetic rule, no recompute-on-intent-change rule).

**Consequence: none of the follow-up rules were ever active in production.** Follow-up #2 and #3 changes to the capability prompt are on disk but were never loaded by the agent during any gate 3 round.

**Context at round 4 turn 6.** 165 prior messages in context, including 5 prior assistant messages narrating arithmetic in the prohibited N op N = N form (turns 79, 108, 127, 142, 146). These establish a strong in-context precedent for arithmetic narration that the buried (and outdated) capability rule cannot overcome.

**Next action required before round 5.** The Telegram session must be cleared so the agent reloads the capability prompt from disk on the next conversation. Without a session reset, the agent will continue to use the old capability prompt regardless of what is committed.

---

## Sub-step Z: Architectural fixes — Commit 1 (runtime mechanics)

Branch: `feature/nutrios-v3`

- Started: 2026-04-26
- Scope: Decision 1 (turn_state capability_prompt injection), Decision 2 (SESSION_DIR + intent classifier + session boundary rename), capability cleanup (NB-23 closure)
- Pre-review commit: (this commit)
- Python test count: 164 passed (was 162; +2 from NB-5 + B-2 review fixes)
- Review findings: 2 blockers / 5 non-blockers
  - B-1 (no LLM test for turn_state): carry to commit 2 per spec
  - B-2 (unguarded compute_turn_state in main): fixed in-pass; + test
  - NB-1 (em-dashes): fixed in-pass across all touched files
  - NB-2 (silent multi-candidate case): carry as NB-28 in KNOWN_ISSUES
  - NB-3 (bare -> dict return type): fixed in-pass; TurnStateResult TypedDict added
  - NB-4 (missing-input rule removed from capability): defer to commit 2
  - NB-5 (no test for absent sessionFile key): fixed in-pass; + test
- KNOWN_ISSUES added: NB-28 (_find_session_file multi-candidate silent no-op)
- Open-in-pass resolutions:
  - sessions.json schema: unambiguous; single entry per peer; implemented directly
  - Capability file: capabilities/mesocycle_setup.md (one file for both intents)
  - Reset timestamp format: YYYY-MM-DDTHH-MM-SS.000Z (matched existing reset files)
  - Intent classifier: scripts/intent_classifier.py
- Notes:
  - turn_state.py: TypedDict return, guarded main(), no em-dashes
  - Commit 2 delivers: LLM voice rules in CLAUDE.md, assert_no_process_narration, multi-turn harness rewrite, NB-4 rule, contract test for session rename
  - Do NOT squash until commit 2 lands green

---

## Sub-step T: Multi-turn LLM test harness — UNCOMMITTED

Branch: `feature/nutrios-v3` (uncommitted working tree on top of 6821d3d)

- Started: 2026-04-26
- Scope: multi-turn harness to catch production-like conversation carryover bugs
- Changes:
  - `test_mesocycle_setup_llm.py`: `MultiTurnHarness` class; 4-turn gate 3 regression test `test_deficit_change_triggers_recompute_multi_turn`; module docstring documents single-shot vs multi-turn harness shapes
  - `capabilities/mesocycle_setup.md`: "never use word offset" rule strengthened to explicitly cover parentheticals ("(offset 0)")
- Gate 1: 128 passed (117 Python + 11 LLM) — green
- Gate 2: 2 blockers fixed (em-dash in comment; dead constant `_MT_BASELINE_NEW`); 3 non-blockers fixed (type annotations, hoisted imports)
- Multi-turn test result: PASSED on first run against current capability prompt — the "Recompute on intent change" rule is working in clean single-session test context
- Gate 3: NOT RUN — uncommitted; round 5 pending session reset
- KNOWN_ISSUES added: none (NB-21/22/23 already in #3 commit)
- Notes:
  - Test passes because it starts with a fresh session context; production failure was caused by stale session + stale capability prompt load
  - Session must be cleared (Telegram restart + dmScope session wipe, or gateway restart) before round 5
  - Sub-step T commit message: "feat(test): multi-turn LLM harness, fixes deficit-change baseline reuse (sub-step T)"

---
