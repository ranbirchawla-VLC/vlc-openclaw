# REVIEW_phase17.md — query_targets.py v2

**Verdict:** Pass. All 562 tests green (528 prior + 34 new). Zero regressions.

## Test Summary

| Category | Count | Description |
|----------|-------|-------------|
| A. Cycle gate | 4 | no_focus, stale_focus, malformed JSON, message text |
| B. Filtered list | 6 | Focus-only, cycle_reason, momentum sort, tie-breaker, confidence, max_buy_override |
| C. Override mode | 5 | Full universe, warning, no cycle_reason, works without focus, honors filters |
| D. Filters + validation | 5 | brand, signal, no results, budget, bad sort, bad format |
| E. Premium status | 2 | In ok response, in gate response |
| F. Error paths | 2 | Missing cache, stale schema |
| G. Path isolation | 1 | No production path leakage |
| H. CLI | 3 | parse_filters (2), subprocess smoke |
| Internal helpers | 5 | Sort by volume/signal/max_buy, not_in_cache, reserve format from risk |
| **Total** | **34** | All hand-computed; no v1-output circularity |

## Decisions Surfaced and Resolved

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| 1. Stale vs missing focus | (b) Differentiated gate | Consistent with Phase 16; both states block, but state field lets LLM frame differently |
| 2. Filter parsing surface | (c) v1 minus irrelevant | Dropped: priority tiers, discoveries, _best_platform. Kept: brand, budget, format. Added: signal, sort, ignore-cycle |
| 3. Sort default | Momentum desc, volume desc, ref asc | Volume as secondary = data quality signal; ref asc = deterministic tiebreak |

## Required Fixes Applied

| Fix | What | How |
|-----|------|-----|
| 1. Sort validation | Invalid --sort returns error/bad_filter | _validate_filters checks sort_by, format, signal; lists accepted values. Tests D18, D19 |
| 2. targets_not_in_cache | Count at top level | targets_not_in_cache_count integer always present in ok response. Test in TestTargetsNotInCache |
| 3. Override + filters | Override honors all filters | Documented and tested: C14 test_override_with_filters |

## Push-back Resolution

Direct _build_target_entry tests (#25/#26) dropped per option (a). Format derivation tested through public API: TestTargetsNotInCache.test_reserve_format_from_risk verifies risk_nr=45 -> format="Reserve", max_buy=max_buy_res. DRY extraction of derive_format_and_max_buy to grailzee_common flagged for Batch B.

## max_buy_override Read-Through

Implemented in _build_target_entry: reads max_buy_override from focus target, uses it when non-null. Tested: B10 test_max_buy_override_honored (override=3100 vs computed=2910 -> effective=3100).

## v1 Behavior Deliberately Dropped

| v1 Feature | Reason |
|-----------|--------|
| Priority tiers (HIGH/MEDIUM/LOW) | Guide principle #2: no tiers, signal replaces priority |
| Discoveries section | Emerged/watchlist are report-time outputs |
| _best_platform helper | LLM decides platform in capability layer |
| summary_line | LLM formats the response |
| sweet_spot, search_terms, notes | v1 brief-specific fields not in v2 cache |
| sourcing_brief.json as data source | v2 reads analysis_cache.json directly |

## Scope Creep Flags

| Flag | Target | Status |
|------|--------|--------|
| derive_format_and_max_buy extraction | Batch B | DRY: evaluate_deal + query_targets both compute format from risk_nr |
| max_buy_override end-to-end | Phase 24 | Strategy skill must write overrides; query_targets already reads them |
| Phase 16 Flag A (alt_refs) | Resolved for query_targets | Focus matching uses exact keys; strip_ref not needed |

## File Inventory

| File | Lines | New/Modified |
|------|-------|-------------|
| scripts/query_targets.py | 599 | New (guide target: ~120; larger due to decomposed helpers, validation, and 4 response shapes) |
| tests/test_query_targets.py | 819 | New |
| REVIEW_phase17.md | ~80 | New |
