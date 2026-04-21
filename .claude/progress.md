# Grailzee Eval v2 Build Progress

Branch: `feature/grailzee-eval-v2` (27 commits ahead of `main`; last 3 not yet pushed)
Build guide: `skills/grailzee-eval/Grailzee_Eval_v2_Implementation.md`
Authoritative schema spec: `state/grailzee_schema_design_v1_1.md`; v1 doc at `state/grailzee_schema_design_v1.md` remains byte-identical and is flagged as redundant
Test count: 1039 passing
Last phase completed: **A.cleanup.3 post-Phase-A hygiene sweep on 2026-04-21.** Phase A + cleanup complete.
Working tree: clean

## Completed Phases

| Phase | Commit | What |
|-------|--------|------|
| 0 | `eaa8654` | Preflight audit, plan doc rename, gitignore cleanup |
| 1 | `f03b176` | grailzee_common.py (578 lines); all constants, formulas, ref matching, DJ configs, quality filter, name cache, cycle helpers, presentation premium, OTel tracer. 64 tests. |
| 2 | `531fee2` | Name cache seed (22 entries to Drive), requirements.txt, OTel packages installed. 73 tests. |
| 3 | `4845d6d` | read_ledger.py + ledger_manager.py; LedgerRow dataclass, CSV I/O, 4 CLI subcommands (log/summary/premium/cycle_rollup). Fixture cycle_ids corrected from weekly to biweekly. 123 tests. |
| 4 | `9cdef96` | backfill_ledger.py; validate/preview/commit CLI, 15 validation rules, atomic commits. No historical data written. 165 tests. |
| 5 | `b6f913b` | ingest_report.py; Excel to CSV with sell-through join. Programmatic fixture builder. 5 normalizers. 216 tests. |
| 6 | `b006c44` | analyze_references.py; scoring engine extracted from v1. calc_risk, analyze_reference, score_all_references, DJ config breakout. v1/v2 equivalence confirmed. 243 tests. |
| 7 | `7dd8ce0` | analyze_trends.py; compare_periods extracted from v1, momentum_score new per guide 7.6. v1/v2 equivalence confirmed. 278 tests. |
| 8 | `a5c9094` | analyze_changes.py; emerged/shifted/faded/unnamed detection. New in v2 (no v1 equivalent). 298 tests. |
| 9 | `403c379` | analyze_breakouts.py; median >8%, volume >2x, sell-through +15pp. New in v2. 322 tests. |
| 10 | `3aa537f` | analyze_watchlist.py; 1-2 sale refs with no prior activity. New in v2 (v1 labeled these "Low data" and dropped). 346 tests. |
| 11 | `13703c8` | analyze_brands.py; brand-level momentum rollups. New in v2. Guide Section 12 fixed: run() now takes (all_results, trends). 371 tests. |
| 12 | `ce6f6ab` | roll_cycle.py; cycle_outcome.json production. New in v2 (no v1 cycle concept). Thin wrapper around read_ledger.cycle_rollup(). 388 tests. |
| 13 | `e10c95f` | build_spreadsheet.py + build_summary.py + build_brief.py; spreadsheet (3 sheets), markdown summary, dual-output sourcing brief. 438 tests. |
| 14 | `a2e9244` | write_cache.py; v2 cache schema (Section 13), backup rotation (10), run history (50). CACHE_SCHEMA_VERSION=2 in grailzee_common.py. 469 tests. |
| 15 | `b0793ea` | run_analysis.py; full pipeline orchestrator. cycle_id_from_csv() + apply_premium_adjustment() added to grailzee_common.py. 19 integration tests on 27k-row fixtures. 488 tests. |
| 16 | `f093f3a` | evaluate_deal.py v2 (724 lines); 8 private helpers, 4-pass cache lookup, on-demand CSV fallback, confidence enrichment, cycle focus alignment, premium status surfacing. 528 tests. |
| 17 | `af1e1f2` | query_targets.py v2 (599 lines); cycle discipline gate, override mode, focus filtering, momentum sort, confidence enrichment. 562 tests. |
| 18-19 | `dc955c0` | MNEMO seeding (10 memories) + 4 capability files (report, deal, targets, ledger). |
| 20 | `5814701` | SKILL.md top-level intent dispatcher. |
| 21 | `ed8af9d` | Pre-deletion audit — clean post-remediation. |
| 22-23 | `286d58b` | Migration: v2 replaces v1; legacy grailzee-eval deleted. |
| 24a | `f0b3b62` | grailzee-cowork: outbound bundle builder + inbound handler + tests. |
| 24b | `4fc11ff` | grailzee-cowork code-review pass + grailzee-strategy Chat skill (strategy_output_v1 schema, dual-input dispatch, JSON apply pipeline). |
| A (old) | `30a60ce` → `ee6d4f4` | Backfill script rewrite + 14-row historical seed CSV. Real write executed. |
| A.5 (old) | `2c7e0a5` → `e511d52` | Per-cycle outcome files. Stale `cycle_outcome.json` (singular) removed. |
| A.7 | `15c431d` → `d0f8052` | Cowork bundle + strategist wiring; `resolve_previous_cycle_outcome()` walks prev_cycle() chain. |
| A.8 | `45fe96f` → `73407c0` | Full-ledger bundling. Strategist reads full ledger + splits into current-cycle slice + full-history view. |
| 0.1 | `fd86981` | OTEL coverage audit. Report tracked at `state/grailzee_otel_audit.md`. |
| 0.2 | `1766872` | backfill_ledger.py instrumentation. 1 top-level + 6 inner spans with canonical attrs. |
| A.1 | `758e3f9` | config_helper.py module + 51 tests. `read_config`, `write_config`, `mark_field_set`, `is_defaulted`, `schema_version_or_fail`, `defaulted_fields_of`. |
| A.2 | `10f2569` | analyzer_config.json + consumer migration. Externalized 6 tuning constants; 2 loader helpers added; 5 consumers switched to config reads; 44 tests added. |
| A.3 | `5d5a23c` | brand_floors.json + installer + walker + tests. Pure file creation; no consumer yet (B.6 target). 5 brand entries per v1.1 §1 Item 1. |
| A.4 + cleanup.2 | `ca9effd` | A.4: sourcing_rules.json + build_brief hybrid migration + load_sourcing_rules loader. A.cleanup.2: 6-item consistency sweep. 895 tests. |
| cleanup.1 | `276cd98`, `6b5d068`, `2d5490e`, `fd86981` | Four hygiene commits. |
| permissions | `35d5964` | Read-only permissions allowlist added to `.claude/settings.json`. |
| A.5 Surface 1 | `02d1143` | Three installers (cycle_focus, monthly_goals, quarterly_allocation) with Drive-backed defaults, 76 new tests + load_cycle_focus v1-shape compat. Resolves cowork KNOWN_ISSUES #1 placeholder fabrication. 973 tests. |
| A.5 Surface 2 | `3514549` | Cowork bundle includes all 6 configs with analyzer-native naming; role rename `cycle_focus_current` → `cycle_focus` + legacy archive alias; `workspace_state_dir` kwarg + CLI flag; 11 new bundle tests. 985 tests. |
| A.6 Surface 1 | `20b8cb0` | Cowork `_parse_cycle_id` biweekly-semantics fix. `_cycle_calendar_position` delegates to analyzer-side `cycle_date_range`; 6 regression tests covering NN 1-26 and month-spanning cycles; 2 bug-encoding tests updated. 991 tests. |
| A.6 Surface 2 | `47c3867` | Ledger schema migration v1 → v2. LEDGER_COLUMNS, LedgerRow, parse_ledger_csv (hard-cutover reject on v1 header), ledger_manager.log signature (`--buy-date` required, `--sell-date` default today), read_ledger (groups on sell_cycle_id), backfill_ledger, write_cache all updated. New `migrate_ledger_v2.py` with backup + cycle-mismatch abort + idempotence. 1008 tests. |
| A.6 execute | (no commit; 2026-04-21) | Live Drive ledger migrated. 14 rows, all legacy (blank buy_date/buy_cycle_id per S6). Backup at `trade_ledger.csv.v1_backup` on Drive. Six-gate verification all green: parse_ledger_csv read-back, read_ledger enrichment, roll_cycle per-cycle, write_cache confidence, cowork bundle. |
| A.cleanup.3/C1 | `99f6204` | fsync port in `backfill_ledger.write_ledger_atomic` + `roll_cycle.run` (kill -9 / crash / power-loss durability). 7 unreferenced backfill_sample/backfill_template fixtures deleted. |
| A.cleanup.3/C2 | `cf22307` | `migrate_ledger_v2` dry-run preview uses `csv.writer(sys.stdout)` instead of `",".join` (quote-safety for comma-containing values; 1 new test). `test_evaluate_deal._write_ledger` helper + 9 row literals rewritten to v2-native keys (pure rename). |
| A.cleanup.3/C3 | `eac745b` | Installer `main()` CLI test suite: shared `_installer_main_helpers.py` + parametrized `test_installers_main_cli.py` covering all 6 Phase A installers × 5 checks = 30 new tests (--help, --dry-run default target, --force fresh, --force overwrite, unknown flag). 1039 tests. |
| A.cleanup.3 filesystem-only | (no commit; 2026-04-21) | Items 1+2: accidental empty `.git` phantom removed from `skills/grailzee-eval/` (no commits, no remote); `/tmp/a5_drive_backup/*.pre_a5` deleted (48h window expired). |

