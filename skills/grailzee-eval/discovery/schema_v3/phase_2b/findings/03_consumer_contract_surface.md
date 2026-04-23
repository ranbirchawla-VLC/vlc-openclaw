# 2b.I.3 — Consumer Contract Surface

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Purpose**: Catalogue every reader of `analysis_cache.json` and in-process `all_results`; identify what breaks at 2b ship.

---

## analysis_cache.json file readers

These consume the written cache file. All break at 2b ship when `schema_version: 3` and market fields move into `buckets`.

| File | Lines | What it reads | Break? |
|------|-------|---------------|--------|
| `scripts/evaluate_deal.py` | 85-96 | `schema_version` (stale-schema guard), `cache["references"]`, `cache["dj_configs"]` flat entry with `median, max_buy_nr, max_buy_res, risk_nr, signal, volume, st_pct, momentum, trend_signal` | Yes; all per-ref market accesses broken |
| `scripts/build_shortlist.py` | 82-118, 262-264 | `cache["references"][ref]` flat per-ref shape; `entry.get("signal")`, `entry.get("median")`, `entry.get("max_buy_nr")`, etc. | Yes; flat per-ref market fields absent in v3 |
| `scripts/run_analysis.py` | 288-298 | `cache_dict["references"]` sub-dict passed to `build_shortlist.run` | Yes; `build_shortlist` breaks |

Note: `evaluate_deal._load_cache` currently checks `schema_version < CACHE_SCHEMA_VERSION`. If `CACHE_SCHEMA_VERSION` bumps from 2 to 3 in `grailzee_common.py`, then a v2 cache would fail the check (3 > 2, condition inverted: v2 cache has schema_version=2, 2 < 3, would return stale-schema error). A v3 cache (schema_version=3) passes (3 < 3 is false). So the schema guard behavior is correct for v3 reads but `evaluate_deal` itself still breaks on the field accesses.

---

## In-process `all_results` readers (pipeline scripts)

These receive `all_results` as a Python dict argument from `run_analysis.py`. They do NOT read the cache file, but they expect the v2 flat per-reference market shape. In v3, `all_results` from `analyze_buckets.py` has `buckets` inside each reference entry.

| File | Lines | What it reads | Break? |
|------|-------|---------------|--------|
| `scripts/analyze_brands.py` | 85 | `all_results["references"][ref]["signal"]`, `["volume"]`, `["median"]` | Yes |
| `scripts/build_spreadsheet.py` | 103, 110, 114, 117 | `ref_data["max_buy_res/nr"]`, `["median"]`, `["signal"]`, `["volume"]` | Yes |
| `scripts/build_summary.py` | 50-51, 95, 108 | `r["signal"]`, `r["max_buy_nr"]`, `r["max_buy_res"]`, `r["volume"]` | Yes |
| `scripts/build_brief.py` | 97, 108, 145, 176, 181, 202, 207 | `rd["signal"]`, `rd["volume"]`, `rd["max_buy_nr/res"]`, `rd["median"]` | Yes |

---

## Tests that pin v2 shape (require `pytest.skip`)

| File | Lines | What is pinned | Skip marker needed? |
|------|-------|----------------|---------------------|
| `tests/test_write_cache.py` | 148-151 | `cache["schema_version"] == 2` and `CACHE_SCHEMA_VERSION == 2` | Yes (2c restores; but CACHE_SCHEMA_VERSION constant itself changes in 2b) |
| `tests/test_write_cache.py` | 181-198 | Exhaustive per-ref key set (v2 flat shape: median, max_buy_nr, signal, etc.) | Yes |
| `tests/test_write_cache.py` | 216-234 | Specific v2 field values (ref["median"] == 3200, ref["signal"] == "Strong", etc.) | Yes |
| `tests/test_run_analysis.py` | 450-472 | `test_reference_has_all_cache_fields` pins v2 per-ref key set | Yes |
| `tests/test_run_analysis.py` | 447, 254-269 | Direct `cache["references"]["79830RB"]["median"]`, `ref["max_buy_nr"]` accesses | Yes |
| `tests/test_analyze_references.py` | entire file | Tests against v2 `analyze_references.score_all_references` and `load_sales_csv` interfaces | Yes (module deprecated in 2b) |
| `tests/test_build_shortlist.py` | whole file | Calls `_flatten_row` which reads flat per-ref shape | Yes |
| `tests/test_evaluate_deal.py` | fixture setup (62-65) uses flat per-ref shape | Direct field construction for eval tests | Yes (2c) |

