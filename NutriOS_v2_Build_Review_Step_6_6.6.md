# NutriOS v2 — Build Review: Step 6 + 6.6 (Tool Layer)

**Branch:** `feature/nutrios-v2`
**Scope:** Path canonicalization + foundation (conftest, models, render, engine) + ten Python tool entrypoints under `skills/nutrios/tools/`.
**Reviewer:** Claude (self-review, post-build)
**Result:** PASS — no stop conditions triggered, no tripwires breached, refinement opportunities documented.

---

## 0. Summary

Ten new tool entrypoints, full TDD per tool, gate-clean across all four tripwires from the brief. Path folded `skills/nutriOS/` → `skills/nutrios/` as the first commit on the branch; everything below the foundation layers builds on the canonical path.

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
| (tests) `conftest.py` | 122 | `test_conftest_fixtures.py` | 3 |
| **Total production** | **3576** | **Total tests** | **426** |

Suite: **426 passed, 0 failed, 0 skipped, 0.46s.**

---

## 1. Stop Conditions (review.md §1)

| # | Condition | Finding |
|---|---|---|
| 1 | Secrets in code or committed config | None. No credentials, keys, or tokens. NUTRIOS_DATA_ROOT is a path env var read in `data_root()`; tests monkeypatch via tmp_path. |
| 2 | `except Exception:` without re-raise / bare `except:` | None. Exception handlers are scoped (`json.JSONDecodeError` in `read_events`/`read_aliases`, `OSError` only on the cleanup path of atomic-write helpers, all re-raise via `raise StoreError(...) from exc` or pass through). |
| 3 | External call without timeout | None. Tools are local-disk only; no HTTP, LLM, DB, or subprocess. |
| 4 | New behavior without a test | None. TDD per tool; 243 new tests added against the 183 step-5 baseline. |
| 5 | New LLM call / external integration without log event | N/A — no LLM calls in this pass. |
| 6 | `shell=True` with non-constant input | None. No subprocess. |
| 7 | LLM call with prompt inlined | N/A — no LLM calls. Module prompts (`module-*.md`) are step 7. |
| 8 | Dependency added without pinned version | None. Only `pydantic` (already pinned by the environment). |
| 9 | PII to LLM API without policy | N/A. |
| 10 | Schema/state migration without rollback | Migration is step 6.5 (next pass). This pass adds State.last_recipe_id with backward-compat default 0; legacy state.json files load cleanly (test: `test_state_backward_compat_missing_last_recipe_id`). |

**No stop conditions triggered.**

---

## 2. Tripwire Greps — Concrete Output

### Tripwire 2: Append-only JSONL (`grep -rn 'open(.*\.jsonl' skills/nutrios/tools/`)

```
(no output)
```

**Zero hits.** Every JSONL read in the tool layer goes through `store.tail_jsonl`. Every JSONL write goes through `store.append_jsonl`. Edits use `supersedes` semantics (FoodLogEntry, WeighIn, MedNote) — a new line is appended that references the prior id; no existing line is ever rewritten. Verified by inspection across all ten tools.

### Tripwire 3a: No clock calls in tools (`grep -rn 'datetime\.now\|date\.today' skills/nutrios/tools/`)

```
skills/nutrios/tools/nutrios_read.py:13:    3. now and tz are inputs; never datetime.now() / date.today() in tool layer.
```

**One hit, in a docstring** describing the tripwire. No actual call sites. Every tool takes `now: datetime` and `tz: str` as required input fields; downstream engine and render functions also take them as parameters. The single docstring match is intentional — it documents the discipline.

### Tripwire 3b: No engine import in render (`grep -rn 'from nutrios_engine\|import nutrios_engine' skills/nutrios/lib/nutrios_render.py`)

```
(no output)
```

**Zero hits.** Step 5 corrective held; no regression introduced by the new render functions added in this pass. `render_daily_summary` and the seventeen new tool-layer renderers consume engine results passed as parameters; render does not call engine.

### Tripwire 4: No error f-strings in tools (`grep -rn 'f".*error\|f".*failed' skills/nutrios/tools/`)

```
(no output)
```

**Zero hits.** Every user-facing error string in the tool layer is produced by a `nutrios_render` template:

- `render_gate_error` (existing) — protected gate rejections
- `render_dose_not_due` (existing) — non-dose-day dose attempt
- `render_dose_already_logged` (NEW) — duplicate dose
- `render_supersedes_not_found` (NEW) — missing edit target (weigh-in, event, recipe)
- `render_invalid_weight` (NEW) — weight bounds violation
- `render_protocol_not_initialized` (NEW) — missing protocol/goals
- `render_recipe_duplicate_name_error` (NEW) — recipe name collision
- `render_quantity_clarify`, `render_macros_required` (NEW) — followup paths