## Phase A + cleanup complete.

All five strategy-writable config files present, cowork bundle carries all six (three workspace + three Drive), ledger is v2, cowork boundary-detection bug fixed. Branch pushed to origin.

## Next phases

- **C.1** — cycle_focus schema_version v1 → v2. Target entries grow from reference strings to objects carrying stamped predictions (`predicted_nr_clear_prob`, `expected_net_at_median`, `dollar_per_hour`, `capital_required`, `max_buy_nr`, `max_buy_res`, `notes`). Per schema v1 §2.4. Strategy commits the numbers; analyzer doesn't predict. Requires C.2+ (cycle_targets archive, grading) to complete the prediction loop.
- **B.1+** — consumer wiring for A.4-written fields (labor, monthly_return, premium_model close_count_floor, premium_model.min_trade_count).

## Scripts Built So Far

```
scripts/
  grailzee_common.py             (~980 lines; shared constants, formulas, loaders, utilities; LedgerRow v2 shape)
  config_helper.py               (470 lines; v1.1 §2 defaulted_fields helper, A.1)
  install_analyzer_config.py     (134 lines; A.2 installer)
  install_brand_floors.py        (179 lines; A.3 installer)
  install_sourcing_rules.py      (135 lines; A.4 installer)
  install_cycle_focus.py         (189 lines; A.5 Surface 1 installer; Drive-backed default)
  install_monthly_goals.py       (151 lines; A.5 Surface 1 installer; Drive-backed default)
  install_quarterly_allocation.py (168 lines; A.5 Surface 1 installer; Drive-backed default)
  migrate_ledger_v2.py           (264 lines; A.6 Surface 2 one-shot v1→v2 rewrite; backup + idempotence)
  seed_name_cache.py             (109 lines; fixture seeder)
  read_ledger.py                 (~290 lines; groups on sell_cycle_id; emits buy_* + sell_* keys)
  ledger_manager.py              (~285 lines; --buy-date required, --sell-date default today)
  backfill_ledger.py             (~555 lines; v2 OUTPUT_COLUMNS; input schema unchanged; dedup on sell_date)
  ingest_report.py               (431 lines)
  analyze_references.py          (355 lines; reads scoring config)
  analyze_trends.py              (247 lines)
  analyze_changes.py             (135 lines)
  analyze_breakouts.py           (129 lines)
  analyze_watchlist.py           (65 lines)
  analyze_brands.py              (79 lines)
  roll_cycle.py                  (~80 lines; atomic-write cleanup + fsync ported)
  build_spreadsheet.py           (262 lines)
  build_summary.py               (163 lines)
  build_brief.py                 (~290 lines; hybrid _resolved_sourcing_rules)
  write_cache.py                 (155 lines; last_trade reads t["sell_date"])
  run_analysis.py                (~145 lines; outer CLI span emits analyzer_config_source + sourcing_rules_source)
  evaluate_deal.py               (~725 lines; reads risk_reserve_threshold from config)
  query_targets.py               (599 lines)
  report_pipeline.py             (~145 lines; --trend-window reads from analyzer_config)
```

