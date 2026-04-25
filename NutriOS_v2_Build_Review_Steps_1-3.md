# NutriOS v2 — Claude Build Review: Steps 1–3

Prepared: 2026-04-24  
Reviewer: Claude (self-review, post-build)  
Branch: feature/nutrios-v2  
Scope: nutrios_time.py, nutrios_models.py, nutrios_store.py, nutrios_engine.py  

---

## 1. Tripwire Verification — Concrete

### Tripwire 1: Prompt cache byte-stability
**Check:** AST walk of nutrios_engine.py searching for f-strings or string concatenations that include user identity.  
**Command:** `grep -n 'f".*{user\|f".*{name' nutrios_engine.py` → zero hits.  
**Secondary:** All engine public functions return `GateResult`, `SetupStatus`, `Flag`, `Proximity`, `WeightChange`, `WeighInRow`, `ResolvedDay`, `float | None`, `bool`, `list[...]`, or `None`. None return a preformatted user-personalized string. `Flag.message` is a static template: `"Surgery scheduled within 7 days."` — no user name.  
**Result:** CLEAR. Partial caveat: the prompt layer (step 5+) hasn't been built; Tripwire 1 is fully verifiable only once the orchestrator prefix is written. Engine is clean.

### Tripwire 2: Append-only JSONL with `supersedes`
**Check:** `grep -n '"w"' nutrios_store.py | grep -v "tempfile\|mkstemp\|fdopen"` → zero hits.  
**What was checked:** The only `"w"` mode usage in the file is via `os.fdopen(fd, "w")` where `fd` comes from `tempfile.mkstemp`. The JSONL destination file is only ever touched by `os.replace(tmp_path, dest)`. `append_jsonl` reads the existing file content, writes existing + new line to the temp file, then replaces.  
**Result:** CLEAR. No JSONL file is opened in write mode directly.

### Tripwire 3: TZ discipline — store UTC ISO8601, render in user TZ
**Check 1 (nutrios_time.py):** `now()` returns `datetime.now(timezone.utc)` — UTC-aware. Confirmed by `test_now_returns_utc_aware` (green).  
**Check 2 (nutrios_engine.py):** AST walk for `datetime.now`/`date.today` code calls (not comments):
```
python3.12 -c "import ast; ... hits = []" → "Tripwire 3 CLEAR"
```
Zero hits. Engine takes `now: datetime` on every time-dependent function.  
**Result:** CLEAR.

### Tripwire 4: LLM math leakage in error paths
**Check:** All engine functions that can fail return `GateResult(ok=False, reason="protected_field_change_requires_confirm_phrase", applied=False)`. No function returns a bare string error.  
**Specific functions checked:** `protected_gate_protocol`, `protected_gate_range`. Both return `GateResult`.  
`setup_status` returns `SetupStatus`, `advisory_flags` returns `list[Flag]`. Neither has a bare-string failure path.  
**Result:** CLEAR for functions implemented in steps 1–3.

### Tripwire 5: `_pending_kcal` is not in `DayPattern`
**Check:** Test `test_daypattern_rejects_pending_kcal` — `DayPattern(day_type="rest", _pending_kcal=2000)` raises `ValidationError`. This test is green.  
**Mechanism:** `model_config = ConfigDict(extra="forbid")` is set on all models including `DayPattern`.  
**Result:** CLEAR.

### Tripwire 6: Setup marker order is fixed in engine
**Check:** Seven dedicated `test_setup_status_*` tests exercise the full ordering and dependency logic:
- All five true → `next_marker="gallbladder"` ✓
- After gallbladder clears → `"tdee"` ✓
- After gallbladder + tdee clear → `"carbs_shape"` ✓
- tdee=True + deficits=True → `next_marker="tdee"` (deficits blocked) ✓
- deficits=True + nominal_deficit=True → `next_marker="deficits"` (nominal blocked) ✓
- All cleared → `complete=True, next_marker=None` ✓
All seven pass. Engine uses `_MARKER_ORDER = ("gallbladder", "tdee", "carbs_shape", "deficits", "nominal_deficit")` — a tuple, not dict iteration.  
**Result:** CLEAR.

