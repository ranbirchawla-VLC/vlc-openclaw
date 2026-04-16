# Phase 3 Review
Date: 2026-04-16

## Summary
- Blockers found and fixed: 1 (fixture cycle_ids — see section B)
- Majors found and fixed: 0
- Minors found and fixed: 1 (test isolation — tests leaked real Drive cache)
- Nits: 0 fixed, 0 deferred
- Scope creep flagged: 0

## A. Data correctness — hand-verified financials

| Trade | Gross | Fees | Net | ROI % | Test asserts |
|-------|-------|------|-----|-------|-------------|
| 79830RB NR 2750->3200 | 450 | 149 | 301 | 10.95 | MATCH |
| 91650 NR 1500->1675 | 175 | 149 | 26 | 1.73 | MATCH |
| 79230R NR 2800->3150 | 350 | 149 | 201 | 7.18 | MATCH |
| 28600 RES 4200->4750 | 550 | 199 | 351 | 8.36 | MATCH |
| 79830RB NR 1900->2100 | 200 | 149 | 51 | 2.68 | MATCH |
| A17320 NR 2100->2350 | 250 | 149 | 101 | 4.81 | MATCH |

- Total net profit: **1031.00** (test_total_net_profit asserts exactly)
- Profitable trades: **6 of 6** (test_profitable_count asserts 6)
- Avg ROI: **5.95%** (test_avg_roi asserts within +-0.05)
- Per-trade ROI: all 6 values verified in test_per_trade_roi_values (tolerance < 0.01)
- Per-trade net: all 6 values verified in test_per_trade_net_values (exact match)

## B. Cycle_id round-trip verification — BLOCKER FOUND AND FIXED

The prompt's fixture cycle_ids used weekly numbering. Our cycle_id_from_date uses biweekly per plan Section 4. The fixture was corrected:

| date_closed | Prompt fixture | cycle_id_from_date | Corrected fixture |
|---|---|---|---|
| 2025-10-10 | cycle_2025-41 | cycle_2025-20 | cycle_2025-20 |
| 2025-11-15 | cycle_2025-46 | cycle_2025-23 | cycle_2025-23 |
| 2025-12-01 | cycle_2025-48 | cycle_2025-24 | cycle_2025-24 |
| 2026-01-05 | cycle_2026-01 | cycle_2026-01 | cycle_2026-01 (matched) |
| 2026-02-14 | cycle_2026-06 | cycle_2026-03 | cycle_2026-03 |
| 2026-03-01 | cycle_2026-09 | cycle_2026-04 | cycle_2026-04 |

Resolution: fixture updated to match cycle_id_from_date output. The plan's biweekly definition is authoritative.

## C. CSV schema integrity: PASS
- Header row = LEDGER_COLUMNS exactly. Verified by test_ensure_creates_header_only.
- csv.writer handles all writes (no manual string formatting).
- No trailing whitespace, no BOM.

## D. Ledger write integrity: PASS
- ensure_ledger_exists idempotent: test_ensure_is_idempotent.
- append_ledger_row preserves existing: test_sequential_writes_preserved, test_log_preserves_existing_rows.
- Malformed input exits non-zero: test_log_invalid_account_exits_2, test_log_invalid_price_exits_2, test_log_negative_price_exits_2, test_log_invalid_date_exits_2.
- Parent dir creation: test_append_creates_parent_directory.

## E. OTel span emission: PASS
Four CLI spans: `ledger_log`, `ledger_summary`, `ledger_premium`, `ledger_cycle_rollup`.
- `ledger_log`: brand, reference, account, cycle_id, buy_price, sell_price
- `ledger_summary`: filter.brand, filter.reference, filter.cycle_id
- `ledger_premium`: trade_count, threshold_met
- `ledger_cycle_rollup`: cycle_id
No spans on library internals (read_ledger.py, grailzee_common.py helpers).

## F. CLI contract: PASS
- All stdout output parseable by json.loads: test_summary_stdout_is_valid_json, test_cycle_rollup_stdout_valid_json.
- Errors to stderr: validated in invalid-input tests.
- Exit codes: 0 success, 2 bad input (6 tests verify exit 2).
- --ledger override used by every test.

## G. Plan alignment: PASS
- Schema matches Section 5.2 (7 columns, exact order).
- Fees per 5.4 (NR=149, RES=199).
- Derived fields per 5.3 (platform_fees, net_profit, roi_pct, median_at_trade, max_buy_at_trade, model_correct, premium_vs_median).
- Cycle rollup schema per 5.7.
- CLI contract per 10.4 (log, summary, premium, cycle_rollup).

## H. Not-in-scope verification: PASS
- No historical trades written.
- No ingest_report.py, no analyze_*.py.
- No test touches real Drive paths (all use --ledger/--cache overrides or NO_CACHE sentinel).
- No modifications under skills/grailzee-eval/.

## I. Tripwires: PASS
- CLI tests use subprocess (not mocked).
- Derived fields None when cache absent: test_derived_fields_none_without_cache.
- reference_confidence case-insensitive: test_case_insensitive_brand.
- cycle_rollup empty cycle: structured zeros, not missing keys.
- append_ledger_row creates parent dir: test_append_creates_parent_directory.
- parse_ledger_csv on malformed row: raises ValueError (test_parse_malformed_row_raises).

## Changes made during review
1. **Fixture cycle_ids corrected** (BLOCKER): 5 of 6 cycle_ids updated to match biweekly cycle_id_from_date output.
2. **Test isolation** (MINOR): All no-cache tests now pass explicit NO_CACHE path to prevent leaking real Drive cache data into assertions. Affected test_read_ledger.py (TestRunSummary, TestRunFilters, TestReferenceConfidence, TestCycleRollup classes) and one test in TestRunWithCache.

## Out of scope (NOT fixed, for human decision)
None identified.

## Recommendation
READY FOR HUMAN REVIEW AND COMMIT.
