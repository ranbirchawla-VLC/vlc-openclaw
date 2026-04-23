# ingest_report.py Full Column Emission Patch — Discovery Findings

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2` (no code changes during discovery)
**Runtime**: Python 3.12.10 (canonical, pyenv); openpyxl 3.1.5
**Source files read**:
- `.../GrailzeeData/reports/Grailzee Pro Bi-Weekly Report - April W1.xlsx`
- `.../GrailzeeData/reports/Grailzee Pro Bi-Weekly Report - April W2.xlsx`

---

## 1. xlsx column inventory (primary sheet `Auctions Sold`)

Both workbooks have 12 columns in identical semantic order. Two variances (both catalogued by Phase 1):

| Pos | W1 header | W2 header | Variance | Sample W2 value |
|-----|-----------|-----------|----------|------------------|
| 1 | `Sold at` | `Sold At` | case only | `datetime(2026, 4, 21, 0, 0)` |
| 2 | `Auction` | `Auction` | (none) | `"Omega Seamaster Planet Ocean 600M 42MM Black Dial Steel Bracelet (232.30.42.21.01.003)"` |
| 3 | `Make` | `Make` | (none) | `"Omega"` |
| 4 | `Model` | `Model` | (none) | `"Omega Seamaster Planet Ocean"` |
| 5 | `Reference Number` | `Reference Number` | (none) | `"232.30.42.21.01.003"` (sometimes float) |
| 6 | `Sold For` | `Sold For` | (none) | `2750.0` (float) |
| 7 | `Condition` | `Condition` | (none) | `"Very Good"` |
| 8 | `Year` | `Year` | (none) | `"Unknown"` or `2026.0` (float) |
| 9 | `Papers` | `Papers` | (none) | `"Yes"` / `"No"` |
| 10 | `Box` | `Box` | (none) | `"Yes"` / `"No"` |
| 11 | `Dial` | `Dial Numbers` | **rename** | `"Arabic Numerals"` / `"No Numerals"` / blank |
| 12 | `URL` | `URL` | (none) | `"https://grailzee.com/products/..."` |

Row counts: W1 = 9,440 rows; W2 = 9,895 rows. Matches Phase 1.

Aggregate sheets (both workbooks, identical): `Top Selling Watches`, `Most Sold Makes`, `Most Sold Models`, `Most Searched Keywords`, `Best Selling Days`, `Best Selling Times`, `Sales Auction Type`. Only `Top Selling Watches` is used today (sell-through join).

---

## 2. Current `ingest_report.py` emission inventory

`OUTPUT_COLUMNS` at `skills/grailzee-eval/scripts/ingest_report.py:39-42`:

```
["date_sold", "make", "reference", "title", "condition",
 "papers", "sold_price", "sell_through_pct"]
