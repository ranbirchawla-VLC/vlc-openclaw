# Grailzee Eval v2 Build Progress

Branch: `feature/grailzee-eval-v2` (single long-lived; unpushed).
Canonical state doc: `GRAILZEE_SYSTEM_STATE.md` at repo root. Historical build log (through 2026-04-24 schema Phase 1 discovery + B.8) preserved at `.claude/progress-v0.md`.

Session-open read-back rule (per global CLAUDE.md): read `GRAILZEE_SYSTEM_STATE.md` first, then this file for the current sub-phase context.

---

## Session 2026-04-24 (evening): ingest_report full-column patch + Phase 2a v3 ingest module

Two ships in one session: the prerequisite patch unblocking 2a, then 2a itself end-to-end.

### Ship 1: commit `f7ecab8` (prerequisite patch)

Phase 2a v1 prompt received with two open gaps. Resolved:
- **Gap 1**: `Grailzee_Schema_v3_Decision_Lock_2026-04-24_v1.md` not at workspace root; operator pointed to `/Users/ranbirchawla/Downloads/GZ Agent/Phase 2/`. Seven locked decisions absorbed.
- **Gap 2**: v2 prompt referenced `GrailzeeData/reports_csv/`; operator directive "ignore the input; keep the existing root". Drive root resolved from `discovery/schema_v3/load.py`.

Pre-discovery structural surface: `reports_csv/` was empty (Phase 1 cleaned it) and existing `ingest_report.py` stripped `Dial`/`Dial Numbers`. Operator chose option (B): patch ingest_report.py to preserve all source columns.

Patch shipped: `OUTPUT_COLUMNS` extended from 8 to 13 (`model, year, box, dial_numerals_raw, url` appended), `SOLD_AT_ALIASES`/`DIAL_ALIASES` for W1/W2 header variants, raw passthrough preserves NBSP. Tests 957 -> 960 (+3 new + 1 modified pin). Live W1+W2 ingested cleanly. Subject-line em-dash caught and amended to semicolon (`87f5c03` -> `f7ecab8`).

Plan-review flags both accepted: (a) `Dial` and `Dial Numbers` are one canonical column not two; (b) `Model` was the unnamed fifth stripped column.

### Ship 2: commit `9777199` (Phase 2a)

v2 2a prompt resumed against the patched CSVs. Five investigation phases ran cleanly (P2a_I[1-5]_findings.md under `discovery/schema_v3/phase_2a/`):

