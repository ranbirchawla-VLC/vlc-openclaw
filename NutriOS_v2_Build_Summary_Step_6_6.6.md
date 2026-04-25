# NutriOS v2 — Build Summary: Step 6 + 6.6 (Tool Layer)

**Branch:** `feature/nutrios-v2`
**Result:** Step 6+6.6 complete after a corrective pass on independent-review findings. Ten Python tool entrypoints + foundation. 443 tests passing. Path canonicalized. Step 6.5 (migration) gate: next.

---

## Files added / changed

### Foundation

| Path | Lines | Purpose |
|---|---|---|
| `skills/nutrios/lib/nutrios_models.py` | 338 (+42) | + ToolResult, RecipeMacros, Recipe (with `removed`+`macros_per_serving`), Event.removed, State.last_recipe_id |
| `skills/nutrios/lib/nutrios_render.py` | 702 (+251) | + 18 tool-layer render templates, _GATE_ERROR_TEMPLATES extended for new error codes |
| `skills/nutrios/lib/nutrios_engine.py` | 384 (+37) | + expand_recipe; event_next/event_today/advisory_flags filter `removed=True` |
| `skills/nutrios/lib/nutrios_store.py` | 406 (+86) | + read_recipes/write_recipes, read_aliases, read_json_raw/write_json_raw, last_recipe_id counter |
| `skills/nutrios/lib/nutrios_time.py` | 87 (no change) | (existing) |

### Tools (all new)

| Tool | Lines | Tests | Test file |
|---|---|---|---|
| `nutrios_read.py` | 286 | 27 | `test_nutrios_read.py` (358) |
| `nutrios_write.py` | 159 | 16 | `test_nutrios_write.py` (271) |
| `nutrios_log.py` | 162 | 16 | `test_nutrios_log.py` (251) |
| `nutrios_weigh_in.py` | 101 | 14 | `test_nutrios_weigh_in.py` (158) |
| `nutrios_dose.py` | 111 | 10 | `test_nutrios_dose.py` (156) |
| `nutrios_med_note.py` | 84 | 15 | `test_nutrios_med_note.py` (142) |
| `nutrios_event.py` | 123 | 15 | `test_nutrios_event.py` (192) |
| `nutrios_recipe.py` | 190 | 25 | `test_nutrios_recipe.py` (271) |
| `nutrios_protocol_edit.py` | 74 | 9 | `test_nutrios_protocol_edit.py` (129) |
| `nutrios_setup_resume.py` | 369 | 22 | `test_nutrios_setup_resume.py` (357) |
| **Tool subtotal** | **1659** | **169** | |

### Test infrastructure (new)

| Path | Lines | Purpose |
|---|---|---|
| `skills/nutrios/tests/conftest.py` | 122 | `tmp_data_root` and `setup_user` fixtures, single sys.path setup |
| `skills/nutrios/tests/test_conftest_fixtures.py` | 94 | Three tests — fixture-under-test verification |

---

## Tests by suite

| Suite | Step 5 baseline | Post corrective | Delta |
|---|---|---|---|
| test_nutrios_time | 22 | 26 | +4 (to_local direct tests) |
| test_nutrios_models | 21 | 39 | +18 |
| test_nutrios_store | 28 | 32 | +4 (1 last_recipe_id + 3 read_jsonl_all) |
| test_nutrios_engine | 67 | 87 | +20 (11 expand_recipe + 3 event-removed + 6 is_dose_day) |
| test_nutrios_render | 45 | 79 | +34 (32 tool-layer + 2 invalid-weight) |
| test_conftest_fixtures | — | 3 | +3 |
| test_nutrios_read | — | 27 | +27 |
| test_nutrios_write | — | 20 | +20 (16 base + 4 _pending_kcal preservation) |
| test_nutrios_log | — | 16 | +16 |
| test_nutrios_weigh_in | — | 14 | +14 |
| test_nutrios_dose | — | 10 | +10 |
| test_nutrios_med_note | — | 15 | +15 |
| test_nutrios_event | — | 15 | +15 |
| test_nutrios_recipe | — | 29 | +29 (25 base + 4 soft-delete leak) |
| test_nutrios_protocol_edit | — | 9 | +9 |
| test_nutrios_setup_resume | — | 22 | +22 |
| **Total** | **183** | **443** | **+260** |

Suite runtime: 0.50s.

---

## Key contracts locked

- **Tool output:** every tool returns `ToolResult(display_text, needs_followup, state_delta, marker_cleared, next_marker)` via `model_dump_json()` on stdout. Exit 0 on happy path AND on rendered business-logic rejections; non-zero only on true crashes.
- **Recipe expansion:** `engine.expand_recipe(recipe, qty)` — qty in servings (fractional allowed); kcal as `int(round(per_serving.kcal * qty))`; macros as float; qty must be > 0.
- **Soft-delete (D3):** `Event.removed`, `Recipe.removed` boolean fields. Engine's `event_next`/`event_today`/`advisory_flags` filter on `removed=True`. Recipe lookup in `nutrios_log` skips removed.
- **`_pending_kcal` discipline (D4 + setup_resume):** scratch field on `goals.json.day_patterns[*]`. Read raw, strip, validate against canonical Goals model. Carbs_shape write preserves it via `store.write_json_raw`. Deficits step consumes the values and clears them via Pydantic round-trip.
- **Setup-resume:** marker walker through engine's fixed order, one at a time, through the standard turn contract. `gallbladder` calls into `nutrios_protocol_edit.apply_protocol_edit`; `tdee`/`nominal_deficit` direct mesocycle write; `carbs_shape`/`deficits` raw goals.json write.
- **Tripwires:** all four pass with zero false hits (one docstring match in nutrios_read counted and acknowledged).

