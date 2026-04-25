# NutriOS v2 — Build Progress

Branch: `feature/nutrios-v2`  
Last clean commit: `f1c9950` — `test(time): direct tests for nutrios_time.to_local`  
Suite: **426 passed, 0 failed**

---

## Files and line counts

| Module | Lines | Tests | Test count |
|---|---|---|---|
| `lib/nutrios_time.py` | 87 | `test_nutrios_time.py` | 26 |
| `lib/nutrios_models.py` | 338 | `test_nutrios_models.py` | 39 |
| `lib/nutrios_store.py` | 406 | `test_nutrios_store.py` | 29 |
| `lib/nutrios_engine.py` | 384 | `test_nutrios_engine.py` | 81 |
| `lib/nutrios_render.py` | 702 | `test_nutrios_render.py` | 79 |
| `tools/nutrios_read.py` | 286 | `test_nutrios_read.py` | 27 |
| `tools/nutrios_write.py` | 159 | `test_nutrios_write.py` | 16 |
| `tools/nutrios_log.py` | 162 | `test_nutrios_log.py` | 16 |
| `tools/nutrios_weigh_in.py` | 101 | `test_nutrios_weigh_in.py` | 14 |
| `tools/nutrios_dose.py` | 111 | `test_nutrios_dose.py` | 10 |
| `tools/nutrios_med_note.py` | 84 | `test_nutrios_med_note.py` | 15 |
| `tools/nutrios_event.py` | 123 | `test_nutrios_event.py` | 15 |
| `tools/nutrios_recipe.py` | 190 | `test_nutrios_recipe.py` | 25 |
| `tools/nutrios_protocol_edit.py` | 74 | `test_nutrios_protocol_edit.py` | 9 |
| `tools/nutrios_setup_resume.py` | 369 | `test_nutrios_setup_resume.py` | 22 |
| `tests/conftest.py` | 122 | `test_conftest_fixtures.py` | 3 |
| **Total production** | **3576** | **Total tests** | **426** |

---

## Steps built vs. remaining

| Step | Module | Status |
|---|---|---|
| 1 | `nutrios_time.py` | ✓ complete + corrective + to_local test |
| 2a | `nutrios_models.py` | ✓ complete (extended in 6+6.6) |
| 2b | `nutrios_store.py` | ✓ complete + corrective (extended in 6+6.6) |
| 3 | `nutrios_engine.py` | ✓ complete + corrective + expand_recipe + soft-delete filter |
| 4 | `nutrios_mnemo.py` | **deferred** (Mnemo integration — explicit decision) |
| 5 | `nutrios_render.py` | ✓ complete + corrective + 18 tool-layer templates |
| 6 | Tool shims (10 files) | ✓ complete (read, write, log, weigh-in, dose, med-note, event, recipe, protocol-edit, setup-resume) |
| 6.5 | `nutrios_migrate.py` | **next pass** |
| 6.6 | Tool entrypoints | ✓ complete (folded into step 6) |
| 7 | `prompts/` | **not started** |
| 8 | `scaffold.sh` update | **not started** |
| 9 | `INSTALL.md` update | **not started** |

---

## Red tests

None. All 426 pass. Suite runtime: 0.46s.

---

## Tripwires (concrete)

All four pass:

- **T2** `grep -rn 'open(.*\.jsonl' skills/nutrios/tools/` → no output
- **T3a** `grep -rn 'datetime\.now\|date\.today' skills/nutrios/tools/` → 1 docstring hit (acknowledged)
- **T3b** `grep -rn 'from nutrios_engine\|import nutrios_engine' skills/nutrios/lib/nutrios_render.py` → no output
- **T4** `grep -rn 'f".*error\|f".*failed' skills/nutrios/tools/` → no output

---

## Path canonicalization

`skills/nutriOS/` → `skills/nutrios/` complete. `git ls-files skills/nutriOS/` returns nothing. Both `make test-nutrios` and bare `pytest` resolve from the canonical path. Two-step git mv via uniquely-named intermediates avoided the case-insensitive-filesystem rejection.

---

## Open / carry-forward items

### Architectural (from review §6)

- **Phase-2 read/write helper extraction.** `_pending_kcal` discipline open-coded across 5 sites in nutrios_setup_resume.
- **Tool input base class.** Common `user_id`/`now`/`tz`/`extra="forbid"` pattern across all 10 tools.
- **`nutrios_write` ↔ `nutrios_protocol_edit` overlap.** Refactor `_write_protocol` to call `apply_protocol_edit` for one source of truth.
- **D2 trust model on manual food path.** Future `foods.json` table for frequent foods.

### Spec / contract follow-ups

- **Deficits per-day overrides** ("rest 500" syntax) — currently MVP supports `"yes"` only.
- **`event_today` / `event_next` caller pairing rule** — document in step 7 orchestrator prompt.
- **`render_setup_resume_prompt` context dict shape** — currently untyped; per-marker dict subtypes worth introducing.
- **Aliases.json write helper** — read-only added; writes deferred to step 7.

### Operational

- **PYTHONPATH discipline** — sys.path.insert per tool file (Ranbir-approved MVP); step 8 replaces with packaged invocation.
- **Step 4 (mnemo) deferred** by explicit decision.

---

## Format / contract choices made (carried forward from step 5)

| Element | Choice | Notes |
|---|---|---|
| Range separator in macro line | `–` (en-dash, U+2013) | matches spec |
| Negative delta sign | `−` (U+2212, MINUS SIGN) | used in `render_kcal_line`, `render_weight_trend`, `render_weigh_in_confirm` |
| Date format in events / log entries | `YYYY-MM-DD` | ISO via `str(date_obj)` |
| Date format in daily summary header | `"Fri Apr 24"` (`%a %b %d`, leading zero stripped) | |
| Macro line total width | 32 chars | derived from spec examples |
| Gram value formatting | `:g` format (drops trailing zeros) | `_fmt_g` helper, used by `render_log_confirm` and recipe summaries |
| Tool exit code | 0 for happy + business-rule rejections; non-zero only for true crashes | per Ranbir's decision 5 |
| Tool stdout | exactly one JSON line — `result.model_dump_json()` | verified by `test_read_main_returns_tool_result_instance` |
