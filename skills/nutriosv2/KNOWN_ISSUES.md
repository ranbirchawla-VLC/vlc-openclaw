# KNOWN_ISSUES.md — nutriosv2

Items deferred from prior sub-step gates, with target sub-step for resolution. Append-only; mark resolved items with the squash sha that closed them.

---

## Sub-step 0 carry-forward (deferred to sub-step 2)

### ~~NB-5 (sub-step 0 review): ok/err have no tests~~ (resolved)
- Resolved in sub-step 2 prep commit (see Resolution log).

### ~~NB-6 (sub-step 0 review): today_str has no test~~ (resolved)
- Resolved in sub-step 2 prep commit (see Resolution log).

---

## Sub-step 1 carry-forward (deferred to sub-step 2)

### ~~NB-1 (sub-step 1 review): get_active_mesocycle imports private helpers from lock_mesocycle~~ (resolved)
- Resolved in sub-step 2 prep commit (see Resolution log).

### NB-2 (sub-step 1 review): TODO(otel) stubs are dead code per CLAUDE.md
- Files: tool entry/exit points in `scripts/compute_candidate_macros.py`, `scripts/lock_mesocycle.py`, `scripts/get_active_mesocycle.py`
- Fix: remove TODO(otel) comments. Spans are designed in Session 3 but wiring is its own future sub-step; comments are clutter not roadmap.

### NB-3 (sub-step 1 review): open() without context manager in 2 places
- Locations: TBD — find via grep, replace with `with open(...) as f:` form. Atomic-write helpers in common.py already use context managers; these are likely in tool scripts that bypass the helpers.

### NB-4 (sub-step 1 review): _MacroRowInput/_IntentInput duplicate MacroRow/Intent
- File: `scripts/lock_mesocycle.py`
- Fix: decide once — either consolidate to a single shared validator module (input model and domain model share validators), or keep the split and document why (input validates wire-shape, domain validates invariants). Don't let the duplication slide unexamined.

### NB-5 (sub-step 1 review): Unreachable return after err() in all 3 main() functions
- Files: `scripts/compute_candidate_macros.py`, `scripts/lock_mesocycle.py`, `scripts/get_active_mesocycle.py`
- Fix: err() calls sys.exit(1); the return after it is dead. Remove. If a linter is configured later it'll flag these.

### NB-8 (sub-step 1 review): Forbidden-word test uses substring — "the tool" false-positive risk
- File: `tests/llm/` (specific file TBD)
- Fix: tighten the assertion. Use word-boundary regex or structured assertion against tool-call shape rather than substring on response text. Risk is a legitimate response containing the substring "the tool" failing the test, masking real fabrication elsewhere.

---

## Sub-step 2 carry-forward

### NB-10 (sub-step 2 prep): lock_mesocycle does not validate start_date.weekday() == dose_weekday
- File: `scripts/lock_mesocycle.py` (`_Input` validator)
- Fix: add a `@model_validator` that asserts `date.fromisoformat(start_date).weekday() == dose_weekday`. Without this, the dose-offset formula `(date.weekday() - dose_weekday) % 7` yields wrong macro rows for misaligned cycles.
- Target: sub-step 3 or standalone cleanup PR.

### NB-11 (sub-step 2 prep): existing test fixture has start_date/dose_weekday misalignment
- File: `scripts/tests/test_mesocycle.py`, `_lock_input()` helper
- Context: `start_date="2026-05-01"` (Thursday, weekday 3) with `dose_weekday=0` (Monday) — misaligned. Harmless today since lock_mesocycle doesn't validate it and tests don't exercise dose-offset math, but will break once NB-10 enforcement lands.
- Fix: update `_lock_input()` to use an aligned pair (e.g., `start_date="2026-05-05"`, `dose_weekday=0`) when NB-10 lands.
- Target: same commit as NB-10.

---

### NB-12 (sub-step 2 prep review): `datetime` imported inside `_filter_by_date` function body
- File: `scripts/get_daily_reconciled_view.py`, inside `_filter_by_date`
- Fix: move `from datetime import datetime` to top-level imports alongside `from datetime import date as date_type`.
- Priority: low (Python caches imports; no correctness issue).