- **I.1** header surface: 12-col xlsx, 2 known variances absorbed by ingest patch; canonical mapping locked.
- **I.2** NBSP: 47+59=106 NR-prefix rows (delta -3 vs Phase 1's 109; within tolerance). NBSP only in `title`. `re.UNICODE` + Python 3.12 catches U+00A0.
- **I.3** asset-class: 0+3=3 LV handbag matches in W2; 0 false positives, 0 false negatives. Phase 1 reproduced exactly.
- **I.4** dedup: 6 W1 + 4 W2 = 10 within-report 4-tuple collisions surfaced (real, not future-proofing); 15 W1 + 18 W2 = 33 within-report 3-tuple near-collisions catalogued (dial-color/year/bracelet variants); cross-report 4-tuple overlap 8,837 (delta -2 vs Phase 1).
- **I.5** numerals fall-through: 9+13=22 rows (6 distinct values: `No Numbers` x10, `Sapphire Numerals` x4, `Plexiglass` x2, `Abaric Numerals` x2, `Other` x1, `Gemstone Numerals` x2).

Operator adjustments at gate: ship within-report dedup as locked + log via summary counter; leave 3-tuple near-collisions in-bucket (4-axis 2b will resolve dial-color and NR-vs-RES; year/bracelet stay as-is); cascade extension for `no numbers` -> `No Numerals` and `abaric` -> `Arabic`; drop the rest as Decision-5-equivalent.

Plan-review tightened the named_special tiebreak: longest-match-wins (not first-match-by-vocabulary-order). Reason: vocabulary contains both `panda` and `reverse_panda`; first-match returns `panda` on a "Reverse Panda" descriptor, silently wrong on every Reverse Panda listing. Pinned by `TestNamedSpecial::test_reverse_panda_not_panda`.

Module shape: single file `skills/grailzee-eval/scripts/ingest.py` (685 lines), parity with sibling scripts. `CanonicalRow` as `@dataclass(frozen=True, slots=True)`; `IngestSummary` as `@dataclass` with 11 counters + source_reports list. Pure `load_and_canonicalize` plus side-effect wrapper `ingest_and_archive`. CLI with `validate` and `ingest` subcommands.

Pipeline order locked per v2 prompt: load -> header validation -> NBSP normalization (load-bearing) -> asset-class filter -> dial-numerals cascade -> dial-color parsing + named_special detection -> auction-type detection -> 4-tuple dedup (within-report first-seen, cross-report prefer-most-recent) -> 3-tuple near-collision count.

Two OTel spans (`ingest.load_and_canonicalize`, `ingest.ingest_and_archive`) emit all 11 summary counters as flat attributes plus `outcome`.

#### Test delta

960 baseline -> **1,046 passing** (+86). Above the +35-to-+55 prompt band; flagged at close-out. Reasoning: heavy parametrization for vocabulary coverage (15-case named_special vocab, 9-case numerals exact-match, etc.); each case is a distinct pytest instance. No tests wasted; consolidating to lists-in-loops would lose per-case failure granularity. Operator accepted.

#### Live spot-check (Part A + Part B)

**Part A** (W1+W2 union, validation): 19,335 source -> 10,440 canonical. Cross-report dedup overlap 8,801 (delta -36 vs Phase 1's 8,837). Delta is filter-aware semantics: pre-filter drops (asset_class + blank + fallthrough = 84 rows) on one report's side prevent the cross-report counter from incrementing for matching keys. Not a regression; documented in `P2a_spotcheck_partA.md`. `dial_color_unknown=1,116` exceeds Phase 1's 392 because v2 prompt's parsed-vs-unknown simplification collapses Phase 1's 1,286 ambiguous bucket into unknown (multi-color-in-window cases). Expected.

**Part B** (W2-only operational rehearsal in tmp tree): 9,895 -> 9,846. Archival happy path works (source moved, original filename preserved, byte-fidelity intact). Idempotency block raises `FileExistsError` and leaves source in place. Live `reports_csv/` untouched; both CSVs still present at session close.

#### Em-dash hygiene

Pre-commit sweep on Phase 2a artifacts: 8 em-dashes in markdown findings + 6 in `discover_2a.py` (script that generated some of them). All replaced with semicolons. Code (`ingest.py`, `test_ingest.py`) was always clean. Subject line of commit `9777199` confirmed clean.

### State of the tree post-session

- Two unpushed commits on `feature/grailzee-eval-v2`: `f7ecab8` (ingest patch), `9777199` (Phase 2a ingest module).
- Live `reports_csv/`: `grailzee_2026-04-06.csv` and `grailzee_2026-04-21.csv` both present, no `archive/` subdir on Drive yet.
- Phase 1 artifacts (`schema_v3/load.py`, `discover.py`, `findings/`) still untracked per default-delete-at-Phase-2-close convention.
- `GRAILZEE_SYSTEM_STATE.md` Section 4 not yet updated; held for operator preference. Both commits ready to be cited in a single STATE entry.

## Session 2026-04-24 (late): Phase 2b; v3 bucket construction, scoring, write_cache reshape

### Shipped (T1-T9 + CACHE_SCHEMA_VERSION bump + T6 skip markers + T7 tests + T8 schema doc)

**T1/T2/T3/T5/G8**: `scripts/analyze_buckets.py` (new, ~390 lines). Four-axis bucket construction (`bucket_key`, `build_buckets`), per-bucket scoring (`score_bucket` delegates to `analyze_reference`), named_special threading (longest-slug-wins, alphabetical tiebreak), DJ config breakout (`_score_dj_configs`), full `score_all_references` with OTel span (`reference_count`, `total_bucket_count`, `scored_bucket_count`, `below_threshold_bucket_count`, `dj_config_count`, `outcome`). CLI entry point.

**T4**: `scripts/write_cache.py` reshaped to v3. New helpers: `_dominant_median` (highest-volume eligible bucket proxy for B.2/B.3 `current_median`); `_best_signal` (best signal across reference's buckets for summary counts); `_SIGNAL_RANK` dict. Per-reference entry: market fields removed, `buckets: rd.get("buckets", {})` added, trend/momentum at reference level per Patch 2. DJ config loop: adds `confidence=None`, `trend_signal="No prior data"`, `trend_median_change=0`, `trend_median_pct=0`, `momentum=None`. Summary counts via `_best_signal`. Docstring updated.

**CACHE_SCHEMA_VERSION bump**: `grailzee_common.py` line 87: `2` -> `3`.

**T9**: `scripts/run_analysis.py` updated. `analyze_references` import removed; `analyze_buckets` + `load_and_canonicalize` added. Step 6 now runs `load_and_canonicalize` + `analyze_buckets.run`; B.4/B.5 OTel attributes adapted to bucket-level counts. Steps 9 (brands), 14 (spreadsheet, summary, brief), 16 (shortlist): wrapped with log-and-skip (2c-restore); `summary_path` defaults to `""`. `import logging` + module-level `_log` added.

**T6 skip markers**:
- `test_analyze_references.py`: module-level `pytestmark` skip
- `test_build_shortlist.py`: module-level `pytestmark` skip
- `test_write_cache.py`: 19 targeted `@pytest.mark.skip` on tests that pin v2 flat shape or depend on `_dominant_median` returning non-None from flat `_ref()` fixtures
- `test_run_analysis.py`: 9 targeted skips (flat-shape pins, output-builder-skipped file assertions, median-dependent pct assertions); `test_no_qualifying_refs` updated to v3 behavior (below-threshold refs ARE in cache with Low data signal)

**Fixture update**: 3 large fixture CSVs + `sales_sample.csv` updated with 5 new v3 ingest columns (`model`, `year`, `box`, `dial_numerals_raw="Arabic Numerals"`, `url=""`). Required by `ingest.py`'s `EXPECTED_CSV_COLUMNS` check.

**T7**: `tests/test_analyze_buckets.py` (new, 49 tests). Covers: `bucket_key` serialization, `build_buckets` grouping, `_named_special_for_bucket` (longest/tiebreak), `_st_pct_for_rows`, `score_bucket` (below/above threshold, key fields, named_special, axes), `score_all_references` (return shape, named/unnamed, multi-ref, two-bucket, empty), DJ config path (config_breakout flag), `_row_to_sale`, W2-scale smoke test (3 tests via real fixture CSV).

**T8**: `grailzee_schema_design_v2_0.md` written; supersedes v1/v1_1. Covers keying, top-level shape, reference entry, bucket entry, DJ configs, summary, producing modules, 2c consumer list, `_dominant_median` interim note.

#### Test delta

Baseline: 1,046 (Phase 2a). Phase 2b close: **997 passed, 98 skipped**. Net change: +49 new tests (T7), 98 tests now carry 2c-restore skip markers (19 test_write_cache.py + 9 test_run_analysis.py + entire test_analyze_references.py + entire test_build_shortlist.py). Skipped tests are greppable via `rg "2c-restore"`.

#### State of tree post-session

- Phase 2b complete; no commit yet (per repo CLAUDE.md: operator commits after review).
- Modified: `scripts/analyze_buckets.py` (new), `scripts/write_cache.py`, `scripts/run_analysis.py`, `scripts/grailzee_common.py` (CACHE_SCHEMA_VERSION=3), `grailzee_schema_design_v2_0.md` (new), `tests/test_analyze_buckets.py` (new), `tests/test_write_cache.py`, `tests/test_run_analysis.py`, `tests/test_analyze_references.py`, `tests/test_build_shortlist.py`, `tests/fixtures/grailzee_2026-04-06.csv`, `tests/fixtures/grailzee_2026-03-23.csv`, `tests/fixtures/grailzee_2026-03-09.csv`, `tests/fixtures/sales_sample.csv`.
- Discovery findings (written this session): `discovery/schema_v3/phase_2b/findings/01_scorer_call_graph.md`, `02_dj_config_pipeline.md`, `03_consumer_contract_surface.md`, `04_bucket_population_census.md`.

#### 2b not-done (deferred to 2c per plan)

- `evaluate_deal.py` bucket-aware lookup
- `build_shortlist.py` `_flatten_row` bucket read-path
- `analyze_brands.py`, `build_spreadsheet.py`, `build_summary.py`, `build_brief.py` v3 read-paths
- Proper per-bucket ledger lookup replacing `_dominant_median`
- `GRAILZEE_SYSTEM_STATE.md` Section 4 update
- Part A + Part B spot-checks and §1.7 analytical-quality benchmark (operator review step, not implementation)

## Next phases

- **Operator review + commit**: review Phase 2b diff (`git --no-pager diff HEAD`), then commit. Two commits expected: one for Phase 2a ingest patch artifacts already staged, one for Phase 2b.
- **GRAILZEE_SYSTEM_STATE.md Section 4 update**: append entries for `f7ecab8` (ingest_report patch), `9777199` (Phase 2a ingest module), and Phase 2b bucket scorer + write_cache reshape. Each entry: shipped surface, test delta, architecture notes.
- **Part A + Part B spot-checks**: W1+W2 union run against live CSVs; verify ~722 eligible buckets (3% tolerance). W2-only pipeline run; confirm v3 cache `schema_version: 3`, 5 DJ config entries, `dj_configs[*].trend_signal == "No prior data"`.
- **§1.7 analytical-quality benchmark**: 10 references side-by-side v2 vs v3 scoring comparison (operator review step).
- **Phase 2c** (after spot-checks pass): `evaluate_deal.py` bucket-aware four-axis lookup; `build_shortlist.py` `_flatten_row` bucket read-path; `analyze_brands.py`, `build_spreadsheet.py`, `build_summary.py`, `build_brief.py` v3 read-paths; proper per-bucket ledger lookup replacing `_dominant_median`; restore 98 skipped tests.
- **Backlog ready-to-execute** (STATE §6): live `sourcing_brief_cycle_2026-06.json` Drive-state gap; `apply_premium_adjustment` + `adjusted_max_buy` dead-code pair; `analyzer_config.premium_model.*` zero-consumer subtree; B.9 watchlist rename (deferred).

## Pointers

- Canonical current-state truth: `GRAILZEE_SYSTEM_STATE.md` at repo root.
- Full prior build history (Phase 0 through B.8 + schema Phase 1 discovery): `.claude/progress-v0.md`.
- Schema v3 lock: `/Users/ranbirchawla/Downloads/GZ Agent/Phase 2/Grailzee_Schema_v3_Decision_Lock_2026-04-24_v1.md`.
- Phase 1 evidence: `skills/grailzee-eval/discovery/schema_v3/findings/PHASE1_REPORT.md`.
- Ingest patch artifacts: `skills/grailzee-eval/discovery/ingest_full_column_patch/findings.md` + `spotcheck.md`.
- Phase 2a artifacts: `skills/grailzee-eval/discovery/schema_v3/phase_2a/` (5 P2a_I*_findings.md + P2a_spotcheck_part[A,B].md + discover_2a.py).
