# ingest_report.py Full Column Emission Patch — Spot-check

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Runtime**: Python 3.12.10 (canonical)
**State**: patch applied, all tests passing (960 of 960).

---

## 1. Test suite regression check

Before patch: 957 tests passing (state-doc baseline).
After patch: **960 tests passing**, zero failures, zero errors.

Test delta: **+3 new** (round-trip appended-fields, W2-header-alias, NBSP-passthrough) **+ 1 modified** (exhaustive-shape pin at `test_ingest_report.py:159` updated from 8-name set to 13-name ordered list).

Within the projected +3-to-+8 band.

---

## 2. Live ingest: W1 xlsx → CSV

Command:
```
python3 scripts/ingest_report.py \
  "<Drive>/reports/Grailzee Pro Bi-Weekly Report - April W1.xlsx" \
  --output-dir "<Drive>/reports_csv"
```

Result:
```json
{
  "output_csv": "<Drive>/reports_csv/grailzee_2026-04-06.csv",
  "rows_written": 9440,
  "sheets": {
    "auctions_sold_rows": 9440,
    "top_selling_rows": 1737,
    "sell_through_joined": 6656,
    "sell_through_missing": 2784
  },
  "warnings": [
    "2784 sales had no matching reference in Top Selling Watches; sell_through_pct empty for those rows"
  ]
}
```

No "Unexpected columns ignored" warning; all 12 source headers are now in `KNOWN_AUCTION_COLUMNS`. Row count 9,440 matches xlsx source exactly (Phase 1 confirmed).

CSV file:
- Rows: 9,441 including header (= 9,440 data rows, matches `rows_written`).
- Header: `date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct,model,year,box,dial_numerals_raw,url`. 13 columns, existing 8 in order, 5 appended.
- Sample row 1: `2026-04-06,Jaeger-LeCoultre,176.84.70,2010 Jaeger-LeCoultre Master Compressor ...,Very Good,Yes,6350.0,,Jaeger-LeCoultre Master Compressor,2010.0,Yes,Arabic Numerals,https://grailzee.com/products/...`. All five appended fields populate.

---

## 3. Live ingest: W2 xlsx → CSV

Same command pattern, W2 input.

Result:
```json
{
  "output_csv": "<Drive>/reports_csv/grailzee_2026-04-21.csv",
  "rows_written": 9895,
  "sheets": {
    "auctions_sold_rows": 9895,
    "top_selling_rows": 1790,
    "sell_through_joined": 6968,
    "sell_through_missing": 2927
  },
  "warnings": [
    "2927 sales had no matching reference in Top Selling Watches; sell_through_pct empty for those rows"
  ]
}
```

Row count 9,895 matches xlsx source exactly. No column-variance warnings. W2's `Sold At` (case variant) and `Dial Numbers` (rename) both resolved via the alias helpers.

CSV file:
- Rows: 9,896 including header (= 9,895 data rows).
- Header: identical to W1.
- Sample row 1: `2026-04-21,Omega,232.30.42.21.01.003,...,Very Good,No,2750.0,0.47,Omega Seamaster Planet Ocean,Unknown,No,Arabic Numerals,https://grailzee.com/products/...`. `year="Unknown"` passes through raw per §6 passthrough rule; `dial_numerals_raw="Arabic Numerals"` sourced from the renamed W2 column; sell_through joined at 0.47.

---

## 4. v2 analyzer end-to-end against patched CSV

Command:
```
python3 scripts/run_analysis.py \
  "<Drive>/reports_csv/grailzee_2026-04-21.csv" \
  --output-dir <tmp>/out --cache <tmp>/cache.json --backup <tmp>/backup.json
```

Exit status: success. Cache written.

Cache verification:
- `schema_version`: **2** (unchanged, as required).
- `cycle_id`: `cycle_2026-08` (derived from CSV filename 2026-04-21 per existing `cycle_id_from_csv`).
- `source_report`: `grailzee_2026-04-21.csv`.
- References scored: 680.
- Brands: 24.
- Top-level keys: `['brands', 'breakouts', 'changes', 'cycle_id', 'dj_configs', 'generated_at', 'market_window', 'premium_status', 'references', 'schema_version', 'source_report', 'summary', 'unnamed', 'watchlist']`. Matches the state-doc Section 3 shape.

No field errors. No scorer failures on the patched CSV. Additive columns (`model`, `year`, `box`, `dial_numerals_raw`, `url`) are transparent to the v2 scorer's DictReader by-name consumers.

### Note on scoring coverage

680 refs is below current production's 1,229. This matches the coverage regression Phase 1 surfaced (single-report at `min_sales=3` is smaller than what the historical cache was built on). **Not caused by this patch**; the patch is strictly additive and cannot reduce coverage. Flagged in `PHASE1_REPORT.md §6` as a standing operator decision that follows this patch into Phase 2 work, not a patch-introduced regression.

---

## 5. Spot-check assertions

| Assertion | Status |
|-----------|--------|
| Patched ingest runs against W1 live xlsx | pass |
| Patched ingest runs against W2 live xlsx | pass |
| CSV header = 13 columns, existing 8 first in order, 5 appended | pass (W1 + W2 byte-identical headers) |
| Row count matches xlsx source (W1 9,440; W2 9,895) | pass |
| No "Unexpected columns ignored" warning on live data | pass |
| W2 `Sold At` (case variant) resolves to `date_sold` | pass |
| W2 `Dial Numbers` resolves to `dial_numerals_raw` | pass |
| v2 analyzer end-to-end produces `schema_version: 2` cache | pass |
| No field errors during scoring | pass |
| All 960 tests pass | pass |

---

## 6. No em-dashes

Spot-check report and patched code/tests scanned. None.

---

## 7. Operator unblocked for Phase 2a

Both live CSVs now carry the full source column set. Phase 2a can read from `reports_csv/*.csv` and get `dial_numerals_raw` plus the full `title` field for dial-color derivation plus raw `year`, `box`, `url`, `model`. v2 prompt §4 I.1 inventory + §5 pipeline all have the inputs they need.

---

*End of spot-check findings.*
