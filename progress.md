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