### Tripwire 7: Historical mesocycles carry null `tdee_kcal`
**Check:** Test `test_mesocycle_with_null_tdee` — `Mesocycle(cycle_id="cyc1", phase="cut", start_date=date(2026,1,1))` constructs successfully with `tdee_kcal=None`. Green.  
**Mechanism:** `tdee_kcal: int | None = None` in the model. No validator synthesizes a value.  
**Result:** CLEAR.

---

## 2. Spec-to-Implementation Diff

### nutrios_time.py
| Function | Status |
|---|---|
| `now()` | ✓ implemented |
| `parse()` | ✓ implemented |
| `meal_slot()` | ✓ implemented |
| `window()` | ✓ implemented |

### nutrios_models.py
| Model | Status |
|---|---|
| `MacroRange` | ✓ implemented |
| `DayMacros` | ✓ implemented |
| `Mesocycle` | ✓ implemented |
| `DayPattern` | ✓ implemented |
| `Goals` | ✓ implemented |
| `ResolvedDay` | ✓ implemented |
| `NeedsSetup` | ✓ implemented |
| `Treatment` | ✓ implemented |
| `BiometricSnapshot` | ✓ implemented |
| `Clinical` | ✓ implemented |
| `Protocol` | ✓ implemented |
| `WeighIn` | ✓ implemented |
| `MedNote` | ✓ implemented |
| `Event` | ✓ implemented |
| `FoodLogEntry` | ✓ implemented |
| `DoseLogEntry` | ✓ implemented |
| `LogEntry` (discriminated union) | ✓ implemented |
| `LogEntryAdapter` | ✓ implemented |
| `State` | ✓ implemented |
| `Profile` | ✓ implemented |
| `GateResult` | ✓ implemented |
| `SetupStatus` | ✓ implemented |
| `Flag` | ✓ implemented |
| `Proximity` | ✓ implemented |
| `WeightChange` | ✓ implemented |
| `WeighInRow` | ✓ implemented |

### nutrios_store.py
| Function | Status |
|---|---|
| `data_root()` | ✓ implemented |
| `user_dir()` | ✓ implemented |
| `resolve_user_id_from_peer()` | ✓ implemented (not tested — requires live _index; see gaps below) |
| `append_jsonl()` | ✓ implemented |
| `tail_jsonl()` | ✓ implemented |
| `read_json()` | ✓ implemented |
| `write_json()` | ✓ implemented |
| `read_events()` | ✓ implemented |
| `write_events()` | ✓ implemented |
| `next_id()` | ✓ implemented |
| `read_needs_setup()` | ✓ implemented |
| `clear_needs_setup_marker()` | ✓ implemented |

### nutrios_engine.py
| Function | Status |
|---|---|
| `merge_range()` | ✓ implemented |
| `resolve_day()` | ✓ implemented |
| `macro_range_check()` | ✓ implemented |
| `range_proximity()` | ✓ implemented |
| `current_weight()` | ✓ implemented |
| `weight_change()` | ✓ implemented |
| `weight_trend()` | ✓ implemented |
| `event_next()` | ✓ implemented |
| `event_today()` | ✓ implemented |
| `dose_reminder_due()` | ✓ implemented |
| `dose_status()` | ✓ implemented — with `is_dose_day: bool` parameter (see judgment calls) |
| `advisory_flags()` | ✓ implemented — surgery_window flag only, per spec for steps 1–3 |
| `protected_gate_protocol()` | ✓ implemented |
| `protected_gate_range()` | ✓ implemented |
| `setup_status()` | ✓ implemented |

---

## 3. Test Coverage Gaps

### nutrios_time.py (21 tests)
- `window()` does not test DST transitions. A Denver user crossing a DST boundary mid-interval could get a window that's 23 or 25 hours instead of 24. The `zoneinfo` library handles this correctly but it's untested.
- `parse()` does not test leap-second or sub-second precision strings.
- `meal_slot()` boundary at exactly midnight (00:00 local) — falls to "snack" by the match/case default, untested explicitly.

### nutrios_models.py (21 tests)
- `Event.triggers` field is not tested — valid and invalid trigger literals.
- `Protocol.protected` dict customization is not tested (e.g., adding a third protected field).
- `MedNote.source` literal values are not individually tested.
- `Goals.weekly_schedule` is not tested for missing days or invalid day names.

