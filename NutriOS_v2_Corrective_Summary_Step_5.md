# NutriOS v2 — Corrective Summary: Step 5

**Branch:** `feature/nutrios-v2`  
**Suite before corrective:** 176 passed  
**Suite after corrective:** 183 passed (+7)

---

## File diff

| File | Lines before | Lines after | Delta |
|---|---|---|---|
| `skills/nutriOS/lib/nutrios_render.py` | 436 | 451 | +15 |
| `skills/nutriOS/tests/test_nutrios_render.py` | 376 | 534 | +158 |

---

## Test count delta

| Phase | Tests |
|---|---|
| Step 5 complete (pre-corrective) | 176 |
| After Fix 2 (gate error None guard) | 178 (+2) |
| After Fix 1 + Fix 3 (signature + weigh-in) | 183 (+5) |
| **Total after corrective** | **183** |

---

## What changed

### Fix 1 — `render_daily_summary` no longer calls `nutrios_engine`

Signature extended with 8 new parameters: `weigh_in_change`, `protein_status`, `carbs_status`, `fat_status`, `protein_actual`, `carbs_actual`, `fat_actual`, `kcal_actual`. The inline `from nutrios_engine import macro_range_check` and three engine calls are gone. Caller (step 6 tool shim) computes all values and passes them in.

### Fix 2 — `render_gate_error` explicit None guard

Added `if result.reason is None: raise ValueError(...)` before the template lookup. Gives a precise error message for the semantically invalid case (`ok=False, reason=None`) rather than a generic "no template for None" message. Added `test_render_gate_error_raises_on_none_reason` and `test_render_gate_error_raises_on_unknown_reason`.

### Fix 3 — `weigh_in_today` renders in daily summary

Weigh-in line appears between the date header and the kcal line. Format:
- Both set: `Weighed in: 184.2 lbs (−0.3 from last)` — uses `_MINUS` (U+2212) for negative delta, `+` for positive
- Change is None: `Weighed in: 184.2 lbs`
- `weigh_in_today` is None: line suppressed entirely

`weigh_in_change` is now an explicit parameter — caller computes it via `engine.weight_change`. Render does not call engine.

---

## Open issues resolved

| Issue | Status |
|---|---|
| Issue 1 — engine import in render | Resolved |
| Issue 2 — KeyError vs ValueError on None reason | Resolved |
| Issue 3 — weigh_in_today unused | Resolved |

---

## Carry-forward (unchanged)

- `event_today` / `event_next` caller contract needs documenting in step 7 orchestrator prompt
- `nutrios_time.to_local` not directly tested in `test_nutrios_time.py` (exercised via render tests)
- macOS case-sensitivity `skills/nutriOS/` vs `skills/nutrios/` — known, not urgent until deployment
