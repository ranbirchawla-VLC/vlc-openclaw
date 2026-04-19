# Phase 4 Review
Date: 2026-04-16

## Summary
- Blockers found and fixed: 0
- Majors found and fixed: 0
- Minors found and fixed: 0
- Nits: 0
- Scope creep flagged: 0

## A. Validation coverage

| Rule | Rejection condition | Fixture | Test |
|------|-------------------|---------|------|
| Date format | Not YYYY-MM-DD | backfill_sample_invalid_dates.csv (row 1) | test_malformed_date_rejected |
| Future date | date > today | backfill_sample_invalid_dates.csv (row 2) | test_future_date_rejected |
| Non-date string | Unparseable | backfill_sample_invalid_dates.csv (row 3) | test_non_date_string_rejected |
| Invalid account | Not NR/RES after upper | backfill_sample_invalid_schema.csv (rows 1-2) | test_invalid_account_rejected |
| Lowercase NR accepted | 'nr' -> 'NR' valid | backfill_sample_invalid_schema.csv (row 3) | test_lowercase_nr_accepted |
| Empty brand | Whitespace-only | backfill_sample_invalid_schema.csv (row 4) | test_empty_brand_rejected |
| Reference with comma | CSV corruption | backfill_sample_invalid_schema.csv (row 5) | test_reference_with_comma_rejected |
| Negative price | buy_price < 0 | backfill_sample_invalid_prices.csv (row 1) | test_negative_buy_rejected |
| Zero price | sell_price = 0 | backfill_sample_invalid_prices.csv (row 2) | test_zero_sell_rejected |
| Non-numeric price | 'abc' | backfill_sample_invalid_prices.csv (row 3) | test_non_numeric_rejected |
| Dollar sign in price | '$2750' accepted | backfill_sample_invalid_prices.csv (row 4) | test_dollar_sign_accepted |
| Mismatched cycle_id | Doesn't match computed | backfill_sample_invalid_cycle.csv | test_mismatched_cycle_rejected |
| Header mismatch | Wrong columns | Dynamic fixture | test_wrong_header_rejected |
| Losing trade | sell < buy (warning) | backfill_sample_with_warnings.csv (row 1) | test_losing_trade_warning |
| High-value trade | buy > 50000 (warning) | backfill_sample_with_warnings.csv (row 2) | test_high_value_warning |

Every documented rejection rule has a dedicated fixture row and test.

## B. Atomicity of commit: PASS

Tested explicitly:
- `test_commit_invalid_writes_zero_rows`: 3-row input with all bad dates; ledger empty after.
- `test_commit_mixed_validity_writes_zero`: 2 valid + 1 bad date; ledger empty after. Proves validate-all-before-write approach works.

Implementation: `validate_all()` runs on every row before any call to `append_ledger_row()`. If `errors` is non-empty, commit returns exit 2 without writing.

## C. Cycle_id integrity: PASS

- `test_commit_auto_fills_cycle_id`: blank cycle_id in input -> populated in committed rows.
- `test_mismatched_cycle_rejected`: pre-populated wrong cycle_id -> rejected.
- `test_preview_cycle_ids_auto_filled`: preview shows auto-filled cycles.

## D. Aggregates correctness: PASS

Hand-computed from backfill_sample_valid.csv (same data as Phase 3 fixture):
- total_buy=15250, total_sell=17225, total_fees=944, total_net=1031
- avg_roi=5.95, profitable=6, losing=0
- accounts: NR=5, RES=1; brands: Tudor=5, Breitling=1

test_preview_aggregates_correct asserts all values against these constants. No circularity; constants are defined as hand-computed literals in the test file.

## E. Warning vs rejection distinction: PASS

- `test_warnings_exit_0`: file with warnings-only exits 0.
- All invalid fixtures exit 2.
- Warning presence confirmed: test_losing_trade_warning, test_high_value_warning.

## F. CLI contract: PASS

- JSON stdout: test_valid_output_is_json, test_commit_stdout_is_valid_json.
- Errors to stderr: commit failures write to stderr (tested via returncode).
- Exit codes: 0 clean, 0 warnings-only, 2 validation failures.
- --ledger override: used in every commit test.
- Header-only input: test_template_header_only_exits_0, test_preview_header_only_exits_0.

## G. OTel span emission: PASS

| Span name | Attributes |
|-----------|------------|
| `backfill_ledger.validate` | input_path, rows_total, rows_valid, rows_rejected, warning_count |
| `backfill_ledger.preview` | input_path, rows_total, rows_valid, rows_rejected, warning_count, total_net_profit |
| `backfill_ledger.commit` | input_path, ledger_path, ledger_rows_before, ledger_rows_after |

No spans on per-row validators.

## H. Not in scope (verified absent): PASS

- No historical data written to production Drive ledger.
- No modifications under skills/grailzee-eval/.
- No cache reads/writes in backfill_ledger.py.
- backfill_ledger.py is a separate tool, not a subcommand of ledger_manager.py.

## I. Tripwires: PASS

- Comment lines between data rows: test_comments_between_data_rows.
- UTF-8 BOM: test_utf8_bom_handled.
- Trailing blank lines: test_trailing_blank_lines_ignored.
- Unicode reference: test_unicode_reference_accepted.
- No unnecessary memory holding (streaming via csv.DictReader; rows list is bounded by input size).

## Recommendation

READY FOR HUMAN REVIEW AND COMMIT.
