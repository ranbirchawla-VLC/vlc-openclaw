# Phase 5 Review
Date: 2026-04-16

## Summary
- Blockers found and fixed: 0
- Majors found and fixed: 0
- Minors found and fixed: 1 (fixture builder string price handling in sum_price aggregation)
- Nits: 0
- Scope creep flagged: 0

## A. Format drift coverage

### Price normalization (normalize_price)
| Input | Expected | Test |
|-------|----------|------|
| 2000 (int) | 2000.0 | test_int |
| 2000.0 (float) | 2000.0 | test_float |
| "$2,000" (string) | 2000.0 | test_string_with_dollar_and_comma |
| "2,000.00" (string) | 2000.0 | test_string_with_comma_decimal |
| None | None | test_none |
| "" | None | test_empty_string |
| "abc" | None | test_non_numeric |

### Reference normalization (normalize_reference)
| Input | Expected | Test |
|-------|----------|------|
| 126300.0 (float) | "126300" | test_float_strips_dot_zero |
| "A17320" (string) | "A17320" | test_string_preserved |
| 126300 (int) | "126300" | test_int |
| None | None | test_none |
| "" | None | test_blank |
| "126300.0" (string) | "126300" | test_string_float |

### Year normalization (normalize_year)
| Input | Expected | Test |
|-------|----------|------|
| 2025.0 (float) | 2025 | test_float |
| 2025 (int) | 2025 | test_int |
| "Unknown" | None | test_unknown |
| "" | None | test_blank |
| None | None | test_none |

### Sell-through normalization (normalize_sell_through)
| Input | Expected | Test |
|-------|----------|------|
| "23%" | 0.23 | test_percent_string |
| 0.28 (float) | 0.28 | test_fraction_float |
| 23 (int) | 0.23 | test_integer_percent |
| None | None | test_none |
| "" | None | test_empty_string |
| 0 | 0.0 | test_zero |
| "100%" | 1.0 | test_one_hundred_percent |

## B. Join correctness: PASS

Verified via TestMinimalValid:
- 3 sales, 2 unique references (79830RB x2, A17320 x1), both in Top Selling Watches.
- sell_through_joined=3, sell_through_missing=0.
- Join is by reference number only (not by model name). The Top Selling fixture builder aggregates by normalized reference, matching the ingest join key.

Verified via TestReferenceUnmatched:
- Sale with reference not in Top Selling Watches -> row kept in CSV, sell_through_pct empty.

## C. Resilience to missing optional data: PASS

TestNoTopSelling: report with no Top Selling Watches sheet succeeds (exit 0), all rows have empty sell_through_pct, warning emitted mentioning "missing".

## D. Strict failure on required data: PASS

| Failure | Test | Behavior |
|---------|------|----------|
| No Auctions Sold sheet | test_no_auctions_sheet_fails | exit non-zero |
| Auctions Sold header only | test_empty_data_fails | exit non-zero |
| Missing required column | test_missing_required_column_fails | exit non-zero |
| File doesn't exist | test_nonexistent_file_fails | exit non-zero |

## E. Row-level tolerance: PASS

TestMissingSoldAt: row with blank Sold at is skipped, remaining rows written, warning with skip count.

## F. Output naming stability: PASS

TestOverwrite:
- Same input twice -> same filename, second run fails without --overwrite.
- With --overwrite, second run succeeds and replaces the file.

## G. CLI contract: PASS

JSON stdout confirmed by json.loads in tests. Errors to stderr. Exit 0 on success/warnings, non-zero on failure. --output-dir and --overwrite work as documented.

## H. OTel: PASS

Single `ingest_report.run` span per invocation. Attributes: input_path, output_path, rows_written, rows_skipped, sell_through_joined, sell_through_missing, warning_count. No inner spans.

## I. Memory behavior: PASS

`read_only=True` on workbook load (line 279). Streaming `ws.iter_rows` for both sheets. No `list(ws.rows)` or `list(ws.values)`. Spot-verified by grep.

## J. Not in scope (absence check): PASS

No analysis logic. No cache writes. No ledger modifications. No real Grailzee reports as fixtures. No v1 modifications.

## K. Tripwires: PASS

- Empty string (not "0" or "None") for missing sell_through_pct: confirmed in TestNoTopSelling.
- .0 suffix stripped from references: test_float_reference_normalized.
- Dates serialized as YYYY-MM-DD only: test_csv_date_format.
- Unicode in titles: test_unicode_in_title.
- Papers capitalization preserved (not normalized): test_papers_capitalization_preserved.

## Changes made during review

1. **_fixture_builders.py:112-118**: Fixed sum_price aggregation to handle string price values (e.g. "2,000") by parsing them before adding. Without this, the TestFormatDrift fixture builder crashed on TypeError.

## Out of scope

None identified.

## Recommendation

READY FOR HUMAN REVIEW AND COMMIT.