ValueError is raised in tools only for true crash paths (missing required field on action-dispatched input), per the contract: "Internal exceptions (validation failures, file errors) propagate up; the OpenClaw runtime handles those."

---

## 3. Tool Contract Conformance Table

One row per tool. ✓ = yes, "—" = N/A.

| Tool | Input model | Engine calls | Render calls | Output is `ToolResult` | Errors via render |
|---|---|---|---|---|---|
| nutrios_read | ReadInput | resolve_day, macro_range_check, dose_reminder_due, dose_status, weight_change, weight_trend, event_next, advisory_flags | render_daily_summary, render_weight_trend, render_med_notes_list, render_event_list, render_protocol_view, render_goals_view, render_mesocycle_view, render_recipe_list, render_protocol_not_initialized | ✓ | ✓ |
| nutrios_write | WriteInput | protected_gate_range, protected_gate_protocol | render_write_confirm, render_gate_error | ✓ | ✓ |
| nutrios_log | LogInput | expand_recipe | render_quantity_clarify, render_macros_required, render_log_confirm | ✓ | ✓ |
| nutrios_weigh_in | WeighInInput | weight_change | render_invalid_weight, render_supersedes_not_found, render_weigh_in_confirm | ✓ | ✓ |
| nutrios_dose | DoseInput | — (uses local weekday match directly; same logic as dose_reminder_due) | render_protocol_not_initialized, render_dose_not_due, render_dose_already_logged, render_dose_confirm | ✓ | ✓ |
| nutrios_med_note | MedNoteInput | — | render_med_note_confirm, render_protocol_view, render_protocol_not_initialized | ✓ | ✓ |
| nutrios_event | EventInput | event_next | render_event_added, render_event_list, render_event_removed_confirm, render_supersedes_not_found | ✓ | ✓ |
| nutrios_recipe | RecipeInput | — | render_recipe_save_confirm, render_recipe_update_confirm, render_recipe_delete_confirm, render_recipe_list, render_recipe_view, render_recipe_duplicate_name_error, render_supersedes_not_found | ✓ | ✓ |
| nutrios_protocol_edit | ProtocolEditInput | protected_gate_protocol | render_write_confirm, render_gate_error | ✓ | ✓ |
| nutrios_setup_resume | SetupResumeInput | setup_status | render_setup_complete, render_setup_resume_prompt, render_protocol_not_initialized + (delegated) every renderer reachable through nutrios_protocol_edit.apply_protocol_edit | ✓ | ✓ |

Every tool's `main(argv_json: str) -> ToolResult` returns a `ToolResult` instance with a non-empty `display_text` produced by render. Stdout contract: `__main__` prints exactly `result.model_dump_json()` — verified by `test_read_main_returns_tool_result_instance`.

---

## 4. Setup-Resume Marker Routing Audit

Per-marker dispatch. Each row: validation logic, write target, `clear_needs_setup_marker` call site, and the test that exercises a full marker-clear cycle.

| Marker | Validation | Write path | clear_needs_setup_marker call | Cycle test |
|---|---|---|---|---|
| gallbladder | answer ∈ `{"removed", "present", "unknown"}` | `nutrios_protocol_edit.apply_protocol_edit` (gate is no-op for clinical fields) | `_process_gallbladder` after `apply_protocol_edit` returns `"Protocol updated."` | `test_setup_resume_gallbladder_removed_clears_marker` |
| tdee | answer parses as int in `[1000, 5000]` | direct `store.write_json` to `mesocycles/<active_cycle_id>.json` with `tdee_kcal` updated | `_process_tdee` post-write | `test_setup_resume_tdee_valid_writes_mesocycle` |
| carbs_shape | answer ∈ `{"yes", "max", "both"}` | `store.write_json_raw("goals.json", raw)` — preserves `_pending_kcal` | `_process_carbs_shape` post-write | `test_setup_resume_carbs_shape_yes_keeps_min`, `_max_flips_min_to_max`, `_both_sets_both_ends` |
| deficits | answer == `"yes"` (MVP — per-day overrides like "rest 500" are reprompted; documented carry-forward) | `store.write_json("goals.json", proposed_goals)` — Pydantic round-trip strips `_pending_kcal` (intentional, deficits is the consume-and-clear step) | `_process_deficits` post-write | `test_setup_resume_deficits_yes_applies_suggested_and_clears_pending` |
| nominal_deficit | answer == `"yes"` (uses computed most-common from confirmed day_pattern deficits) OR int in `[0, 2000]` | direct `store.write_json` to `mesocycles/<active_cycle_id>.json` with `deficit_kcal` updated | `_process_nominal_deficit` post-write | `test_setup_resume_nominal_deficit_yes_uses_most_common`, `_explicit_number` |

