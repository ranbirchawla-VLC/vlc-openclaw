# Grailzee Eval v2 Build Progress

Branch: `feature/grailzee-eval-v2` (20 commits ahead of `main`, not pushed)
Build guide: `skills/grailzee-eval/Grailzee_Eval_v2_Implementation.md`
Authoritative schema spec: `state/grailzee_schema_design_v1_1.md` (now tracked as of commit `fd86981`); v1 doc at `state/grailzee_schema_design_v1.md` remains byte-identical and is flagged as redundant
Test count: 895 passing
Last phase completed: A.cleanup.1 + permissions allowlist (commits `276cd98` through `35d5964`)
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
| A | `30a60ce` → `ee6d4f4` | Backfill script rewrite + 14-row historical seed CSV. Real write executed. |
| A.5 | `2c7e0a5` → `e511d52` | Per-cycle outcome files. Stale `cycle_outcome.json` (singular) removed. |
| A.7 | `15c431d` → `d0f8052` | Cowork bundle + strategist wiring; `resolve_previous_cycle_outcome()` walks prev_cycle() chain. |
| A.8 | `45fe96f` → `73407c0` | Full-ledger bundling. Strategist reads full ledger + splits into current-cycle slice + full-history view. |
| 0.1 | (audit, now `fd86981`) | OTEL coverage audit. Report now tracked at `state/grailzee_otel_audit.md`. |
| 0.2 | `1766872` | backfill_ledger.py instrumentation. 1 top-level + 6 inner spans with canonical attrs. |
| A.1 | `758e3f9` | config_helper.py module + 51 tests. `read_config`, `write_config`, `mark_field_set`, `is_defaulted`, `schema_version_or_fail`, `defaulted_fields_of`. |
| A.2 | `10f2569` | analyzer_config.json + consumer migration. Externalized 6 tuning constants; 2 loader helpers added; 5 consumers switched to config reads; 44 tests added. |
| A.3 | `5d5a23c` | brand_floors.json + installer + walker + tests. Pure file creation; no consumer yet (B.6 target). 5 brand entries per v1.1 §1 Item 1. |
| A.4 + cleanup.2 | `ca9effd` | **Combined commit.** A.4: sourcing_rules.json + build_brief hybrid migration + load_sourcing_rules loader. A.cleanup.2: 6-item consistency sweep (status→outcome rename, narrowed loader except, atomic-write cleanup port, `_NoOpSpan.add_event`, `--ledger` threading, `_run_subcmd` returncode). 895 tests. |
| cleanup.1 | `276cd98`, `6b5d068`, `2d5490e`, `fd86981` | Four hygiene commits: A.7 test fix landed, A.2 docstring corrected, gitignore dev artifacts, schema docs + CLAUDE.md + TOOLS.md committed. |
| permissions | `35d5964` | Read-only permissions allowlist added to `.claude/settings.json`. |

## Next Phases (Phase A remaining per v1.1)

| Phase | Script | Target lines | Status |
|-------|--------|-------------|--------|
| A.5 | Starter values for cycle/monthly/quarterly files | -- | Not started |
| A.6 | (reserved) | -- | -- |
| B.1+ | Consumer wiring for A.4-written fields (labor, monthly_return, premium_model) and later phases | -- | Deferred |

A.5 is the next Phase A task. Per v1.1 §3: write initial `cycle_focus.json`, `monthly_goals.json`, `quarterly_allocation.json` with concrete starter values (capital_target, volume_target, quarterly capital envelope). Ranbir supplies values at the building-chat handoff.

## Scripts Built So Far

```
scripts/
  grailzee_common.py             (920 lines; shared constants, formulas, loaders, utilities)
  config_helper.py               (470 lines; v1.1 §2 defaulted_fields helper, A.1)
  install_analyzer_config.py     (134 lines; A.2 installer)
  install_brand_floors.py        (179 lines; A.3 installer)
  install_sourcing_rules.py      (135 lines; A.4 installer)
  seed_name_cache.py             (109 lines; fixture seeder)
  read_ledger.py                 (283 lines)
  ledger_manager.py              (257 lines; CLI: log/summary/premium/cycle_rollup)
  backfill_ledger.py             (~540 lines; historical import + hooks + atomic cleanup port)
  ingest_report.py               (431 lines)
  analyze_references.py          (355 lines; now reads scoring config)
  analyze_trends.py              (247 lines)
  analyze_changes.py             (135 lines)
  analyze_breakouts.py           (129 lines)
  analyze_watchlist.py           (65 lines)
  analyze_brands.py              (79 lines)
  roll_cycle.py                  (75 lines; atomic-write cleanup ported)
  build_spreadsheet.py           (262 lines)
  build_summary.py               (163 lines)
  build_brief.py                 (~290 lines; hybrid _resolved_sourcing_rules)
  write_cache.py                 (155 lines)
  run_analysis.py                (~145 lines; outer CLI span emits analyzer_config_source + sourcing_rules_source)
  evaluate_deal.py               (~725 lines; reads risk_reserve_threshold from config)
  query_targets.py               (599 lines)
  report_pipeline.py             (~145 lines; --trend-window reads from analyzer_config)
```