### NB-13 (sub-step 2 prep review): `os.path` used throughout instead of Pathlib
- Files: `scripts/common.py`, `scripts/write_meal_log.py`, `scripts/get_daily_reconciled_view.py`, `scripts/lock_mesocycle.py`, `scripts/get_active_mesocycle.py`
- Fix: piecemeal migration creates inconsistent debt — do it as a single sweep. `common.py` is the source; all other tools follow its pattern. Migrate `os.path.join`/`os.path.exists`/`os.makedirs` to `pathlib.Path` across all five files in one pass when there is budget.
- Priority: low (no correctness impact; do as a standalone cleanup PR, not interleaved with feature work).

### NB-14 (sub-step 2 prep review): `model_validator` on `source`/`recipe_id` uses `if/if` on a `Literal` field — should use `match/case`
- Files: `scripts/models.py` (MealLog), `scripts/write_meal_log.py` (_Input)
- Fix: replace the two-`if` pattern with `match self.source: case "recipe": ... case "ad_hoc": ... case _: raise ValueError(...)`. This makes the validator exhaustive.
- Priority: medium (CLAUDE.md requirement; logic gap on hypothetical third source value).

### NB-15 (sub-step 2 prep review): `active_timezone` not validated before `zoneinfo.ZoneInfo()` call
- File: `scripts/get_daily_reconciled_view.py`, `run_get_daily_reconciled_view()`
- Fix: wrap `zoneinfo.ZoneInfo(inp.active_timezone)` in a try/except `zoneinfo.ZoneInfoNotFoundError` and call `err(...)` with a structured message. Currently raises a traceback instead of `{"ok": false, "error": "..."}`.
- Priority: medium (tool contract broken on invalid timezone; low likelihood since LLM passes valid values).

### NB-16 (sub-step 2 prep review): `_sum_macros` return type is bare `dict` instead of `dict[str, int]`
- File: `scripts/get_daily_reconciled_view.py`
- Fix: annotate as `dict[str, int]`.
- Priority: low (type precision; no correctness issue).

### NB-17 (sub-step 2 prep review): `append_jsonl` not crash-safe for partial-line writes
- File: `scripts/common.py`, `append_jsonl()`
- Bare `open(path, "a") + write + fsync`. A crash between `open` and the trailing newline leaves a partial line on disk. True atomic append (tmp + concat + replace) is expensive and would require rewriting the whole file on each append.
- Standard recovery: add a trailing-line skip in `_load_meal_logs` — if the last line fails JSON parse, log a warning and treat all prior lines as valid. `CorruptStateError` stays the right behavior for corrupt non-trailing lines.
- Fix: implement the trailing-line skip in `_load_meal_logs` (and mirror in `_next_log_id`) in a follow-up. B-1 test fix confirmed the atomic-failure test now exercises the right code path.
- Priority: medium (real durability gap; low probability in practice).

---

## Sub-step 1 follow-up #3 (gate 3 findings)

### ~~NB-21 (sub-step 1 gate 3): Capability did not trigger recompute on intent change~~ (resolved)
- Instance: user changed weekly deficit 4,000 to 3,500 mid-conversation. LLM reused prior weekly intake (12,100) instead of recomputing baseline. Every downstream row understated by ~83 kcal/day.
- Resolution: this commit adds "Recompute on intent change" HARD RULE to capability prompt; intent-change LLM test added.

### ~~NB-22 (sub-step 1 gate 3): Inline arithmetic narration persisted despite per-capability HARD RULE~~ (resolved)
- Instance: LLM narrated arithmetic inline ("(12,100 - 1,550) div 6 = 1,758 cal/day") even after follow-up #2 HARD RULE. Tests did not assert against it.
- Resolution: zero-arithmetic rule promoted to project CLAUDE.md; universal assert_no_llm_arithmetic in LLM test utils auto-runs on every fixture response.