**Full-walk test:** `test_setup_resume_full_walk_reaches_completion` exercises all five markers in order against a setup-pending fixture user with `_pending_kcal` seeded. Final call returns `render_setup_complete` text; all markers cleared on disk.

**Dependency order:** `test_setup_resume_empty_answer_respects_dependency_order` confirms the engine's gate logic (deficits not surfaced while tdee is pending) is honored — `_post_write_response` recomputes `setup_status` after every clear and trusts the engine's ordering.

**Shared-helper extraction:** `nutrios_protocol_edit.apply_protocol_edit` is the only extracted helper required for setup_resume routing. tdee, carbs_shape, deficits, and nominal_deficit are direct writes that don't go through the gate (their fields aren't protected) and inline the small write logic. Documented choice: extracting helpers for non-gated paths added boilerplate without clarity gain.

---

## 5. Path Canonicalization Verification

| Check | Result |
|---|---|
| `git ls-files skills/nutriOS/` returns nothing | Empty — confirmed |
| `skills/nutrios/lib/`, `tests/`, `tools/` all populated under git | Confirmed: 6 lib files + 16 test files + 10 tool files tracked |
| Makefile targets resolve | `make test-nutrios` runs 426 tests |
| Bare pytest discovers full suite | `python3.12 -m pytest` runs 426 tests via `pytest.ini` testpaths |
| macOS APFS case-insensitivity preserved | Both `nutrios` and `nutriOS` continue to address the same physical directory; only the git index changed. The legacy v1 files (AGENTS.md, SKILL.md, openclaw.json, JS tools) were already at lowercase paths and did not move. |

The two-step `git mv` via uniquely-named intermediates (`skills/_nutrios_lib_rename_tmp`, `skills/_nutrios_tests_rename_tmp`) sidestepped the case-only-rename rejection that `core.ignorecase=true` would otherwise produce. All 12 affected files registered as renames (R flag) in `git status`.

---

## 6. What I Would Change With Another Pass

Per the brief: structural items, not cosmetic. Three minimum.

### 6.1 Extract a `_PhaseTwo` namespace for the raw-goals.json read/write path

The `_pending_kcal` discipline is currently surfaced through five distinct call sites in `nutrios_setup_resume.py`: `_build_context` for carbs_shape and nominal_deficit (via `_read_goals_phase2`), `_process_tdee` (also via `_read_goals_phase2`), `_process_carbs_shape` (raw read + raw write), and `_process_deficits` (raw read + Pydantic write to consume the scratch). The pattern is consistent but the mechanism is scattered. A small `_phase2.py` module exposing `read_goals_with_pending(uid) -> tuple[Goals, dict[str, int]]` and `write_goals_preserving_pending(uid, goals, pending) -> None` would make the migration-scratch contract explicit and testable in isolation. Right now the contract is "read raw, strip, validate; write raw if scratch must survive; write validated if scratch should be cleared" — that's three separate concepts in two helper functions and four open-coded callers.

**Why it matters:** Step 6.5 (migration) writes `_pending_kcal` to disk. Step 7 (orchestrator) needs to know nothing about it. The seam is here, in setup_resume. A typed, testable seam will be more maintainable than the current open-coded pattern. Particularly relevant before the migration tests land in 6.5 — the read/write path is the integration point.

### 6.2 Tool input models share enough structure to deserve a base class

Every tool input has `user_id: str`, almost every one has `now: datetime` + `tz: str`, every one has `model_config = ConfigDict(extra="forbid")`. The repetition is harmless today, but as the orchestrator (step 7) starts dispatching based on intent → tool, a shared `ToolInputBase` would let intent classifiers validate the common fields once and let each tool's specific input subclass focus on its own additions. It would also centralize the `extra="forbid"` discipline so a future contributor can't accidentally let an extra field slip through.

**Why it matters:** Tool surface is now ten — enough to start consolidating. The first place a contributor will add a new tool is the eleventh, where the pattern repeats. A base class catches drift before it accumulates.

### 6.3 `nutrios_write` and `nutrios_protocol_edit` overlap on the protocol scope

The brief specifies both as first-class entry points, and I implemented both with parallel gate-and-write logic. `nutrios_protocol_edit` was refactored to expose `apply_protocol_edit` so `nutrios_setup_resume` can call into it without JSON argv parsing; `nutrios_write._write_protocol` was NOT similarly refactored. The duplication is small (~10 lines), but it is two source-of-truth surfaces for the same gate-and-write contract. Future protocol-gate behavior changes (e.g., adding a new protected field, changing the confirm-phrase rule) require updates in two places.

The clean refactor: `_write_protocol` calls `nutrios_protocol_edit.apply_protocol_edit`. One source of truth; `nutrios_write` becomes a dispatcher to scope-specific helpers.