## State Files Installed

```
state/
  analyzer_config.json           (A.2)
  brand_floors.json              (A.3)
  sourcing_rules.json            (A.4)
  trade_ledger.csv               (Phase A — 14 historical trades)
  cycle_outcome_cycle_2026-03.json  (A.5)
  cycle_outcome_cycle_2026-04.json  (A.5)
  cycle_outcome_cycle_2026-05.json  (A.5)
  cycle_outcome_cycle_2026-06.json  (A.5)
  cycle_outcome_cycle_2026-08.json  (A.5)
  grailzee_schema_design_v1.md   (committed in fd86981; byte-identical with v1.1)
  grailzee_schema_design_v1_1.md (authoritative)
  grailzee_otel_audit.md         (Task 0.1 report)
```

## Architecture Decisions

- **Config files live in workspace `state/`, not Drive.** `WORKSPACE_STATE_PATH` resolves to the repo-relative state directory. Drive `STATE_PATH` continues to host data files (cache, ledger, cycle outcomes) only. Introduced in A.2.
- **Memoized loaders with fallback.** Each config has a `load_*` function with module-level memoization (first call wins), a `*_source()` accessor (returns `"file"` | `"fallback"`), and a `_reset_*_cache()` test helper. Fallback dict is always a deep copy of `*_FACTORY_DEFAULTS` so consumers never crash on file-absent. Cache-once-per-process is intentional per the cycle-boundary change-propagation rule (schema v1 §5).
- **Installers follow a shared pattern.** `--target`, `--force`, `--dry-run` flags; exit codes 0/1/2; OTel span with `outcome` attribute branch marker; refuse-overwrite by default. Writes via `config_helper.write_config` (atomic tmp+fsync+os.replace with cleanup leg).
- **`defaulted_fields` construction**: A.2/A.4 use shared `config_helper.leaf_paths` (simple leaf walk excluding managed keys). A.3 uses purpose-built `_floor_pct_paths` walker because only `floor_pct` subkeys are strategy-tunable — `tradeable` and `asset_class` are structural declarations.
- **Hybrid migration for build_brief (A.4).** `_resolved_sourcing_rules()` merges build_brief-internal fields (`platform_priority`, `us_inventory_only`, `never_exceed_max_buy` per S2) with the file-backed fields (`condition_minimum`, `papers_required`, `keyword_filters`). Emitted JSON brief shape unchanged.
- **Atomic-write cleanup (A.cleanup.2 Item 10).** `config_helper._atomic_write_json` was the reference pattern. Ported to `backfill_ledger.write_ledger_atomic` and `roll_cycle.run`. `.tmp` file cleanup on any exception via `try/except … raise`.
- **Span attribute standardization (A.cleanup.2 Item 8).** Application-level span attributes use `outcome`, never `status`. `evaluate_deal.py`'s three `status` span attrs renamed. The function's returned dict still carries `"status"` as public API (consumed by bot/capability layer).
- **Narrowed loader except (A.cleanup.2 Item 9).** Both `load_analyzer_config` and `load_sourcing_rules` catch `(OSError, json.JSONDecodeError, SchemaVersionError, ValueError)` — not `Exception`. `TypeError` and similar propagate so unexpected bugs surface.
- **Subprocess hook hygiene (A.cleanup.2 Items 12-13).** `post_write_hooks` now threads `--ledger` through to sibling scripts (flag before subcommand for `ledger_manager.py`'s parent-parser). `_run_subcmd` checks returncode; non-zero exits log to stderr and set `hook_failed=True` on span. Hooks remain best-effort (caller does not abort).

## Key Decisions Made (carried forward)

- RISK_RESERVE_THRESHOLD = 0.40 (fraction); v1 was 20 (percent). Signal thresholds preserved from v1.
- CORE_REFERENCES dropped; every ref with 3+ sales scored.
- Fixture cycle_ids use biweekly numbering (guide Section 4).
- `classify_dj_config` returns `None` (not "Other") for unclassifiable titles.
- `QUALITY_CONDITIONS = {"very good", "like new", "new", "excellent"}`. Not externalized in A.4; schema-evolution candidate for v2 (backlog).
- Name cache seed: 22 entries.
- OTel: single span per CLI entry point plus per-phase spans where operation is visible; `outcome` attribute on every span with multi-branch termination.
- All tests use `--ledger`/`--cache`/`--output-dir` overrides; no test touches real Drive paths.
- v1 frozen; no changes under `skills/grailzee-eval/` outside the commissioned A-phase refactor scope.
- CACHE_SCHEMA_VERSION = 2 lives in grailzee_common.py (Phase 14).
- `cycle_id_from_csv` parses date from CSV filename, falls back to today.
- `apply_premium_adjustment` lives in grailzee_common.py (Phase 15).
- evaluate_deal Decision 1: not_found returns comp_search_hint + formula; LLM does web research.
- evaluate_deal Decision 2: stale cycle focus returns `state="stale_focus"`; deal eval always completes.
- evaluate_deal Decision 3: no confidence caching; `read_ledger.reference_confidence()` on every call.
- query_targets cycle discipline: `status="gate"` blocks list unless `--ignore-cycle`.
- Gate differentiates `no_focus`/`stale_focus`/`error` states.
- Format derivation duplicated in evaluate_deal and query_targets; extraction to grailzee_common flagged for Batch B.

## Standing rule: plan-review divergence surfacing

When a task spec says X and I plan Y for consistency with prior phase or codebase convention, surface the divergence at plan-review (before build), not only in close-out. Phrase as "Spec says X; I plan Y because Z — confirm or override." Adopted after A.3 where `--target` vs spec's `--output-path` landed in close-out rather than plan-review. Memory saved at `~/.claude/projects/-Users-ranbirchawla--openclaw-workspace/memory/feedback_plan_review_divergences.md`.

## Backlog (open; not blocking A.5)

- **QUALITY_CONDITIONS externalization** (scope_creep_backlog.md A.2 flag): `grailzee_common.QUALITY_CONDITIONS` is scoring-relevant but not in any Phase A config. Schema v2 decision: which file owns it (analyzer_config, sourcing_rules, or new scoring_thresholds).
- **`premium_model.min_trade_count`**: `calculate_presentation_premium` still has a hardcoded `count >= 10` check. `premium_model.close_count_floor` (=5) exists in config but no consumer reads it. B.1 planning to decide.
- **A.4 unused config fields**: `labor.hours_per_piece`, `margin.monthly_return_target_fraction`, `premium_model.{lookback_days, close_count_floor, recent_weighted}` ship as factory defaults with no consumer in A.2. B.1+ consumers wire them up.
- **Markdown footer inconsistency** (A.4 co-review): `build_brief`'s markdown footer strings ("US inventory only. Never exceed MAX BUY. Papers required on every deal.") are hardcoded while the JSON brief's `sourcing_rules` fields come from the config file. Pre-existing; not A.4-introduced.
- **fsync drift** (A.cleanup.2 co-review): `backfill_ledger.write_ledger_atomic` and `roll_cycle.run` ported the `.tmp` cleanup leg but not the fsync durability leg from `config_helper._atomic_write_json`. Follow-up: port fsync OR tighten docstrings.
- **`--name-cache` threading** (A.cleanup.2 Item 12 residual): `backfill_ledger` accepts `--name-cache` but the downstream subprocess hooks (`ledger_manager`, `roll_cycle`) don't take that flag. Neither script actually uses name cache today. Decide whether those should honor it before threading.
- **`hook_failed` per-hook granularity**: currently a single boolean latch per `post_write_hooks` span. If multiple hooks run and a subset fail, the span can't distinguish. Fine operationally (grep stderr) but worth revisiting.
- **A.cleanup.1 leftover — PreToolUse hook path**: `.claude/settings.json` PreToolUse hook references `~/ai-code/vlc-openclaw` but the actual repo is at `~/.openclaw/workspace`. Pre-existing latent; branch-check hits wrong repo. Not A.cleanup.1 scope.
- **Installer `main()` end-to-end CLI tests**: A.2/A.3/A.4 all lack tests that exercise the argparse layer. Separate post-A.5 micro-task.
- **Duplicate schema docs**: `state/grailzee_schema_design_v1.md` and `v1_1.md` are byte-identical; v1 is an authoring artifact. Resolve (delete v1) before schema v2 reference lands.
- **Unrelated pre-existing edits from earlier sessions**: none remaining. All A.7 / docs / dev-artifact items landed in cleanup.1.

## Session log (this window: 2026-04-21)

Landed A.2, A.3, A.4, A.cleanup.2, A.cleanup.1 (four commits), and a read-only permissions allowlist. Tests went from 769 → 895. Working tree clean; 20 commits ahead of main, unpushed. Ready for A.5.
