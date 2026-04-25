# NutriOS v2 — Corrective Review: Steps 1–3

Prepared: 2026-04-24  
Reviewer: Claude (self-review, post-corrective-pass)  
Branch: feature/nutrios-v2  
Scope: Five fixes from `NutriOS_v2_Build_Review_Steps_1-3.md`

---

## 1. Tripwire Verification — Concrete

### Tripwire 2: Append-only JSONL with `supersedes`
**Check:** `grep -n '"w"' nutrios_store.py | grep -v "fdopen\|mkstemp"` → zero hits.  
None of the five fixes touched JSONL append paths. Fix 5 only modified `read_events`/`write_events`, which use atomic whole-file rewrite for a JSON file (not a JSONL file). Tripwire 2 scope is JSONL only. **CLEAR.**

### Tripwire 3: TZ discipline
**Primary check (engine):** AST walk for `datetime.now`/`date.today` code calls:
```
python3.12 -c "import ast; ..." → "Tripwire 3 CLEAR"
```
Zero hits.

**Secondary check — every engine function enumerated:**

| Function | TZ handling | Status |
|---|---|---|
| `resolve_day(now, tz, goals, mesocycle)` | converts `now` via `ZoneInfo(tz)` before weekday name | ✓ |
| `event_next(events, now, tz, n)` | `now.astimezone(ZoneInfo(tz)).date()` for local today | ✓ |
| `event_today(events, now, tz)` | `now.astimezone(ZoneInfo(tz)).date()` | ✓ |
| `dose_reminder_due(protocol, entries, now, tz)` | `now.astimezone(ZoneInfo(tz)).strftime("%A")` | ✓ |
| `advisory_flags(protocol, events, meso, now, tz)` | `now.astimezone(ZoneInfo(tz)).date()` | ✓ |
| `current_weight(weigh_ins)` | no date math; no `tz` needed | ✓ |
| `weight_change(weigh_ins, now, since_days)` | arithmetic on ISO8601 timestamps; no calendar-day semantics; `tz` not needed | ✓ |
| `weight_trend(weigh_ins, last_n)` | sorts by ID; extracts UTC date from ts_iso for display; no calendar-day semantics | ✓ |
| `merge_range`, `macro_range_check`, `range_proximity` | no time | ✓ |
| `protected_gate_protocol`, `protected_gate_range` | no time | ✓ |
| `setup_status` | no time | ✓ |
| `dose_status` | no time | ✓ |

**CLEAR.**

### Tripwires 1, 4, 5, 6, 7
Unchanged from the steps 1–3 review. None of the five fixes touched these paths. No new user-personalized strings added to engine return values; no new bare-string error returns. **All still CLEAR.**

---

## 2. Fix-to-Implementation Diff

### Fix 1 — `window("last_7d")` includes today
**Files changed:** `nutrios_time.py`, `test_nutrios_time.py`  
**Change:** `last_7d` case updated from `(local_today - 8 days, local_today - 1 day)` to `(local_today - 6 days, local_today + 1 day)`. Two stale tests removed (contiguous-with-yesterday, non-overlapping-with-yesterday), four new tests added: span-is-7-days, starts-at-local-6-days-ago, contains-now, excludes-7-days-plus-1-min.  
**Diff (approx):** +33 lines test, -20 lines test, +2 lines impl.