```

Source → current mapping (from `parse_auctions_sold` at lines 164-223):

| Current CSV column | Source | Notes |
|--------------------|--------|-------|
| `date_sold` | `Sold at` / `Sold At` (xlsx col 1) | ISO normalized via `normalize_date` |
| `make` | `Make` (col 3) | raw `.strip()` |
| `reference` | `Reference Number` (col 5) | normalized via `normalize_reference` |
| `title` | `Auction` (col 2) | raw `.strip()` — this is where NR prefix + descriptor text live |
| `condition` | `Condition` (col 7) | raw `.strip()` |
| `papers` | `Papers` (col 9) | raw `.strip()` |
| `sold_price` | `Sold For` (col 6) | normalized via `normalize_price` |
| `sell_through_pct` | (joined from `Top Selling Watches` aggregate sheet) | not from Auctions Sold |

**Source columns NOT emitted**: `Model` (col 4), `Year` (col 8), `Box` (col 10), `Dial`/`Dial Numbers` (col 11), `URL` (col 12). Five columns stripped.

Note: `Model` was not in the patch prompt's explicit list, but it is also stripped. See §3 proposal for handling.

---

## 3. Delta table and canonical name proposals

Five source columns need to be added. Proposed canonical names follow existing emission conventions (snake_case, raw content where ingest does not canonicalize):

| Source header (W1 / W2) | Currently emitted? | Proposed canonical name | Raw passthrough rule |
|-------------------------|--------------------|-------------------------|-----------------------|
| `Model` | No | `model` | `str(v).strip()` |
| `Year` | No | `year` | raw string; cells contain `"Unknown"`, `2026.0` (float), or blank. Do NOT int-cast at ingest (Phase 2a can decide cast rules); just stringify via `str(v).strip()` and collapse `"Unknown"`/blank to empty string to match existing `normalize_year` semantics |
| `Box` | No | `box` | `str(v).strip()` (values `"Yes"` / `"No"`) |
| `Dial` (W1) / `Dial Numbers` (W2) | No | `dial_numerals_raw` | `str(v).strip()` preserving source text (`"Arabic Numerals"`, `"No Numerals"`, `""`, etc.); Phase 1 confirmed 99.94% semantic identity across the rename, so a single canonical target is correct |
| `URL` | No | `url` | `str(v).strip()` |

### Plan-review flag 1: dial_color question in the patch prompt

The patch prompt §2 suggests source names `Dial` and `Dial Numbers` could map to `dial_color_raw` AND `dial_numerals_raw`, as if they were two distinct source columns. They are not. `Dial` (W1) and `Dial Numbers` (W2) are the same single xlsx column renamed between reports; both carry numerals-bucket content (`"Arabic Numerals"`, `"Roman Numerals"`, etc.), never colors. Phase 1 PHASE1_REPORT.md §3 locks this: one canonical field `dial_numerals`, both source spellings alias to it.

There is no `Dial Color` source column. Dial-color is a parsed field derived from the `Auction` descriptor text in Phase 2a (already being emitted as `title` today). No ingest change needed for dial-color; it lives entirely in 2a.

**Recommendation**: one new column `dial_numerals_raw`, not two. Operator confirms or overrides.

### Plan-review flag 2: `Model` column

Not mentioned in the patch prompt's explicit list ("Dial, Dial Numbers, and possibly others"). It is the fifth stripped column. The scorer does not currently read `model` from CSV — it derives display names from `name_cache.json` instead — but the column is relevant to v3 (four-axis bucket construction in 2b may want per-reference model metadata on the canonical row for human-readable output). Appending it costs nothing and preserves optionality.

**Recommendation**: include `model` in the emission. Operator confirms or overrides.

### Proposed final `OUTPUT_COLUMNS`

```
["date_sold", "make", "reference", "title", "condition",
 "papers", "sold_price", "sell_through_pct",
 "model", "year", "box", "dial_numerals_raw", "url"]