---

## Judgment calls deferred / carry-forwards for follow-up

### Architectural (from §6 of the review)

- **Phase-2 read/write pattern:** `_pending_kcal` discipline is open-coded across five call sites in `nutrios_setup_resume` and now also in `nutrios_write._write_goals` (per the corrective pass). Worth extracting a `_phase2.py` helper before step 6.5 lands its migration writes — the pattern is now scattered across two tools.
- **Tool input base class:** every tool input shares `user_id`, most share `now`+`tz`, all use `extra="forbid"`. Worth consolidating before tool 11.
- **`nutrios_write` ↔ `nutrios_protocol_edit` overlap:** parallel gate-and-write logic for the protocol scope. Refactor `_write_protocol` to call `apply_protocol_edit` for one source of truth.
- **Discriminated-union input models for action-dispatched tools:** `nutrios_recipe`, `nutrios_event`, `nutrios_med_note`, `nutrios_write` currently use a single input model with optional fields per action and 11 `raise ValueError` checks for per-action shape. Per-action input models stitched via Pydantic discriminator would close the Tripwire 4 gap structurally — see review §6.5 for the example.
- **D2 trust model:** manual food path trusts LLM-provided macros entirely. A small `foods.json` table for the most-frequent foods is the natural extension.

### Spec-level

- **Deficits per-day overrides:** brief's render template mentions "rest 500" syntax for per-day-type adjustments; this pass supports only `"yes"` (apply all suggestions). Per-day parsing is a future enhancement; the prompt template doesn't need changes when it lands.
- **`event_today` / `event_next` caller pairing rule:** `event_next` uses strict `>` (today excluded). A caller wanting events from today forward must call both. Document in step 7 orchestrator prompt.
- **`render_setup_resume_prompt` context dict shape:** untyped dict. Each marker has implicit shape requirements. A typed model (or per-marker dict subtypes) would catch caller errors at construction time. Deferred to step 7 when the orchestrator-side prompt assembly lands.
- **Aliases.json write helper:** read-only helper added (`store.read_aliases`); writes deferred to step 7 (alias edits aren't part of the tool layer's intent set).

### Operational

- **PYTHONPATH discipline for `python3.12 -m nutrios_<tool>`:** every tool file does `sys.path.insert(0, ...)` matching the test pattern. Ranbir approved as MVP; step 8 (scaffold/openclaw.json) replaces with packaged invocation.
- **Step 4 (mnemo) deferred** by explicit decision; tools talk to store directly. Wiring is post-cutover.

---

## Tripwire verification (concrete)

```
$ grep -rn 'open(.*\.jsonl' skills/nutrios/tools/
(no output)

$ grep -rn 'datetime\.now\|date\.today' skills/nutrios/tools/
skills/nutrios/tools/nutrios_read.py:13:    3. now and tz are inputs; never datetime.now() / date.today() in tool layer.
(one hit, in a docstring documenting the tripwire)

$ grep -rn 'from nutrios_engine\|import nutrios_engine' skills/nutrios/lib/nutrios_render.py
(no output)

$ grep -rn 'f".*error\|f".*failed' skills/nutrios/tools/
(no output)
```

All four tripwires hold on the literal grep. Tripwire 4 has a documented partial gap: 11 `raise ValueError(...)` sites with f-string messages handle action-dispatch shape errors and bypass the render layer. The structural fix (discriminated-union input models) is in the carry-forward list.

---

## Branch state

```
$ git log --oneline feature/nutrios-v2 ^main
f1c9950 test(time): direct tests for nutrios_time.to_local — carry-forward from step 5
34b9da0 feat(tool): nutrios_setup_resume — guided marker walker (10/10)
a83e2e0 feat(tool): nutrios_protocol_edit — gated protocol writes (9/10)
213d150 feat(tool): nutrios_recipe — full lifecycle (8/10)
4583362 feat(tool): nutrios_event — add/list/remove with soft-delete (7/10)
073427b feat(tool): nutrios_med_note — add or view protocol-with-notes (6/10)
8bea0ff feat(tool): nutrios_dose — dose-day-aware log entrypoint (5/10)
ae4459c feat(tool): nutrios_weigh_in — append-only weigh-in entrypoint (4/10)
f489e2f feat(tool): nutrios_log — locked recipe contract (3/10)
25f5a33 feat(tool): nutrios_write — gate-before-write entrypoint (2/10)
fcedf18 feat(tool): nutrios_read — scope-routed read entrypoint (1/10)
00df07d feat(engine): expand_recipe + Event soft-delete filter + last_recipe_id counter
03da51d feat(render): tool-layer renderers — 18 new templates, 32 new tests
e94332f feat(models): ToolResult + Recipe/RecipeMacros + soft-delete + recipe counter
e29fa0d test: shared conftest fixtures + fixture-under-test verification
2334ab5 refactor: canonicalize skills/nutriOS → skills/nutrios
e330fd5 docs: add v2 build briefs as authoritative spec
0907390 feat(render): step 5 corrective — all 3 issues resolved, 183 passing
```

17 commits on the branch since step 5 baseline. Ready for review.

---

## Stop condition

Step 6+6.6 is complete. **Stopping here.** Step 6.5 (migration) is the next pass after Ranbir's gate review of this work.