### ~~NB-23 (sub-step 1 architectural lesson): Per-capability HARD RULES are insufficient for cross-cutting LLM behavior~~ (resolved)
- Pattern: the translator-not-calculator rule leaked twice through per-capability enforcement. Cross-cutting rules require: (1) project-level statement in CLAUDE.md, (2) universal test enforcement, (3) per-capability restating for emphasis only.
- Resolution (Sub-step Z commit 2, SHA TBD): "LLM voice rules" section added to vlc-openclaw CLAUDE.md; assert_no_process_narration universal helper in LLM test utils; mesocycle_setup.md HARD RULES replaced with CLAUDE.md reference. Fully closed.

---

## Sub-step 1 follow-up #2 (gate 3 findings)

### ~~NB-19 (sub-step 1 gate 3): Macro reallocation lacked a Python contract~~ (resolved)
- Instance: when user proposed a single-row override, LLM did inline redistribution math, stated weekly baseline as 12,100 (actual: 12,600). Effective deficit was 4,002 kcal/week, narrated as 3,502.
- Resolution: this commit lands `recompute_macros_with_overrides` + capability HARD RULE enforcing tool-routed adjustment math.

### ~~NB-20 (sub-step 1 capability HARD RULES did not extend to recomputes)~~ (resolved)
- Instance: existing HARD RULES covered initial compute_candidate_macros calls but not the adjustment (row-override) branch of the setup flow.
- Resolution: capability prompt updated with three new HARD RULES covering adjustment flow; adjustment-flow section added.

---

## Sub-step 1 follow-up (gate 3 findings)

### ~~NB-18 (sub-step 1 gate 3): LLM does not disambiguate units/scope on numeric input~~ (resolved)
- Instance: "weekly deficit"; user said 1850, intending weekly. Ambiguity: does the user mean weekly kcal or daily kcal? Pattern applies to every numeric intake: TDEE (daily vs weekly avg), protein (g vs oz), fat (g vs oz), weight (lb vs kg).
- Resolution (Sub-step Z commit 2, SHA TBD): NB-18 numeric-confirmation subsection added to CLAUDE.md "LLM voice rules"; assert_metric_confirmation helper added to LLM test utils; "Missing numeric input: ask, do not infer" rule added to CLAUDE.md voice rules. Architecture locked (Yes/No/Change read-back pattern). Full LLM-test enforcement lands when check-in capability is built.

---

## Resolution log