**Why it matters:** Drift between the two paths is the kind of bug that's invisible until the day a protected field is added and only one path is updated. Pulling them into a single helper now is cheap; pulling them apart later when they have diverged behaviors is not.

### 6.4 (Bonus) The static foods table decision (D2) is going to need revisiting

The current contract — manual food path requires the LLM to provide `kcal/protein_g/carbs_g/fat_g` on input — works as long as the LLM is reliable. In practice, food macro lookups are exactly the kind of thing the LLM will hallucinate (e.g., "150g chicken breast = 250 kcal" is roughly right; "150g salmon = 230 kcal" might come out as 320 kcal). A small in-tree `foods.json` for the user's most-frequent foods would tighten this with very little surface area, and would also let `nutrios_log` produce a "did you mean?" clarification rather than just trusting whatever macros the LLM passes through.

**Why it matters:** Not for this pass — D2 is a deferred decision. Worth flagging that the trust model on the manual path is "trust LLM macros entirely," and that's the path that gets exercised every time the user logs an unfamiliar food.

---

## 7. Resilience: Failure Mode Enumeration (review.md §5)

Tools are local-disk only; the only external dependency is the filesystem. Per review.md §5:

| Question | Answer |
|---|---|
| Slow filesystem (P99 10x normal) | Tools complete; no hard timeout. Daily logs are bounded (~20 lines/day); `tail_jsonl` reads the whole file but the file is small. Acceptable. |
| Filesystem error | Atomic-write helpers (`_atomic_write_text`, `append_jsonl`) clean up the temp file and re-raise. Disk is left in its prior state. Verified: `test_append_jsonl_atomic_on_interrupt`. |
| Filesystem timeout | N/A — synchronous local I/O. |
| Degraded data | Pydantic strict validation rejects malformed payloads at read; `read_events` and `read_recipes` raise `StoreError` on missing wrapper format. |
| Rate limit | N/A. |
| Cost budget | N/A. |

**Idempotency:** Every state-mutating operation has explicit semantics:
- JSONL writes are append-only; re-running an `add` produces a new line with a new id (not idempotent on retry — caller must dedupe via supersedes if needed).
- Event remove and recipe delete are idempotent (re-removing returns the same confirm).
- Setup-resume marker clears are idempotent (re-running with the same answer after the marker is already cleared falls through to `setup complete` — no double-write).
- Protocol/goals/mesocycle/recipes writes are full-state replacements; idempotent on identical input.

**Kill switch:** `NUTRIOS_DATA_ROOT` env var can be unset to halt all tool operations (raises `EnvironmentError` from `data_root()`). No deploy needed.

---

## 8. Agent Architecture (review.md §4)

| Item | Status |
|---|---|
| Single responsibility per skill | ✓ — each tool maps 1:1 to an intent (read, write, log, weigh-in, dose, med-note, event, recipe, protocol-edit, setup-resume). |
| Triggering conditions specific | ✓ — every tool has a typed input model with `extra="forbid"`. The orchestrator (step 7) will route by intent → tool name. |
| Idempotent where possible | ✓ — see §7. |
| Resumable for multi-step flows | ✓ — `nutrios_setup_resume` is the only multi-step flow. Resumable across turns; marker state persists in `_needs_setup.json` between calls. |
| Iteration cap on agent loops | N/A — no agent loops in this pass. The orchestrator (step 7) carries this. |
| Inter-agent contracts documented | ✓ — `ToolResult` is the contract. `state_delta` is the side-channel for the orchestrator. `marker_cleared` and `next_marker` are setup-resume-specific. |
| Loop detection | N/A — no agent-calling-agent in this pass. |
| Memory layer | Step 4 (`nutrios_mnemo.py`) is deferred. Tools talk to `store` directly. |

---

## 9. Tests (review.md §6)

| Item | Status |
|---|---|
| Unit tests are fast and deterministic | ✓ — 426 tests in 0.46s; no LLM mocking required (no LLM calls). |
| Eval suite separate | N/A — no LLM calls. |
| Property assertions for LLM output | N/A — render outputs are deterministic Python; exact-string assertions are appropriate for byte-stable contracts. |
| Unhappy paths covered | ✓ — every tool has at least one rejection-rendered test (gate, validation, missing data) and one missing-input branch. |
| Tests verify behavior, not implementation | Mostly ✓. Render tests use exact-string assertions which bind to formatting strings; this is intentional (cache stability requires byte-stable output) but couples tests to the format. Documented as a known property. |
| Build under ten minutes | ✓ — 0.46s. |

---

## 10. Verdict

**PASS.** All four tripwires clear, every stop condition green, every tool's contract conformance verified, the full setup-resume marker walk lands at completion, the path canonicalization holds, three structural refinements documented for follow-up. Step 6.5 (migration) gate: pending Ranbir review.