### Fix 2 — TZ propagation through engine
**Files changed:** `nutrios_engine.py`, `test_nutrios_engine.py`  
**Change:** `_weekday_name`, `resolve_day`, `event_next`, `event_today`, `dose_reminder_due`, `advisory_flags` all gained `tz: str` parameter. All six functions convert `now` through `ZoneInfo(tz)` before extracting date or weekday. `event_next` changed from `>=` to `>` (today's events go to `event_today`). All existing calls updated to pass `tz="UTC"`. New TZ boundary tests: 2 for `resolve_day`, 3 for `event_today`/`event_next`, 2 for `dose_reminder_due`, 2 for `advisory_flags`.  
**Diff (approx):** +122 lines test, +38 lines impl.

### Fix 3 — `weight_change` empty guard
**Files changed:** `nutrios_engine.py`, `test_nutrios_engine.py`  
**Change:** Return type changed from `WeightChange` to `WeightChange | None`. Added three guard returns: empty list, all-active-empty (all superseded), no entry older than cutoff. Four new tests.  
**Diff (approx):** +37 lines test, +8 lines impl.

### Fix 4 — `resolve_user_id_from_peer` tests + `StoreError`
**Files changed:** `nutrios_store.py`, `test_nutrios_store.py`  
**Change:** `StoreError(Exception)` class added to store module. `resolve_user_id_from_peer` upgraded from bare `KeyError` raises to `StoreError` with named messages. JSON parse errors caught and wrapped. Non-dict index shape caught. Five new tests: happy path, missing peer, missing index, malformed JSON, path-traversal documentation.  
**Diff (approx):** +69 lines test, +22 lines impl.

### Fix 5 — `events.json` locked to wrapped format
**Files changed:** `nutrios_store.py`, `test_nutrios_store.py`  
**Change:** `read_events` now rejects raw-list format with `StoreError` pointing at migration. `write_events` now always writes `{"version": 1, "events": [...]}`. Five new tests: write produces wrapped format, read wrapped returns events, missing file returns `[]`, raw-list raises, round-trip equality.  
**Diff (approx):** +69 lines test, +12 lines impl.

---

## 3. Test Coverage Gaps

### Fix 1 — window("last_7d")
- DST crossing untested: a Denver user whose 7-day window spans the DST boundary (e.g., Nov 1 rollback) gets correct UTC boundaries from `zoneinfo` but it's not tested explicitly.
- `window("last_7d")` when `now` is exactly at local midnight is not tested (edge case: the day just rolled over).

### Fix 2 — TZ propagation
- `resolve_day` does not test a user in a positive UTC offset (e.g., Asia/Tokyo at UTC+9) crossing the UTC day boundary. The fix works correctly via `ZoneInfo` but this positive-offset case is untested.
- `event_next` does not test when `events` is empty (returns `[]` — obvious from implementation but not asserted).
- `advisory_flags` TZ boundary test uses a UTC-6 user. A UTC+14 (Pacific/Kiritimati) user where local day is ahead of UTC by 14 hours is not tested.
- `dose_reminder_due` only tests one timezone (America/Denver). A user crossing midnight in UTC+14 is not tested.
- The interaction between `dose_reminder_due` and `event_today` when the dose day is also an event day is not tested (caller concern, but worth noting).

### Fix 3 — weight_change empty guard
- `weight_change` with a fully-superseded list (all entries have supersedes) → active is empty → returns `None`. This is a new code path (the `if not active: return None` guard) but not tested.
- `weight_change` where `since_days=0` is not tested (would return None since no entry is strictly before now, unless there's a zeroth-day entry).

### Fix 4 — resolve_user_id_from_peer
- Non-string values in the index (e.g., `{"telegram:12345": 42}`) are not tested. Currently returns `42` (an int) without validation. The downstream `user_dir()` would fail on it, but `resolve_user_id_from_peer` does not validate the returned value type.
- Concurrent reads of `_index/users.json` are not tested (no lock; the file is read-only in normal operation, so this is low risk).

### Fix 5 — events.json format
- `read_events` on a file where `"events"` key exists but its value is not a list (e.g., `{"events": "oops", "version": 1}`) — Pydantic validation would raise but the error message would not be the "wrapped format" `StoreError`. Not tested.
- `write_events` with an empty list is not tested (should produce `{"version": 1, "events": []}`).
- `read_events` does not test whether it handles future version numbers gracefully (e.g., version=2). Currently passes through without checking version.

---

## 4. Code Smells

### nutrios_engine.py
- `_weekday_name(now, tz)` is a one-liner helper. The `tz` parameter must now be threaded through every caller. This is correct but verbose. The pattern is consistent — no smell, just notation.
- `advisory_flags` now takes five parameters including `tz`. The function does only one useful thing in steps 1–3 (surgery_window). When more flag categories are added in step 5+, the function will grow significantly. Worth noting for the next pass.

### nutrios_store.py
- `StoreError` is defined at module level but not re-exported via `__all__` or documented in `__init__.py`. Callers need `from nutrios_store import StoreError` or `store.StoreError`. Consistent with the existing approach.
- `read_events` and `write_events` now have asymmetric error handling: `read_events` catches `json.JSONDecodeError` and wraps it; `read_json` (the generic JSON reader) does not — it lets `pydantic.ValidationError` propagate. This is a minor inconsistency.

### test_nutrios_engine.py
- The `_make_protocol_pair` helper is still 30+ lines. Not addressed in this pass (noted in original review, deferred per "no bundled refactors" rule).
- The `_make_goals` helper now hardcodes `weekly_schedule={"friday": day_type}` which is fine for UTC-based tests, but the new TZ tests bypass it and construct `Goals` directly. Two parallel patterns for the same fixture. Low priority.

---

## 5. Judgment Calls

### J1: `StoreError` added for Fix 4
**Decision:** Introduced `StoreError(Exception)` as the module-level error type for store failures (missing index, parse failure, peer not found).  
**Why:** The corrective prompt says "typed exceptions with named messages." `KeyError` is a typed exception but its conventional meaning is "key not found in dict" — using it for "file not found" and "parse error" is a misuse. `StoreError` is specific, non-ambiguous, and gives callers a single type to catch.  
**Alternative:** `LookupError` for index misses, `ValueError` for parse errors. Rejected: two different types complicates caller error handling.

### J2: Path-traversal in resolve_user_id_from_peer — relying on user_dir() downstream
**Decision:** `resolve_user_id_from_peer` does not validate the `channel_peer` string. It treats the peer as an opaque lookup key. If `"../../../etc/passwd"` is a key in the index, the function returns the mapped `user_id` value. The test documents this explicitly and asserts that the returned value (a valid user_id) passes through.  
**Why:** The peer string is not a path — it's a Telegram/Slack/etc identifier. Blocking `"../../../etc/passwd"` as a peer key is belt-and-suspenders: the returned user_id is always validated by `user_dir()`. Adding peer-string validation would create a second validation layer with different rules, which is harder to reason about.  
**Risk:** If an adversarial peer string were added to the index by another code path, this function would pass it through. The `_index/users.json` is written by `scaffold.sh` and the migrator, both trusted — not by user input.

### J3: `event_next` changed from `>=` to `>` (today's events excluded)
**Decision:** `event_next` now returns events strictly after local today (`event.date > today`). Today's events belong to `event_today` only.  
**Why:** The corrective prompt explicitly requires: "an event dated `today` (local) is excluded from 'next' and included in 'today'." This overrides the original `>=` spec from Extension v3.  
**Risk:** If a caller calls both `event_today` and `event_next`, today's event appears once (in `event_today`). If a caller calls only `event_next`, today's events are silently excluded. The caller must know to also call `event_today` to see today's events. Document in the turn contract.

### J4: `window("last_7d")` now overlaps with `window("today")`
**Decision:** Per Fix 1, `last_7d = [today-6d, tomorrow)`. `today = [today-0d, tomorrow)`. These overlap: the current day is in both.  
**Why:** The corrective prompt explicitly says the old "non-overlapping, contiguous" constraint was wrong and the new intent is a rolling 7-day window including today. Accepted intentional overlap.  
**Risk:** Any code that uses both `last_7d` and `today` windows for totals would double-count today. The renderer must de-duplicate or choose one. Not relevant until step 5.

### J5: `weight_change` return type is `WeightChange | None` — caller must check
**Decision:** `None` is returned (not a zero-delta `WeightChange`) when no comparable prior entry exists.  
**Why:** A zero-delta `WeightChange` (current == prior) is indistinguishable from "no data" unless the caller inspects a separate `has_prior` field. Returning `None` is unambiguous. Matches the `current_weight() -> float | None` pattern.

### J6: `read_events` does not validate `version` field
**Decision:** `version` is written (always `1`) but not checked on read.  
**Why:** The corrective prompt says "engine and store ignore it; future migrations may inspect it." No version check was specified. Adding a check now would require a migration strategy that doesn't exist yet.

---

## 6. What I Would Change With Another Pass

1. **Test `weight_change` with a fully-superseded list.** The `if not active: return None` guard is tested implicitly by `test_current_weight_empty`, but `weight_change` has its own guard that hits the same path and is not directly exercised.

2. **Validate the return value type of `resolve_user_id_from_peer`.** Currently returns whatever type the index value is (`int`, `list`, anything). Should assert `isinstance(resolved, str)` and raise `StoreError` if not. Low risk today (the index is written by trusted code) but a 2-line fix.

3. **Add a positive-UTC-offset TZ test for `resolve_day`.** The Fix 2 TZ tests only cover `America/Denver` (UTC-6). A test with `Asia/Tokyo` (UTC+9) at UTC 2026-04-26T14:00Z (which is April 27 local) would prove the fix is not just "Denver-shaped".

4. **Lock `events.json` version field on read.** Add a `StoreError` if `version` is not `1` — easy to do now, avoids silent forward-compatibility issues when version 2 is added later.

5. **Refactor `_make_protocol_pair` in tests** to a fixture. It's the longest construct in the test file. A `conftest.py` was noted in the original review; still worth doing before step 4 adds more tests.

6. **Resolve the `event_next` / `event_today` caller contract.** The corrective created a dependency: to see all events on and after today, a caller must call both. This should be documented in the turn contract (step 7 prompt work) and ideally in a docstring on `event_next` today.

---

*End of corrective review. Six items in section 6. Item 2 (validate return type) is a 2-line fix that could close before step 4. Others are deferred.*
