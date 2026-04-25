# NutriOS v2 — Corrective Summary: Steps 1–3

Prepared: 2026-04-24  
Branch: feature/nutrios-v2  

---

## Files Touched

| File | Lines Before | Lines After | Delta |
|---|---|---|---|
| `lib/nutrios_time.py` | 79 | 78 | −1 |
| `lib/nutrios_engine.py` | 329 | 347 | +18 |
| `lib/nutrios_store.py` | 280 | 314 | +34 |
| `tests/test_nutrios_time.py` | 159 | 173 | +14 |
| `tests/test_nutrios_engine.py` | 522 | 628 | +106 |
| `tests/test_nutrios_store.py` | 184 | 277 | +93 |

---

## Tests Added Per Fix

| Fix | Tests Added | Description |
|---|---|---|
| Fix 1 — last_7d semantics | +4 (−2 stale) | Net +2; rolling 7-day window including today |
| Fix 2 — TZ propagation | +11 | resolve_day (2), event_today/next (4), dose_reminder_due (2), advisory_flags (2), event_next-excludes-today (1) |
| Fix 3 — weight_change guard | +4 | empty list, no-prior, all-recent, two-entries-8-days |
| Fix 4 — resolve_user_id_from_peer | +5 | happy path, missing peer, missing index, malformed JSON, path-traversal |
| Fix 5 — events.json format | +5 | write produces wrapped, read wrapped, missing→[], raw-list raises, round-trip |

---

## Test Counts

| Module | Tests Before | Tests After |
|---|---|---|
| `test_nutrios_time.py` | 21 | 22 (+2 new, −1 stale contiguous, removed non-overlapping) |
| `test_nutrios_models.py` | 21 | 21 (unchanged) |
| `test_nutrios_store.py` | 17 | 27 (+10) |
| `test_nutrios_engine.py` | 54 | 67 (+13) |
| **Total** | **113** | **137** |

`137 passed, 0 failed, 0 skipped` — confirmed via `scripts/runtests nutrios-workspace/skills/nutrios/tests/ -q`.

---

## Commits (corrective pass only)

```
fix(time): last_7d includes today — rolling 7-day window ending at tomorrow-start
fix(engine): TZ propagation — resolve_day, event_next/today, dose_reminder_due, advisory_flags
fix(engine): weight_change returns None on empty/no-prior — matches current_weight pattern
fix(store): resolve_user_id_from_peer — StoreError typed exceptions, JSON parse guard, 5 tests
fix(store): events.json locked to wrapped format + StoreError for parse failures
```

---

## Known Issues (see Corrective Review for full detail)

1. `resolve_user_id_from_peer` does not validate that the returned value is a `str` — 2-line fix recommended before step 4.
2. `event_next` caller contract (must pair with `event_today` to see today's events) needs documenting in step 7 prompts.
3. Positive-UTC-offset TZ test missing for `resolve_day`.

Branch holds. Step 4 (Mnemo) does not begin until the gate clears.
