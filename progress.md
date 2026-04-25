# NutriOS v2 — Build Progress

Branch: `feature/nutrios-v2`  
Last clean commit: `c57b155` — `docs: step 5 render review + summary`  
Suite: **183 passed, 0 failed**

---

## Files and line counts

| Module | Lines | Tests | Test count |
|---|---|---|---|
| `lib/nutrios_time.py` | 87 | `test_nutrios_time.py` (173) | 22 |
| `lib/nutrios_models.py` | 296 | `test_nutrios_models.py` (165) | 21 |
| `lib/nutrios_store.py` | 320 | `test_nutrios_store.py` (285) | 28 |
| `lib/nutrios_engine.py` | 347 | `test_nutrios_engine.py` (628) | 67 |
| `lib/nutrios_render.py` | 451 | `test_nutrios_render.py` (534) | 45 |
| **Total production** | **1501** | **Total test** | **1785 / 183** |

---

## Steps built vs. remaining

| Step | Module | Status |
|---|---|---|
| 1 | `nutrios_time.py` | ✓ complete + corrective |
| 2a | `nutrios_models.py` | ✓ complete |
| 2b | `nutrios_store.py` | ✓ complete + corrective |
| 3 | `nutrios_engine.py` | ✓ complete + corrective |
| 4 | `nutrios_mnemo.py` | **deferred** (Mnemo integration — explicit decision) |
| 5 | `nutrios_render.py` | ✓ complete + corrective — all 3 issues resolved |
| 6 | Tool shims (9 files) | **not started** |
| 6.5 | `nutrios_migrate.py` | **not started** |
| 6.6 | Tool entrypoints | **not started** |
| 7 | `prompts/` | **not started** |
| 8 | `scaffold.sh` update | **not started** |
| 9 | `INSTALL.md` update | **not started** |

Step 4 deferred by explicit decision (this session's brief). Step 6 starts after step 5 gate clears.

---

## Red tests

None. All 183 pass.

---

## Format choices made

| Element | Choice | Spec instruction | Notes |
|---|---|---|---|
| Range separator in macro line | `–` (en-dash, U+2013) | "en-dash (U+2013), not hyphen. Document the choice" | matches spec exactly |
| Negative delta sign | `−` (U+2212, MINUS SIGN) | "real minus (U+2212) or hyphen — pick one consistently" | U+2212 chosen, used in `render_kcal_line` and `render_weight_trend` |
| Date format in events | `YYYY-MM-DD` | "ISO-style `YYYY-MM-DD` for events" | `str(date_obj)` |
| Date format in daily summary header | `"Fri Apr 24"` (`%a %b %d`) | `"Mon Apr 24"` short form | leading zero stripped via `lstrip("0")` |
| Date format in protocol view notes | `YYYY-MM-DD` UTC date | not specified | UTC date from `nutrios_time.parse(ts_iso).date()` |
| Dose not-due format | `"Not a dose day. Next dose: Friday (2026-04-25)"` | not fully specified | uses `next_dose_day.capitalize()` |
| Setup complete message | Two-sentence fixed string | "one paragraph maximum" | within spec |
| Macro line total width | 32 chars | not explicit — derived from spec examples | status right-justified to fill to 32 |
| First column width | 15 chars | not explicit — derived from spec examples | "Name: actual g" always 15 |

---

## Open issues before clearing step 5 gate

All three issues resolved in step 5 corrective.

### Issue 1 — RESOLVED
`render_daily_summary` signature extended: `weigh_in_change`, `protein_status`, `carbs_status`, `fat_status`, `protein_actual`, `carbs_actual`, `fat_actual`, `kcal_actual`. Engine import removed. Engine calls moved to step 6 tool shim (not yet built).

### Issue 2 — RESOLVED
Explicit `if result.reason is None: raise ValueError(...)` guard added before template lookup. Raises clear ValueError with "reason is None" message.

### Issue 3 — RESOLVED
`weigh_in_today` now renders between date header and kcal line. `weigh_in_change` added as explicit parameter. Format: `"Weighed in: 184.2 lbs (−0.3 from last)"` with delta, or `"Weighed in: 184.2 lbs"` without. None suppresses line.

---

## Judgment calls deferred / things Sonnet is uncertain about

### `window("last_7d")` semantics
**Resolved in corrective.** Now returns today through 6 days ago (7 local days inclusive of today). Prior contract was days-2-through-8. If any caller was built against the old contract, it needs updating.

### `event_next` vs `event_today` caller contract
**Flagged in corrective review, not resolved.** `event_next` now uses strict `>` (today excluded). A caller that wants all events from today forward must call both `event_today` and `event_next`. This caller contract needs to be documented in the step 7 orchestrator prompt — it's not currently written anywhere that tools can see.

### `dose_status(today_log_entries, is_dose_day: bool)` signature
**Judgment call from step 3 corrective, accepted.** The spec's implied signature had no `is_dose_day` parameter. Added one to allow the function to return `"not_due"` (caller computes `is_dose_day` from `dose_reminder_due`). The step 6 tool shim must pass this correctly.

### `render_setup_resume_prompt` context dict shape
**Not validated.** The function accepts `context: dict` with no type enforcement. If the caller passes wrong keys, it silently uses fallbacks (`context.get("day_patterns", [])` etc.). Should be a typed model or at least documented as a typed dict. Deferred to step 6 when the setup_resume tool defines the shape.

### macOS case-sensitivity: `skills/nutriOS/` vs `skills/nutrios/`
**Known infrastructure issue from Makefile task.** Git tracks files under `skills/nutriOS/` (capital). macOS filesystem serves them from `skills/nutrios/`. Makefile targets use lowercase (what pytest can find). On a Linux/case-sensitive host, the Makefile paths would need to be `skills/nutriOS/tests`. Not urgent until deployment.

### `nutrios_time.to_local` — not tested
Added to satisfy Tripwire 3 grep. The function is a one-liner (`now.astimezone(ZoneInfo(tz))`). Not tested directly. It is exercised by `render_daily_summary` tests, but not in `test_nutrios_time.py`. Worth adding one test before step 6.

---

## Corrective items by module (what changed from initial build)

| Module | Correctives applied |
|---|---|
| `nutrios_time` | `last_7d` semantics fixed; `to_local` added (step 5) |
| `nutrios_store` | `StoreError` typed exceptions; `resolve_user_id_from_peer` non-string guard; `events.json` wrapped format |
| `nutrios_engine` | TZ propagation to all date/weekday functions; `weight_change` null guard; `event_next` strict `>` |
| `nutrios_models` | No correctives |
| `nutrios_render` | Built in step 5; corrective cleared all 3 issues |
