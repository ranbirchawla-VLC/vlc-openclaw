# NutriOS v2 — Corrective Review: Step 5 Fixes

**Branch:** `feature/nutrios-v2`  
**Scope:** `skills/nutriOS/lib/nutrios_render.py` + `skills/nutriOS/tests/test_nutrios_render.py`  
**Review spec:** `~/.claude/review.md` (global) + corrective brief  
**Result: PASS — no stop conditions triggered**

---

## 1. Stop Conditions

| # | Condition | Finding |
|---|---|---|
| 1 | Secrets in code or committed config | None. No credentials, keys, or env-var access. |
| 2 | Bare `except` or `except Exception:` without re-raise | None. No exception handling added. |
| 3 | External call without explicit timeout | None. Render is pure functions. No I/O. |
| 4 | New behavior without a test | 7 new tests added, 3 existing tests updated. All new branches covered. |
| 5 | New request entry / LLM call / external integration without log event | None. No new integrations. |
| 6 | `shell=True` with non-constant input | None. No subprocess calls. |
| 7 | LLM call with prompt inlined | None. No LLM calls. |
| 8 | Dependency added without pinned version | None. No new deps. |
| 9 | PII sent to LLM API without policy | None. No LLM calls. |
| 10 | Schema/state migration without rollback path | None. No data model changes. |

---

## 2. Engine Import Audit

Command run:
```
grep -rn "from nutrios_engine\|import nutrios_engine" skills/nutriOS/lib/nutrios_render.py
```

Output: **no output** — zero hits. Fix 1 is clean.

The old inline `from nutrios_engine import macro_range_check` at line 370 is gone. The `render_daily_summary` docstring now states "No engine import here." The module-level imports are unchanged; nutrios_engine is not referenced anywhere in the render module.

---

## 3. Signature Change Blast Radius

`render_daily_summary` gained 8 new parameters:  
`weigh_in_change`, `protein_status`, `carbs_status`, `fat_status`, `protein_actual`, `carbs_actual`, `fat_actual`, `kcal_actual`

Command run:
```
grep -rn "render_daily_summary(" skills/nutriOS/
```

All call sites:

| File | Line | Status |
|---|---|---|
| `skills/nutriOS/lib/nutrios_render.py` | 349 | Definition — updated |
| `skills/nutriOS/tests/test_nutrios_render.py` | 354 | `test_render_daily_summary_basic` — updated |
| `skills/nutriOS/tests/test_nutrios_render.py` | 380 | `test_render_daily_summary_advisory_first` — updated |
| `skills/nutriOS/tests/test_nutrios_render.py` | 403 | `test_render_daily_summary_no_trailing_newline` — updated |
| `skills/nutriOS/tests/test_nutrios_render.py` | 424 | `test_render_daily_summary_all_unset_suppresses_macro_lines` — new |
| `skills/nutriOS/tests/test_nutrios_render.py` | 447 | `test_render_daily_summary_weigh_in_with_delta` — new |
| `skills/nutriOS/tests/test_nutrios_render.py` | 470 | `test_render_daily_summary_weigh_in_no_delta` — new |
| `skills/nutriOS/tests/test_nutrios_render.py` | 492 | `test_render_daily_summary_no_weigh_in` — new |
| `skills/nutriOS/tests/test_nutrios_render.py` | 513 | `test_render_daily_summary_weigh_in_position` — new |

No production call sites exist yet — step 6 tool shims are not built. When step 6 builds, the tool caller must pass all 8 new parameters after computing them via `nutrios_engine`. This is by design.

---

## 4. New and Modified Test Names

### New tests (7 total)

**Fix 2 — `render_gate_error` None guard:**
- `test_render_gate_error_raises_on_none_reason`
- `test_render_gate_error_raises_on_unknown_reason`

**Fix 1 — signature change verification:**
- `test_render_daily_summary_all_unset_suppresses_macro_lines`

**Fix 3 — weigh-in rendering:**
- `test_render_daily_summary_weigh_in_with_delta`
- `test_render_daily_summary_weigh_in_no_delta`
- `test_render_daily_summary_no_weigh_in`
- `test_render_daily_summary_weigh_in_position`

### Existing tests modified (signature plumbing only, no new assertions):
- `test_render_daily_summary_basic`
- `test_render_daily_summary_advisory_first`
- `test_render_daily_summary_no_trailing_newline`

---

## 5. Section 6 — Tests and Evals

- **New behavior tested:** all three fixes have tests before the implementation landed. TDD discipline held.
- **Property assertions:** all `assert "x" in result` or `assert positions`. No snapshot matches.
- **Unhappy paths:** Fix 2 adds both None-reason and unknown-reason ValueError tests. Fix 3 has explicit suppression test (`weigh_in_today=None`). Fix 1 has explicit UNSET suppression test.
- **Tests verify behavior, not implementation:** no test breaks on internal renames.
- **Build time:** 183 tests in 0.15s.

---

## 6. Findings

None blocking. Two observations for the carry-forward log:

**Observation A — `weigh_in_change` when `delta_lbs == 0`.**  
If `delta_lbs` is exactly 0.0, the current logic renders `"+0.0 from last"` (positive branch). This is cosmetically odd but not incorrect. The spec doesn't address zero-delta. Document for step 6 when it builds the engine→render handoff.

**Observation B — `kcal_actual` type is `int` but callers may pass float.**  
The signature says `kcal_actual: int`. Callers summing `FoodLogEntry.kcal` fields (which are `int` per the model) will pass int correctly. Fine as-is. Step 6 tool caller should not pass a float here.

---

## 7. Verdict

**PASS.** No stop conditions. Engine import clean. All call sites updated. 183/183 tests pass.
Branch holds. Step 6 gate: pending Ranbir review.