## State Files

```
Repo state/ (workspace):
  analyzer_config.json           (A.2; tracked)
  brand_floors.json              (A.3; tracked)
  sourcing_rules.json            (A.4; tracked)
  grailzee_schema_design_v1.md   (tracked; byte-identical with v1.1)
  grailzee_schema_design_v1_1.md (authoritative; tracked)
  grailzee_otel_audit.md         (Task 0.1 report; tracked)

Drive STATE_PATH (not in git):
  trade_ledger.csv               (v2 shape post-A.6; 14 rows all with blank buy_*)
  trade_ledger.csv.v1_backup     (A.6 rollback path; v1 shape; preserved)
  cycle_focus.json               (A.5 starter; cycle_id="starter", epoch date range)
  monthly_goals.json             (A.5 starter; month="starter")
  quarterly_allocation.json      (A.5 starter; quarter="starter")
  analysis_cache.json            (analyzer output)
  cycle_outcome_cycle_*.json     (per-cycle rollups)
  run_history.json               (analyzer audit trail)
  name_cache.json                (display lookup)
```

## Architecture Decisions

- **Config files — Drive vs workspace.** A.2–A.4 configs live in workspace state (repo-tracked, shipped with code). A.5 configs (cycle_focus/monthly/quarterly) live on Drive STATE_PATH because cowork apply rewrites them at strategy commits. The `CYCLE_FOCUS_PATH` / `MONTHLY_GOALS_PATH` / `QUARTERLY_PATH` constants in grailzee_common match the Drive location; A.5 installers default there too.
- **Hard cutover for ledger schema (A.6).** `parse_ledger_csv` raises ValueError on any CSV missing `sell_date`/`sell_cycle_id` columns. No silent compat shim. Migration vehicle (`migrate_ledger_v2.py`) is a one-shot rewrite with explicit `.v1_backup` copy and cycle-mismatch abort.
- **Biweekly cycle semantics (A.6 Surface 1).** NN in `cycle_YYYY-NN` is a biweekly counter (1-26+ per year), NOT a calendar month. Cowork `_cycle_calendar_position` delegates to analyzer-side `cycle_date_range` to derive month/quarter from the cycle's START date. Single source of truth for biweekly math stays in grailzee_common.
- **Cowork bundle scope (A.5 Surface 2).** Six config files from two locations (three workspace + three Drive) carried byte-faithful. `workspace_state_dir` kwarg + `--workspace-state-dir` CLI flag. Legacy `cycle_focus_current.json` archive alias (not a manifest role) retained for one cycle while strategy-side docs migrate.
- **Memoized loaders with fallback.** Each config has a `load_*` function with module-level memoization, a `*_source()` accessor (`"file"` | `"fallback"`), and a `_reset_*_cache()` test helper. Fallback is always a deep copy of `*_FACTORY_DEFAULTS`. Cache-once-per-process matches the cycle-boundary change-propagation rule.
- **Installers follow a shared pattern.** `--target`, `--force`, `--dry-run` flags; exit codes 0/1/2; OTel span with `outcome` attribute; refuse-overwrite by default. Writes via `config_helper.write_config` (atomic tmp+fsync+os.replace with cleanup leg).
- **`defaulted_fields` construction.** A.2/A.4 use `config_helper.leaf_paths`. A.3 uses a purpose-built `_floor_pct_paths` walker (only `floor_pct` subkeys are tunable). A.5 cycle_focus uses an inline collapse helper for `cycle_date_range` (parent path, not start/end). A.5 quarterly_allocation uses a custom walker to inject empty-dict parent paths that `leaf_paths` alone drops.
- **Hybrid migration for build_brief (A.4).** `_resolved_sourcing_rules()` merges build_brief-internal fields with file-backed fields; emitted JSON brief shape unchanged.
- **Span attribute standardization.** Application-level span attributes use `outcome`, never `status`. Returned dicts may still carry `"status"` as public API.
- **Narrowed loader except.** Loaders catch `(OSError, json.JSONDecodeError, SchemaVersionError, ValueError)`; `TypeError` and other bugs propagate.

