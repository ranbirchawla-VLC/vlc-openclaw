# NutriOS v2 — Build Summary Step 6.5 (Migration Phase 1)

Branch: `feature/nutrios-v2`
Build commit: `fb27c6e` — `build: step 6.5 — nutrios_migrate.py Phase 1 structural migrator`
Corrective commit: `b56e000` — `fix: corrective pass on step 6.5 code-reviewer findings`
Suite: **524 passed, 0 failed** (was 443 pre-step). Suite runtime: ~0.9s.
Code-reviewer subagent: **PASS WITH FIXES** → all HIGH and MED #3/#5 addressed in commit `b56e000`; MED #4 + LOW #6/#7/#9 + NIT #11 also addressed.

---

## Files

| Module | Lines | Tests | Test count |
|---|---|---|---|
| `lib/nutrios_migrate.py` | 1342 | `test_nutrios_migrate.py` | 76 |
| `lib/nutrios_store.py` (delta) | +37 | `test_nutrios_store.py` (delta) | +5 |
| `tests/fixtures/v1/rule_1_full/` (12 files) | — | (drives most tests) | — |
| `tests/fixtures/v1/rule_2_minimal/` (4 files) | — | drives Rule 2 path | — |
| `tests/fixtures/v1/missing_protocol/` (1 file) | — | drives exit-1 path | — |
| `tests/fixtures/golden/rule_1_full_report.md` | 58 | golden compare | — |

Production line delta this step: +1342 (migrator) + 37 (store helper) = **1379 lines**.

---

## What was built

`nutrios_migrate.py` runs Phase 1 v1→v2 structural migration. Headless, deterministic, fixture-tested. Implements every row of `NutriOS_v2_Build_Brief_v2_Extension_v3.md` Part 6.1.

### Module surface

- `migrate(*, source, dest, user_id, force) -> MigrationResult` — public entrypoint. Returns a structured result; no exceptions escape.
- `main(argv=None) -> int` — CLI entrypoint. Returns exit code; `__main__` calls `sys.exit(main())`.
- 9 internal `_transform_*` / `_load_v1_tree` / `_write_v2_tree` helpers.
- 7 named `_tpl_*` report-section templates + 6 `_err_*`/`_warn_*` line templates (Tripwire 4 — every report line and every error message comes from a template).
- 9 v1-shape Pydantic models (migration-only, never join `nutrios_models.py`).

### Companion store helper

`nutrios_store.write_jsonl_batch(user_id, filename, models)` — atomic batch write for migration efficiency. Same `tempfile.mkstemp + fsync + os.replace` primitive as `append_jsonl`. Append vs. batch is a per-file mode choice; mixing them on the same file in one run would clobber. Documented in the docstring.

### Fixture coverage

`rule_1_full/` exercises:
- Treatment field renames + optional fields
- Biometrics direct carry + `current_weight_lbs` discard
- 3 weigh-ins (date+12:00 local→UTC, monotonic ids)
- 2 med team notes (one with explicit source, one defaulting to `self`)
- 4 events: surgery, appointment, milestone, unknown type (`family` → `other` with `[original_type=family]` in notes)
- 3 daily logs: with food (`source: estimated`→`manual`), `dose_logged: true` synthesizing one DoseLogEntry, `water_count`, `day_notes`, `running_totals`, `remaining`, `targets`
- 2 valid + 1 quarantined recipe (missing `macros_per_serving`)
- Active mesocycle + 2 historical (always `tdee_kcal=null`, both flagged)
- 1 `.bak` file (discarded with count in report)
- Day patterns with per-day-type `is_deficit_day` flag → fat ceiling override 65→58

`rule_2_minimal/` covers `whoop_tdee_kcal: null` → `_pending_kcal` raw-dict scratch field per Tripwire 5.

`missing_protocol/` drives exit-code 1.

---

## Steps built vs. remaining

| Step | Module | Status |
|---|---|---|
| 6.5 | `nutrios_migrate.py` | ✓ complete + corrective + 12 follow-up tests |
| 7 | `prompts/` | not started |
| 8 | `scaffold.sh` update | not started |
| 9 | `INSTALL.md` update | not started |

---

## Tripwires (verified)

| Tripwire | Verification | Status |
|---|---|---|
| T2 — append-only JSONL | `grep -rn 'open(.*\.jsonl' skills/nutrios/lib/nutrios_migrate.py skills/nutrios/tools/` → no output | ✓ |
| T3 — TZ discipline | `grep -n 'datetime\.now(\|date\.today(' skills/nutrios/lib/nutrios_migrate.py` → no output | ✓ |
| T4 — templated errors | All report sections via `_tpl_*`; all error/warning lines via `_err_*`/`_warn_*`. No inline f-strings in writer paths. | ✓ |
| T5 — `_pending_kcal` scope | `grep -n '_pending_kcal' skills/nutrios/lib/nutrios_models.py` → no output. Field appears in `lib/nutrios_migrate.py` (3 hits — writer) and in carry-forward strip helpers in `tools/`. | ✓ |

---

## Exit-code contract (verified end-to-end via `python -m`)

| Code | Trigger | Stdout | Stderr |
|---|---|---|---|
| 0 | success | report path | (silent) |
| 1 | runtime failure (missing v1 file, malformed v1, write failure) | (silent) | error string |
| 2 | re-run refused (marker present, no `--force`) | (silent) | "User already migrated; use --force to rebuild" |
| 3 | invalid argument (path missing, source==dest, malformed user_id) | (silent) | error string |

`--force` triggers `_scoped_user_dir_for_rm` (triple-check: parent equality, leaf name equality, prefix containment) before any rmtree. Reviewer's symlink attack scenarios (4 variants) all correctly refused.

---