- **NB-1** (sub-step 1): resolved in `feature/nutrios-v3-substep2-py` Task 1 commit — `mesocycles_dir()` and `active_txt_path()` promoted to `common.py`; `get_active_mesocycle.py` imports from `common` directly.
- **NB-5 (sub-step 0)**: resolved in `feature/nutrios-v3-substep2-py` Task 1 commit — `ok()`/`err()` covered by `test_ok_exits_zero_and_prints_json`, `test_ok_accepts_list`, `test_err_exits_one_and_prints_json`.
- **NB-6 (sub-step 0)**: resolved — `today_str()` covered by `test_today_str_returns_iso_date_format` and `test_today_str_timezone_affects_date`. The original Task 1 test (`test_today_str_tz_override_differs_from_utc`) only verified format, not timezone behavior; replaced with a mock-clock test that freezes time at 2026-04-25T05:30Z and asserts UTC returns "2026-04-25" while America/Denver returns "2026-04-24".
- **B-1 (sub-step 2 prep review)**: resolved in post-review commit — atomic-failure test now patches `append_jsonl` at the `write_meal_log` module level, confirming the JSONL write is what's blocked, not the trace `json.dumps`.
- **B-2 (sub-step 2 prep review)**: resolved in post-review commit — `_next_log_id` now raises `CorruptStateError` on corrupt lines (consistent with `_load_meal_logs`); test added (`test_corrupt_jsonl_raises_on_next_log_id`).
- **NB-12**: resolved in second post-review commit — `from datetime import datetime` moved to top-level imports in `get_daily_reconciled_view.py`.
- **NB-14**: resolved in second post-review commit — `recipe_id_consistency` validator rewritten with `match/case` in both `models.py` and `write_meal_log.py`; exhaustive `case _` arm added.
- **NB-15**: resolved in second post-review commit — `main()` in `get_daily_reconciled_view.py` validates `active_timezone` via `zoneinfo.ZoneInfo()` before calling `run_*`; returns `{"ok": false, "error": "unknown timezone: ..."}` on `ZoneInfoNotFoundError`.
- **NB-16**: resolved in second post-review commit — `_sum_macros` return annotated as `dict[str, int]`.
- **NB-19**: resolved in sub-step 1 follow-up #2 commit; `recompute_macros_with_overrides` tool + HARD RULE routing all adjustment math through Python.
- **NB-20**: resolved in sub-step 1 follow-up #2 commit; adjustment-flow section + three HARD RULES added to `capabilities/mesocycle_setup.md`.
- **NB-21**: resolved in sub-step 1 follow-up #3 commit; intent-change recompute HARD RULE + LLM test added.
- **NB-22**: resolved in sub-step 1 follow-up #3 commit; zero-arithmetic rule in CLAUDE.md + universal assert_no_llm_arithmetic in test utils.
- **NB-23**: resolved in sub-step 1 follow-up #3 commit (architectural lesson) and Sub-step Z commit 2 (CLAUDE.md voice rules section + assert_no_process_narration + capability cleanup). Fully closed.
- **NB-24** (closed-by-architecture, Sub-step Z commit 1): capability prompts loaded once per bot session fixed by Decision 1. turn_state tool reads capability_prompt fresh from disk on every user turn; no caching at any layer. Closed by architecture, not a code workaround.
- **NB-25** (logged Sub-step Z commit 1, open): session scope is per-bot-lifetime; stopgap atomic-rename on intent-transition boundary implemented in turn_state.py. Closure condition: migration to native OpenClaw session_control.boundary primitive when that API ships. Until then the rename stopgap is load-bearing.
- **NB-26** (resolved Sub-step Z commit 2, SHA TBD): process-narration cousins (date arithmetic, script description, offset language, intermediate values) covered by assert_no_process_narration universal helper in LLM test utils. Rule generalized in CLAUDE.md "LLM voice rules" forbidden-patterns table.
- **NB-27** (resolved Sub-step Z commit 2, SHA TBD): test-runtime parity discipline locked in CLAUDE.md "Test conditions match production conditions" section. Multi-turn harness fixture arc rewritten to reproduce the four production differences (intent bundling, continuity turn, deficit-change-after-locked-offer, override on new baseline). Fail-before-fix confirmation documented in fixture comments.

---

## Sub-step Z carry-forward

### NB-29 (sub-step Z commit 2 review): `assert_metric_confirmation` defined but unused

- File: `scripts/tests/llm/llm_test_utils.py`
- Issue: `assert_metric_confirmation` is defined and exported but has no call sites in any test fixture.
- Fix: call sites land in the check-in capability build (sub-step 2 or later). When the check-in
  capability is built, add LLM-test fixtures that call `assert_metric_confirmation` for each metric
  input field (weekly deficit, TDEE, protein floor, fat ceiling, target calories).
- Priority: low (no correctness impact; NB-18 architecture is locked).
- Target: check-in capability build.

### NB-33: Session boundary rename disabled

- File: `scripts/turn_state.py`, `compute_turn_state()`
- Reason: rename was firing too aggressively; default-to-continuation rule does not protect against intent classifier mis-calling continuation turns as new intents. Banana flow regression 2026-04-26.
- Status: deferred.
- Fix: redesign boundary detection before re-enabling `_reset_session_file`. Definition retained in `turn_state.py` for one-line re-enable. Detection still runs and logs to stderr.
- Target: boundary detection redesign (dedicated sub-step).

### NB-28 (sub-step Z commit 1 review): `_find_session_file` silently returns None for multi-candidate case

- File: `scripts/turn_state.py`, `_find_session_file()`
- Issue: when `sessions.json` contains more than one entry matching `(accountId=nutriosv2, from=telegram:<user_id>)`, the function returns `None` with no log or structured error. `_reset_session_file` silently no-ops; the boundary transition records the new intent but does not rename the session file. The user experiences stale context with no diagnosable signal.
- Fix: emit a stderr warning (or structured log) with the candidate count and session keys before returning `None`. Add a test for the multi-candidate case.
- Priority: medium (real failure mode on OpenClaw restart; low probability in practice).
- Target: sub-step Z commit 2 or standalone cleanup.
