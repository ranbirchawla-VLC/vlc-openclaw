# REVIEW_phase16.md — evaluate_deal.py v2

**Verdict:** Pass. All 528 tests green (488 prior + 40 new). Zero regressions.

## Test Summary

| Category | Count | Description |
|----------|-------|-------------|
| A. Cache hit decisions | 6 | One per branch: Pass->NO, over-max->NO, ceiling->MAYBE, Careful-route->MAYBE, strong->YES, within->YES |
| B. On-demand CSV fallback | 2 | Found with 5 sales; insufficient with 1 sale |
| C. Not found | 1 | comp_search_hint payload verified |
| D. Cycle focus alignment | 4 | in_cycle, off_cycle, no_focus, stale_focus |
| E. Confidence enrichment | 3 | With history, no history, mixed outcomes (win_rate=60.0%) |
| F. Premium status | 2 | threshold_met=False, threshold_met=True (pre-adjusted max_buy) |
| G. Error paths | 6 | Missing cache, stale schema, bad price, price formatting, bad cycle JSON, missing cycle_id |
| H. Path isolation | 1 | No production path leakage |
| CLI | 2 | Smoke test (subprocess), bad price arg (subprocess) |
| Internal helpers | 11 | _find_reference 4-pass (7), _score_decision (4) |
| Ad budget | 2 | Low median, high median bracket verification |
| **Total** | **40** | All hand-computed; no v1-output circularity |

## Decisions Surfaced and Resolved

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| 1. Web fallback | Return not_found + comp_search_hint | Python stays deterministic; LLM does web research per Section 10.2 |
| 2. Stale cycle focus | state="stale_focus" with both cycle_ids | Section 10.2: deal eval always available; LLM decides presentation |
| 3. Confidence caching | No cache; read CSV every call | Ledger structurally small; sub-millisecond reads |
| Premium adjustment | Reads pre-adjusted max_buy from cache | Confirmed: orchestrator applies before cache write (run_analysis.py:97-101) |
| Raw report fallback | Delegates to analyze_references.analyze_reference() | No scoring duplication; openpyxl dependency eliminated |

## Required Fixes Applied (from plan review)

| Fix | What | How |
|-----|------|-----|
| 1. Careful/Reserve risk band | Document 20-40% band explicitly | Code comment on MAYBE branch (evaluate_deal.py:292-297) |
| 2. Confidence on not_found | Skip enrichment; confidence=null | Unverified input risk; test C9 asserts None |
| 3. Malformed cycle_focus.json | state="error" with parse note | No silent fallback; test G22 asserts error state |
| 4. premium_status by status | error responses omit premium_status | Tests G19, G20 assert key absent |
| 5. CLI test isolation | _parse_price_arg extracted | Unit-testable; CLI tests labeled in TestCLI class |

## Suggestion Applied

match_reference confirmed as string-pair matcher (not cache-iterator). _find_reference owns the cache-iteration loop; uses match_reference for substring comparisons in passes 3-4. Documented in _find_reference docstring.

## Scope Creep Flags

| Flag | Target | Status |
|------|--------|--------|
| A. alt_refs not in v2 cache | Phase 17 follow-up | Added to scope_creep_backlog.md |
| B. recommend_reserve coupling | In-code comment | Comment on _score_decision derivation (evaluate_deal.py:278-282) |
| Floor field absent in v2 cache | v3 candidate | metrics.floor=None for cache hits; populated for on-demand |

## File Inventory

| File | Lines | New/Modified |
|------|-------|-------------|
| scripts/evaluate_deal.py | 724 | New (guide target: ~250; larger due to decomposed helpers and full response builder) |
| tests/test_evaluate_deal.py | 1044 | New |
| REVIEW_phase16.md | ~95 | New |

## Notes

- Script is 724 lines vs guide target of ~250. The delta comes from: full function decomposition into 8 private helpers (plan requirement), comprehensive response builder with v1-superset schema, CLI with argparse (not sys.argv slicing), and inline documentation of the risk band logic. No dead code; every line is reachable.
- "Reserve" signal (risk 20-30%) confirmed still produced by v2 analyze_references.py:106. Both "Reserve" and "Careful" stay in the MAYBE branch condition.
- v1's openpyxl dependency for raw-report fallback eliminated. On-demand analysis reads from CSVs via analyze_references.load_sales_csv().
