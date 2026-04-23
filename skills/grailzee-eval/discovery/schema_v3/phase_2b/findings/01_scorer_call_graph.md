# 2b.I.1 — Current Scorer Call Graph

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Purpose**: Map current flow from CSV load to cache emit; catalogue every field by origin; identify what 2b changes vs what stays.

---

## Full call chain

```
run_analysis.py
  Step 6: analyze_references.run(pricing_csv_paths, name_cache_path)
    -> load_sales_csv(csv) per CSV            # raw sale dicts: {price, condition, papers, reference, make, title, sell_through_pct}
    -> _build_sell_through_map(all_sales)     # {ref: mean(st_pct)} for all refs
    -> load_name_cache(name_cache_path)
    -> score_all_references(all_sales, name_cache, sell_through)
         -> group_sales_by_reference(sales)   # defaultdict(list) by normalize_ref
         -> analyze_reference(ref_sales, st)  # returns per-ref market metrics dict
         -> score_dj_configs(dj_sales)        # 126300 sub-buckets by title keyword
    returns: {references: {ref: {...}}, dj_configs: {...}, unnamed: [...]}

  Step 7: analyze_trends.run(csv_paths, name_cache_path)
    returns: {trends: [...], momentum: {ref: {score, label}}}

  Step 9: analyze_brands.run(all_results, trends)
    reads: all_results["references"][ref]["signal"], ["volume"], ["median"]

  Step 14: build_spreadsheet.run(all_results, ...)
    reads: all_results["references"][ref]["median"], ["signal"], ["volume"], ["max_buy_nr/res"]

  Step 14: build_summary.run(all_results, ...)
    reads: all_results["references"][ref]["signal"], ["max_buy_nr/res"], ["volume"]

  Step 14: build_brief.run(all_results, ...)
    reads: all_results["references"][ref]["signal"], ["volume"], ["max_buy_nr/res"], ["median"]

  Step 15: write_cache.write_cache(all_results, trends, ...)
    Market fields sourced from all_results per-reference:
      brand, model, reference, named,
      median, max_buy_nr, max_buy_res, risk_nr, signal, volume, st_pct,
      condition_mix, capital_required_nr, capital_required_res,
      expected_net_at_median_nr, expected_net_at_median_res
    Trend fields threaded from trends dict:
      trend_signal (trends["trends"][ref]["signal_str"])
      trend_median_change (["med_change"])
      trend_median_pct (["med_pct"])
      momentum (trends["momentum"][ref])
    Ledger-derived fields computed here:
      confidence           <- _confidence_from_trades(trades, brand, ref)
      premium_vs_market_pct, premium_vs_market_sale_count
                           <- _premium_vs_market_from_trades(trades, brand, ref, median)
      realized_premium_pct, realized_premium_trade_count
                           <- _realized_premium_from_trades(trades, brand, ref, median, today)
    DJ config ledger overlay: inherit from parent 126300 entry (B.2/B.3)

  Step 16: build_shortlist.run(cache_dict["references"], cycle_id, ...)
    reads analysis_cache.json references sub-dict (flat per-reference shape)
```

---

## Per-reference field table

| Field | Origin | Function that sets it | In v3 buckets? |
|-------|--------|-----------------------|----------------|
| `brand` | market | `score_all_references` (name cache lookup) | reference-level |
| `model` | market | `score_all_references` (name cache lookup) | reference-level |
| `reference` | market | `score_all_references` | reference-level |
| `named` | market | `score_all_references` | reference-level |
| `median` | market | `analyze_reference` | per-bucket |
| `max_buy_nr` | market | `analyze_reference` | per-bucket |
| `max_buy_res` | market | `analyze_reference` | per-bucket |
| `risk_nr` | market | `analyze_reference` | per-bucket |
| `signal` | market | `analyze_reference` | per-bucket |
| `volume` | market | `analyze_reference` | per-bucket |
| `st_pct` | market | `analyze_reference` (passthrough from st map) | per-bucket |
| `condition_mix` | market | `_condition_mix` inside `analyze_reference` | per-bucket |
| `capital_required_nr` | market | `analyze_reference` (B.5) | per-bucket |
| `capital_required_res` | market | `analyze_reference` (B.5) | per-bucket |
| `expected_net_at_median_nr` | market | `analyze_reference` (B.5) | per-bucket |
| `expected_net_at_median_res` | market | `analyze_reference` (B.5) | per-bucket |
| `trend_signal` | market/trend | `write_cache` from trends dict | per-bucket (threaded from ref-level trend) |
| `trend_median_change` | market/trend | `write_cache` from trends dict | per-bucket (threaded from ref-level trend) |
| `trend_median_pct` | market/trend | `write_cache` from trends dict | per-bucket (threaded from ref-level trend) |
| `momentum` | market/trend | `write_cache` from trends["momentum"] | per-bucket (threaded from ref-level) |
| `confidence` | ledger | `_confidence_from_trades` in `write_cache` | reference-level (unchanged) |
| `premium_vs_market_pct` | ledger | `_premium_vs_market_from_trades` in `write_cache` | reference-level |
| `premium_vs_market_sale_count` | ledger | `_premium_vs_market_from_trades` in `write_cache` | reference-level |
| `realized_premium_pct` | ledger | `_realized_premium_from_trades` in `write_cache` | reference-level |
| `realized_premium_trade_count` | ledger | `_realized_premium_from_trades` in `write_cache` | reference-level |

---

## Functions changing in 2b

| Function / module | Change |
|-------------------|--------|
| `analyze_references.py` (whole module) | Replaced by `analyze_buckets.py`; kept in tree for grep trail until 2c cleanup |
| `write_cache.write_cache` | Reshape: market fields move per-bucket, ledger fields stay at ref level, `schema_version: 3` |
| `run_analysis.py` Step 6 | Replace `analyze_references.run` with `load_and_canonicalize` + new `analyze_buckets` call |
| `grailzee_common.CACHE_SCHEMA_VERSION` | Bump from 2 to 3 |

## Functions staying unchanged

| Function / module | Status |
|-------------------|--------|
| All scoring primitives: `calc_risk`, `analyze_reference`, `max_buy_nr/reserve`, `_condition_mix` | Unchanged; 2b calls them N times (one per bucket) instead of once per reference |
| `_confidence_from_trades`, `_premium_vs_market_from_trades`, `_realized_premium_from_trades` | Unchanged; still called at reference level |
| `analyze_trends.py` | Unchanged; trend data threaded per-bucket in 2b as ref-level passthrough |
| `analyze_changes.py`, `analyze_breakouts.py`, `analyze_watchlist.py` | Unchanged (read raw CSVs, not scorer output) |
| `analyze_brands.py` | Requires shape update (see I.3 consumer break table) |
| `build_spreadsheet.py`, `build_summary.py`, `build_brief.py` | Require shape updates or skip (see I.3) |
| `ingest.py` | Frozen per 2a; no touch |
| `grailzee_common.py` formulas | Unchanged |

---

## Key observation: `st_pct` per-bucket sourcing

In v2, `st_pct` is the reference-level mean sell-through from all rows. In v3 with 4-axis bucketing, `st_pct` should come from `CanonicalRow.sell_through_pct` for the bucket's rows. `CanonicalRow` carries the per-row `sell_through_pct` field (passthrough from ingest_report), so the bucket mean is computable. This is a natural migration; the existing `_build_sell_through_map` logic (mean across all rows for a ref) runs per bucket instead.