## Code review

### First pass (subagent)

PASS WITH FIXES. Findings:

| # | Severity | Issue | Fix landed |
|---|---|---|---|
| 1 | HIGH | `migrate()` mutated `os.environ['NUTRIOS_DATA_ROOT']` without restore | ✓ try/finally restore around `_migrate_with_env` body |
| 2 | HIGH | `_check_migration_marker` propagated `JSONDecodeError` past the no-exception contract | ✓ catch + sentinel `{"_corrupt": True}` triggers same exit-2 |
| 3 | MED | Quarantine writes non-atomic + slug collisions overwrote silently | ✓ `_atomic_write_local` helper + slug disambiguated by `_id<rid>` |
| 4 | MED | `_load_v1_tree` raised `TypeError` on null/non-list events or recipes | ✓ `isinstance(items, list)` guard, raises ValueError with templated message |
| 5 | MED | Partial-write failure left no marker → silent re-run on partial tree | ✓ `_rollback_partial_user_dir` after write failure; next run starts clean |
| 6 | LOW | `source == dest` silently accepted | ✓ `_err_source_equals_dest` guard, exit 3 |
| 7 | LOW | `whoop_tdee_kcal < 0` silently fell into Rule 2 | ✓ `_warn_whoop_negative` adds report warning; rule 2 still fires |
| 9 | LOW | No subprocess-style test for stderr-on-failure discipline | ✓ `test_main_failure_writes_to_stderr_not_stdout` |
| 11 | NIT | Dead `f` prefix in `_tpl_warnings_section` | ✓ removed |
| 8 | LOW | `last_recipe_id` silently coerces non-int v1 ids | not addressed (correctness preserved; documented as defensive coercion) |
| 10 | LOW | All migrated food entries share noon-local `ts_iso` | not addressed (out of scope; v1 didn't carry per-meal timestamps) |

12 new tests added for the corrective items (76 total in `test_nutrios_migrate.py`).

### Second pass

Not invoked — corrective fixes are scoped, additive, and accompanied by green tests for each. Will run on the next architectural gate (step 7 prompts).

---

## Format / contract choices made

| Element | Choice | Notes |
|---|---|---|
| Migrator location | `lib/` | matches Tripwire 5 grep target; mirrors `nutrios_engine` etc. |
| Invocation | `PYTHONPATH=skills/nutrios/lib python -m nutrios_migrate ...` | sys.path insert at top is the standard tools/ pattern |
| `_pending_kcal` write path | `store.write_json_raw` (raw-dict, bypasses Pydantic) | T5 demands no entry into the canonical model |
| JSONL batch primitive | `write_jsonl_batch` (new) sharing `append_jsonl`'s atomicity | T2 sustained for migration efficiency |
| Quarantine slug shape | `<sanitized_name>_id<rid>.json` + `.reason.txt` sidecar | id-disambiguated to prevent collision |
| Unknown event type policy | `event_type="other"`, original prepended to notes as `[original_type=foo]` | grep-recoverable |
| Nominal cycle deficit tie-break | most-common deficit; tie → deficit of most-common day_type in weekly_schedule | spec-prescribed |
| Marker precedence on Rule 1 vs Rule 2 | always set: gallbladder, deficits, nominal_deficit, carbs_shape; conditional: tdee (Rule 2 only) | per spec table |
| Synthesized dose `ts_iso` | log_date + protocol.dose_time local → UTC | spec |
| Synthesized dose `dose_mg`/`brand` | snapshot of CURRENT (migrated) protocol at migration time | spec; flagged in report |
| Historical mesocycles | `tdee_kcal=null` always; flagged in report | spec |
| Daily log entry IDs | single monotonic counter across food + dose | spec ("they share LogEntry discriminated union") |

---

## Open / carry-forward items

### Architectural (queued for next pass)

- **Phase-2 helper extraction** — `_strip_pending_from_day_patterns` is now duplicated in `nutrios_setup_resume._strip_pending`, `nutrios_write._strip_pending_from_day_patterns`, and used by `_build_goals_payload` semantically. The migrator writes; the runtime strips. With 3+ callers, extracting a shared helper to `nutrios_store` (or a new `nutrios_pending` module) is the right move. Defer to step 7 cleanup.
- **Discriminated-union input models for tools** — carry-forward from step 6+6.6.
- **`sys.path.insert` → `pyproject.toml`** — step 8 cleanup.

### Operational

- **Live cutover** — Ranbir runs against a copy of his real v1 tree, separately. Migration Phase 1 is fixture-only at the build level; live cutover is operational.
- **Step 4 (mnemo)** — explicitly deferred.

### Step 7 prereqs

- `event_today`/`event_next` caller pairing rule — orchestrator prompt
- `recipe_save_eligible` surfacing logic — orchestrator
- `kcal_actual` int discipline — tool callers
- Setup-resume gate (allowed/blocked intents) — orchestrator

### LOW findings not addressed this pass

- **#8** — `_transform_recipes` silent coercion of non-int recipe ids. Correctness is preserved (quarantine catches the bad recipe via name-based slug); documented as intentional defensive coercion.
- **#10** — All migrated food entries share noon-local `ts_iso`. v1 had no per-meal timestamps; the `id` counter is the source of order. A code comment in `_transform_daily_logs` is the cheapest follow-up.

---

## Stop condition reached

`nutrios_migrate.py` is built, fixtures cover every transformation rule, all 524 tests pass, the migrator runs end-to-end via `python -m` against the full fixture tree producing a report that matches the golden, all four exit codes verified, all four tripwires verified, code-reviewer subagent invoked and findings addressed. **Step 6.5 closed.**

Next gate: step 7 (orchestrator + module prompts), conditional on Mnemo (step 4) decision.