## Key Decisions Made (carried forward)

- RISK_RESERVE_THRESHOLD = 0.40 (fraction); v1 was 20 (percent).
- CORE_REFERENCES dropped; every ref with 3+ sales scored.
- Fixture cycle_ids use biweekly numbering.
- `classify_dj_config` returns `None` (not "Other") for unclassifiable titles.
- `QUALITY_CONDITIONS = {"very good", "like new", "new", "excellent"}`. Not externalized yet.
- Name cache seed: 22 entries.
- OTel: single span per CLI entry point plus per-phase spans where operation is visible; `outcome` attribute on every span with multi-branch termination.
- All tests use `--ledger` / `--cache` / `--output-dir` overrides; no test touches real Drive paths.
- v1 frozen; changes under `skills/grailzee-eval/` only in commissioned A-phase scope.
- CACHE_SCHEMA_VERSION = 2.
- `cycle_id_from_csv` parses date from CSV filename, falls back to today.
- evaluate_deal Decision 1: not_found returns comp_search_hint + formula; LLM does web research.
- evaluate_deal Decision 2: stale cycle focus returns `state="stale_focus"`; deal eval always completes.
- evaluate_deal Decision 3: no confidence caching.
- query_targets cycle discipline: `status="gate"` blocks list unless `--ignore-cycle`.
- A.5: `cycle_id="starter"`, `month="starter"`, `quarter="starter"`, epoch `cycle_date_range` sentinels. `is_cycle_focus_current("starter")` returns False by design.
- A.6 / S6: legacy ledger rows (buy_date=blank, buy_cycle_id=blank) still enter cycle_outcome rollups via sell_cycle_id. Grading (C-phase) skips them.