---

## NOT breaking (no v2 cache shape access)

| File | Status |
|------|--------|
| `scripts/ingest.py` | Frozen; no cache access |
| `scripts/ingest_report.py` | CSV producer; no cache access |
| `scripts/analyze_trends.py` | Reads raw CSVs; does not read cache |
| `scripts/analyze_changes.py` | Reads raw CSVs only |
| `scripts/analyze_breakouts.py` | Reads raw CSVs only |
| `scripts/analyze_watchlist.py` | Reads raw CSVs only |
| `scripts/read_ledger.py` | Reads trade_ledger.csv only |
| `scripts/write_cache.py` | Writer (being reshaped in 2b) |
| `tests/test_ingest.py` | Tests ingest.py only |
| `tests/test_analyze_trends.py` | No cache file read |
| `tests/test_analyze_changes.py` | No cache file read |
| `tests/test_analyze_brands.py` | Tests brand rollup but fixture uses flat shape (breaks; add skip) |

---

## `test_analyze_brands.py` is a pipeline consumer break

`test_analyze_brands.py` constructs test fixtures using flat reference dicts with `signal`, `volume`, `median`. `analyze_brands.run(all_results, trends)` will receive v3 shape in 2b. Tests in this file that pass flat fixtures to `analyze_brands.run` will pass (since `analyze_brands` receives a dict — its fixture is manually constructed), but the production run path will break when `run_analysis.py` calls `analyze_brands.run(all_results, ...)` with v3 shape from `analyze_buckets.py`.

This is an integration break, not a test-fixture break. Captured here as a note for the operator: `analyze_brands.py`, `build_spreadsheet.py`, `build_summary.py`, `build_brief.py` integration tests (specifically `test_run_analysis.py`) cover this break implicitly.

---

## 2c planning input

Consumers requiring restoration in 2c (ordered by functional priority):
1. `build_shortlist.py` — strategy reading-partner input; restore with per-bucket read path
2. `evaluate_deal.py` — bot deal evaluator; restore with per-bucket lookup (four-axis)
3. `analyze_brands.py` — summary stats; needs per-bucket signal aggregation (Patch 1 addition)
4. `build_spreadsheet.py` — human-readable outputs; needs per-bucket read path (Patch 1 addition)
5. `build_summary.py` — human-readable outputs; needs per-bucket read path (Patch 1 addition)
6. `build_brief.py` — human-readable outputs; needs per-bucket read path (Patch 1 addition)
7. `CACHE_SCHEMA_VERSION` in `grailzee_common.py` — consumers check `< CACHE_SCHEMA_VERSION`; bump to 3 in 2b

Note: items 3-6 are in-process `all_results` consumers (not `analysis_cache.json` file readers). Added per Patch 1 resolution of Q1 from §4 plan-review. Their tests receive `2c-restore` skip markers in T6. Call sites in `run_analysis.py` are wrapped with log-and-skip per T9 (not removed).

---

## grailzee-cowork bundle

`skills/grailzee-cowork` reads `analysis_cache.json` for the outbound bundle. In 2b, the bundle picks up the v3 cache (role 6 `analysis_cache`). The strategy skill reads `analysis_cache.json` from inside the bundle. Strategy skill adaptation is 2c scope.