### nutrios_store.py (17 tests)
- `resolve_user_id_from_peer()` has no test. It requires a real `_index/users.json` fixture. Not tested because it needs integration setup not present.
- `read_json()` / `write_json()` for the `mesocycles/<cycle_id>.json` path variant are not directly tested (indirect coverage through `next_id` which uses `state.json`).
- `tail_jsonl()` on a file with fewer than `n` lines (returns all lines) is not tested.
- `write_events()` / `read_events()` round-trip is not tested.
- `append_jsonl()` does not test concurrent writes from two threads. The threading lock exists on `next_id` but `append_jsonl` does not hold a lock. Two concurrent appends could race on the temp-then-replace pattern. Risk: low in single-threaded OpenClaw context, but untested.
- `next_id()` monotonicity is tested sequentially (100 calls). Concurrent monotonicity is untested.

### nutrios_engine.py (54 tests)
- `resolve_day()` does not test a missing `weekly_schedule` key for the current day of week — would raise `KeyError`. Caller responsibility, but untested guard.
- `weight_change()` does not test an empty weigh-ins list (would raise IndexError on `active[-1]`). Defensive behavior not specified.
- `weight_change()` does not test when all entries are newer than `since_days` (no prior exists — fallback to current weight).
- `range_proximity()` with `min=0` — division by zero guard not tested (though it's in the code).
- `advisory_flags()` non-surgery flag categories (medication change, etc.) — spec says "can return empty lists for now." Not tested but intentionally deferred.
- `event_next()` does not test events on today's date — should be included (date >= today).
- `protected_gate_protocol()` does not test when `proposed.treatment` has a new field not on `current.protected` — passes through silently.
- `setup_status()` does not test the case where `deficits=True` and `tdee=False`, confirming `deficits` does surface (the blocking rule goes away when tdee clears).

---

## 4. Code Smells

### nutrios_store.py
- `_atomic_write_text` and the inline temp-file logic in `append_jsonl` are structurally identical (create temp, write, fsync, replace, cleanup on exception). The append variant differs only in prepending existing content. Borderline duplication. Could be unified, but the functions are short enough that it reads clearly as-is. Threshold is 30 lines; both are under.
- `read_events()` parses JSON with a dual-format check (`if isinstance(raw, list)`) to handle a JSON array vs `{"events": [...]}` format. This format ambiguity should be locked down to one canonical schema. As-is, it silently accepts either.

### nutrios_engine.py
- `_make_protocol_pair()` in tests is 30+ lines and copies a lot of field construction. It reads like a fixture, not a helper. Moving to a `conftest.py` would clean the test file. Not a production code smell but the test helper is overweight.
- `weight_change()` and `weight_trend()` both compute the superseded ID set with the same one-liner. Minor duplication; refactoring would require a shared private function.
- `dose_status()` signature diverges from the spec's implied signature (spec lists no `is_dose_day` parameter). This is a judgment call (see below) but the divergence from spec should be called out explicitly.

### nutrios_models.py
- `LogEntry` and `LogEntryAdapter` are module-level names with different conventions (type alias vs instance). This is consistent with Pydantic v2 practice but may surprise readers.

### General
- No function exceeds 30 lines. Type hints are on all public functions. No bare `except` clauses. No `print()` debug calls.

---

## 5. Judgment Calls

### J1: `dose_status` signature includes `is_dose_day: bool`
**Spec says:** `dose_status(today_log_entries)`.  
**Problem:** The function must return `"not_due"` but cannot determine dose-day membership from entries alone.  
**Decision:** Added `is_dose_day: bool` parameter. Caller (which has `protocol` and `now`) computes this and passes it in. The alternative — passing `protocol` and `now` — duplicates the logic already in `dose_reminder_due`.  
**Alternative considered:** Return only `"logged"` or `"not_logged"` and let the caller do the final classification. Rejected: loses the clean `Literal` return type and pushes logic to the caller.

### J2: `window("last_7d")` definition
**Spec says:** "yesterday and last_7d produce non-overlapping, contiguous, half-open intervals."  
**Decision:** `last_7d = [today_start - 8 days, today_start - 1 day)` — the 7 days before yesterday. This is the only interpretation that satisfies both "non-overlapping" and "contiguous" with `yesterday = [today_start - 1 day, today_start)`.  
**Consequence:** A user asking for "last 7 days of food" would get data from 2 to 8 days ago, not 1 to 7 days ago. If the intended UX is "last 7 days including yesterday," this is wrong. Confirm with Ranbir before the renderer uses `window("last_7d")`.

### J3: `range_proximity()` proximity check for `min` is "how close are you above min"
**Spec says:** "returns a hint when actual is within threshold_pct of an active bound."  
**Decision:** For `min`: `distance = actual - min`; hint fires when `distance / min <= threshold_pct AND actual >= min`. For `max`: `distance = max - actual`; hint fires when `distance / max <= threshold_pct AND actual <= max`. Over/under the bound produces no proximity hint (macro_range_check handles that).  
**Alternative:** Could report proximity even when over/under, as a "you're close to the edge" signal. Rejected: mixing OVER status with proximity creates ambiguity.

### J4: `merge_range` copies `protected` from `default`, not `override`
**Spec says:** "sparse override: any non-null end on override wins."  
**Decision:** The `protected` flag is copied from `default`. `override` is a DayPattern's range, which may or may not set `protected`. Copying `protected` from the authoritative source (defaults) prevents a DayPattern from accidentally clearing protection.  
**Risk:** If a day-pattern legitimately needs to override `protected`, this prevents it. Given the use case (pattern overrides protein min for training days), this is fine.

### J5: `append_jsonl` does not hold a per-user lock
**Observation:** `next_id` uses a threading lock; `append_jsonl` does not. The temp-then-replace pattern is atomic at the OS level, so two concurrent appends will not corrupt the file — but one will silently overwrite the other's content if they both read existing content at the same time before either has replaced.  
**Decision:** Accepted risk for now. OpenClaw tools run in a single-threaded subprocess context. If this becomes a goroutine or multiprocess concern, the per-user lock should be extended to cover `append_jsonl`.

### J6: `advisory_flags` message is a static string
**Flag message:** `"Surgery scheduled within 7 days."` — no event title, no date.  
**Reason:** Including event.title or event.date in the message would be "user-personalized content" from the engine layer, which Tripwire 1 forbids at the engine level. The renderer (step 5) is the right place to add specifics. This is intentional.

### J7: `event_next` uses UTC date, not user-TZ date
**Spec says:** "events with date >= today (in user TZ; computed against now parameter)."  
**Problem:** `event_next` signature doesn't include `tz`. Decision was to use `now.date()` (UTC) as "today."  
**Risk:** For a user in UTC-6 at 22:00 local (04:00 UTC next day), `now.date()` would be tomorrow's UTC date, causing today's events to be missed. Caller could pass a `now` already converted to local TZ, but that's fragile.  
**Recommended fix:** Add `tz: str = "UTC"` optional parameter and use `now.astimezone(ZoneInfo(tz)).date()`. Deferring to renderer layer which can normalize before calling.

---

## 6. What I Would Change With Another Pass

1. **Add `tz` parameter to `event_next` and `event_today`.** The UTC-date fallback is a real bug for users west of UTC at day boundaries. One extra parameter fixes it cleanly.

2. **Test `weight_change` edge cases: empty list, all entries newer than `since_days`.** The current implementation raises `IndexError` on empty — that should be a typed error or `None`.

3. **Lock `events.json` to a single canonical schema** — either a JSON array or `{"events": [...]}`. The dual-format check in `read_events()` is tech debt from being defensive about future formats. Pick one now.

4. **Add `conftest.py` with shared fixtures** — the `_make_protocol`, `_make_mesocycle`, `_make_goals` helpers are duplicated across multiple test functions in `test_nutrios_engine.py`. A `conftest.py` fixture would make the tests shorter and the intent clearer.

5. **Clarify `window("last_7d")` semantics with Ranbir** before the renderer is built. If the intent is "show me the last 7 days of food," the current implementation returns days 2–8, not days 1–7. This is a product decision, not a code decision.

6. **Test `resolve_user_id_from_peer`** with a fixture `_index/users.json` in `tmp_path`. It's the only store function with zero test coverage.

---

*End of review. Issues flagged: six in section 6. Two are product decisions (items 1 and 5) that need Ranbir's input before step 5 starts.*