## Standing rule: plan-review divergence surfacing

When a task spec says X and I plan Y for consistency with prior phase or codebase convention, surface the divergence at plan-review (before build), not only in close-out. Phrase as "Spec says X; I plan Y because Z — confirm or override." Memory saved at `~/.claude/projects/-Users-ranbirchawla--openclaw-workspace/memory/feedback_plan_review_divergences.md`.

## Backlog (open; not blocking C.1)

- **Cowork OTEL instrumentation.** `build_bundle.py` has zero OTel spans. Separate cowork OTel audit + instrumentation task. Flagged during A.5 and A.6 plan-review; explicitly deferred.
- **Strategy-skill docs migration.** `grailzee-strategy/SKILL.md:37`, `references/strategy-framework.md:63,130`, `TESTING.md:72,179`, and cowork docs still reference `cycle_focus_current.json`. Migrate docs and drop the `cycle_focus_current.json` archive alias from `build_bundle.py` in a follow-up.
- **QUALITY_CONDITIONS externalization.** `grailzee_common.QUALITY_CONDITIONS` is scoring-relevant but not in any Phase A config.
- **`premium_model.min_trade_count`.** `calculate_presentation_premium` still has a hardcoded `count >= 10` check while `premium_model.close_count_floor` (=5) exists unused.
- **A.4 unused config fields.** `labor.hours_per_piece`, `margin.monthly_return_target_fraction`, `premium_model.{lookback_days, close_count_floor, recent_weighted}` ship as defaults with no consumer.
- **Markdown footer inconsistency.** `build_brief` markdown footer strings hardcoded while JSON brief `sourcing_rules` fields come from config.
- **`--name-cache` threading residual.** `backfill_ledger` accepts `--name-cache` but downstream hooks (`ledger_manager`, `roll_cycle`) don't take that flag.
- **`hook_failed` per-hook granularity.** Single boolean latch per `post_write_hooks` span; can't distinguish subset failures among multiple hooks.
- **A.cleanup.1 leftover.** `.claude/settings.json` PreToolUse hook references `~/ai-code/vlc-openclaw` but repo is at `~/.openclaw/workspace`. Latent; branch-check hits wrong repo.
- **Duplicate schema docs.** `state/grailzee_schema_design_v1.md` and `v1_1.md` are byte-identical; v1 is an authoring artifact. Resolve before schema v2 reference lands.
- **`Grailzee_Eval_v2_Implementation.md` rewrite.** Archival build plan referencing v1 ledger shape throughout. Out-of-date post-A.6; rewrite if a maintainable plan-doc is wanted.
- **March 2026 closes — optional buy_date backfill.** The two March-closed trades (2026-03-24 M79830RB-0001; 2026-03-25 M28500-0003) could have their buy_date filled in by hand if Ranbir has the data. Until then they grade-skip under C.4.
- **REVIEW_phase4.md fixture references.** Archival doc names 7 backfill sample fixtures that were deleted in A.cleanup.3. Harmless but may confuse future readers.

Cleared in A.cleanup.3 (2026-04-21): nested `.git` phantom, `/tmp/a5_drive_backup/*.pre_a5`, fsync drift, unreferenced backfill fixtures, installer main() CLI tests. Count 14 → 12 open items.

## Session log (2026-04-21)

Landed A.5 Surface 1 (`02d1143`), A.5 Surface 2 (`3514549`), A.6 Surface 1 cowork fix (`20b8cb0`), A.6 Surface 2 ledger migration (`47c3867`). Executed live Drive ledger migration via six-gate verification; all gates green. Followed with A.cleanup.3 post-Phase-A hygiene sweep (`99f6204`, `cf22307`, `eac745b`): fsync port in atomic ledger/cycle writes, 7 unreferenced fixture deletions, migrate_ledger_v2 dry-run quote-safety, test_evaluate_deal v2-native key rewrite, 30-test installer main() CLI suite (shared helper + parametrized), filesystem-only cleanup of nested `.git` phantom + `/tmp/a5_drive_backup`. Tests 895 → 1039 across the session (+144 net). `feature/grailzee-eval-v2` now 27 commits ahead of main (last 3 unpushed). **Phase A + cleanup complete.** Ready for C.1.