```

Existing 8 preserved in order. Five appended to the right. Total 13 columns.

---

## 4. v2 scorer read-mode verification

Grep surface: all CSV reads across `skills/grailzee-eval/scripts/` that touch report CSVs.

| File | Line | Pattern | Target | Verdict |
|------|------|---------|--------|---------|
| `analyze_references.py` | 325 | `csv.DictReader(f)` | report CSV via `load_sales_csv` | by-name |
| `grailzee_common.py` | 513 | `csv.DictReader(f)` | `trade_ledger.csv` (separate codepath) | by-name |
| `backfill_ledger.py` | 146 | `csv.reader(f)` | a backfill-sample CSV in the same function's I/O pattern | positional read within ledger module scope; not report CSV |
| `backfill_ledger.py` | 374 | `csv.DictReader(f)` | ledger input | by-name |
| `migrate_ledger_v2.py` | 148 | `csv.DictReader(f)` | ledger migration | by-name |

Only one `csv.reader` (positional) in the surface, at `backfill_ledger.py:146`. It reads a backfill-sample CSV, not a Grailzee report CSV. All report-CSV reads are `DictReader` by-name.

`analyze_references.load_sales_csv` at lines 317-344 reads these keys explicitly: `sold_price`, `sell_through_pct`, `condition`, `papers`, `reference`, `make`, `title`. By-name, seven of the current eight emitted columns (`date_sold` is emitted but not read by the scorer). Zero ordinal reads. Additive columns are invisible to this path.

**Standing-principle verdict**: no violations. Additive columns are safe.

---

## 5. Test impact

Grep surface: tests that pin CSV shape.

| Test file | Line | Pattern | Impact |
|-----------|------|---------|--------|
| `test_ingest_report.py` | 159 | `assert set(reader.fieldnames) == {8 names}` | **breaks** — exhaustive set pin must update to the new 13-name set (or relax to `>=`) |
| `test_build_shortlist.py` | 67 | `return reader.fieldnames, list(reader)` | no assertion on the fieldnames shape at this line; read-only |
| `test_evaluate_deal.py` | 138-364 | hardcoded 8-column fixture literal | no impact — fixture generator produces 8-column CSVs; DictReader consumers in the scorer read by name and do not care about extra columns; but the fixture itself is hardcoded 8-column and does not need changing since it is used only to feed the scorer (which does not read the new fields) |
| `test_run_analysis.py` | 437, 505 | 8-column fixture literal + `row["sold_price"]` | same as above, no impact |
| `test_analyze_watchlist.py` | 255 | 8-column fixture literal | same as above, no impact |
| `tests/fixtures/grailzee_2026-*.csv` (3 files) | header | 8-column fixture files | no impact — DictReader is tolerant to missing columns in consumer reads. Leaving fixtures at 8 columns means those tests also incidentally verify the scorer does not break on "legacy" CSVs without the new columns. Keep as-is |

**Impact**: exactly one test assertion to update (`test_ingest_report.py:159`). The existing 8-column fixtures in `tests/fixtures/` stay valid because downstream scorer reads by-name and ignores unknown columns.

---

## 6. Source data quirks observed

Raw passthrough rule says no transformation at this layer, only column naming. Quirks the ingest patch must preserve without interpretation:

- **`Year` column**: mixed types. Sometimes `float` (`2026.0`), sometimes `"Unknown"` (string), sometimes blank. The existing `normalize_year` at `ingest_report.py:86-102` already handles these by returning `None` for non-numeric. Since the patch is raw passthrough, do NOT call `normalize_year`. Stringify via `str(v).strip()` and emit `""` for blank/None. Preserve `"Unknown"` as text. Phase 2a can parse.
- **`Reference Number` column**: mixed `float`/`str`. `normalize_reference` at lines 70-83 handles this (strips `.0` suffix). Apply existing `normalize_reference` to stay consistent with what already lands in `reference`; this is not Phase-2a-only transform because `reference` itself uses it today.
- **`Dial`/`Dial Numbers` column**: 2 blank cells per 200 rows sampled in W2. Carry NBSP and typo noise per Phase 1. Raw passthrough: `str(v).strip()` if not None, else `""`.
- **`URL` column**: contains full product URL. No special handling.
- **`Box` column**: always `"Yes"` or `"No"` in live data (Phase 1 did not flag variance). `str(v).strip()`.
- **`Model` column**: free text, `str(v).strip()`.

NBSP characters in the `Auction` field (the 109 NR-prefix rows from Phase 1) pass through already today because `title` uses `str(v).strip()` without whitespace normalization. Consistent: the patch preserves NBSP in all new string columns too. Phase 2a handles NBSP normalization as documented in its pipeline step 3.

---

## 7. Zero kill-condition triggers

Per prompt §Kill conditions:

- v2 scorer ordinal reads past column 9 — **not observed** (all by-name).
- Significant structural variance between W1 and W2 — **not observed** (12-col identical semantics, 2 cosmetic header-text variances already handled by canonicalization).
- Test delta exceeds +8 — projected below (see §8).

Discovery passes. Ready for operator review.

---

## 8. Projected implementation scope

- `skills/grailzee-eval/scripts/ingest_report.py`:
  - Extend `OUTPUT_COLUMNS` to 13 names (5 appended).
  - Extend `parse_auctions_sold` to extract `Model`, `Year`, `Box`, `Dial`/`Dial Numbers` (both spellings supported via `col_map.get("Dial") or col_map.get("Dial Numbers")`), `URL`. Raw passthrough semantics per §6.
  - Extend writer at lines 358-371 to emit the new 5 fields per row.
  - Remove `extra` column-variance warning path at lines 175-179 (currently emits "Unexpected columns ignored" if new headers appear; now they are expected).
- `skills/grailzee-eval/tests/test_ingest_report.py`:
  - Update line 159-162 exhaustive-shape pin to the new 13-name set.
  - Add one round-trip test: seeded 12-column xlsx fragment → 13-column CSV with all new fields populated.
  - Add one edge-case test: xlsx with `Dial` header (W1 style) and xlsx with `Dial Numbers` header (W2 style) both produce a CSV with `dial_numerals_raw` populated.
  - Add one NBSP-preservation test: source cell with `\xa0` in `Auction` or `dial_numerals_raw` passes through verbatim.

Projected test delta: **+3 tests** (+1 round-trip, +1 header-alias, +1 NBSP-passthrough) + 1 modified (the exhaustive pin). Within the +3-to-+8 band.

Projected line delta in `ingest_report.py`: approximately +25 net (5 OUTPUT_COLUMNS entries, 5 get() extraction calls, 5 writer dict entries, +1 header-alias handler for Dial variance, a few comment lines; minus the removed extra-column-variance warning).

---

## Ready for plan-review

Two items need operator confirmation before implementation:

1. **`dial_numerals_raw` (one column, not two)**: confirm the patch prompt's mention of `dial_color_raw` was an artifact and a single `dial_numerals_raw` canonical is correct.
2. **`model` inclusion**: confirm adding `model` to emission (optional but zero-cost; patch prompt's "possibly others" likely intended to cover it).

No other open items. Standing by for plan-review approval.

---

*End of discovery findings.*
