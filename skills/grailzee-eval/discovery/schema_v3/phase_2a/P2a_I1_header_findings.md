# P2a I.1: Header Variation Audit
**Date**: 2026-04-24
**Inputs**: live CSVs at `reports_csv/` (post-`f7ecab8`), xlsx at `reports/`.

## Source xlsx headers

| Pos | W1 | W2 | Variance |
|-----|------|------|---------|
| 1 | `Sold at` | `Sold At` | `Sold at` vs `Sold At` |
| 2 | `Auction` | `Auction` | (none) |
| 3 | `Make` | `Make` | (none) |
| 4 | `Model` | `Model` | (none) |
| 5 | `Reference Number` | `Reference Number` | (none) |
| 6 | `Sold For` | `Sold For` | (none) |
| 7 | `Condition` | `Condition` | (none) |
| 8 | `Year` | `Year` | (none) |
| 9 | `Papers` | `Papers` | (none) |
| 10 | `Box` | `Box` | (none) |
| 11 | `Dial` | `Dial Numbers` | `Dial` vs `Dial Numbers` |
| 12 | `URL` | `URL` | (none) |

W1 cols: 12; W2 cols: 12.

## Post-patch CSV headers

W1 CSV (grailzee_2026-04-06.csv): `date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct,model,year,box,dial_numerals_raw,url` (13 cols)

W2 CSV (grailzee_2026-04-21.csv): `date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct,model,year,box,dial_numerals_raw,url` (13 cols)

Identical: True.

## Canonical mapping (CSV column → CanonicalRow field)

Per Decision 1 keying tuple `(reference, dial_numerals, auction_type, dial_color)` plus support fields. CanonicalRow shape proposed for Phase 2a:

| CSV column | CanonicalRow field | Type | Source |
|-----|-----|-----|------|
| `date_sold` | `sold_at` | datetime.date | ISO-parsed via existing normalize_date |
| `make` | `brand` | str | raw |
| `reference` | `reference` | str | post-normalize_reference (.0 stripped) |
| `title` | `auction_descriptor` | str | raw post-NBSP normalization; carries NR prefix and dial-color text |
| `condition` | `condition` | str | raw |
| `papers` | `papers` | str | raw |
| `sold_price` | `sold_for` | float | post-normalize_price |
| `sell_through_pct` | `sell_through_pct` | float | None | raw passthrough |
| `model` | `model` | str | raw |
| `year` | `year` | str | raw passthrough; Phase 2a may parse later |
| `box` | `box` | str | raw |
| `dial_numerals_raw` | `(input to dial_numerals canonicalization, Decisions 5/6)` | str -> Literal['Arabic','Roman','Diamond','No Numerals'] | five-rule cascade in pipeline step 5 |
| `url` | `url` | str | raw |

## Derived fields (computed, not from CSV directly)

- `auction_type: Literal['NR', 'RES']`; derived from `auction_descriptor` via NBSP-tolerant regex `^No Reserve\s*-\s*` (Phase 2 Spec Input 4).
- `dial_color: str`; parsed from `auction_descriptor` text (color anchored to literal `dial`, with bounded compound vocabulary per Decision 3); unparseable → `"unknown"` (Decision 4).
- `named_special: str | None`; populated when a Decision 3 compound (Wimbledon, Tiffany, Panda, etc.) is detected; metadata only in 2a (consumer surfacing in 2c).
- `source_report: str`; CSV filename.
- `source_row_index: int`; row index within source CSV.

## Variance findings

- Two xlsx variances confirmed: position 1 (`Sold at` vs `Sold At`) case-only; position 11 (`Dial` vs `Dial Numbers`) rename. Both already absorbed by `f7ecab8` ingest patch via `SOLD_AT_ALIASES` / `DIAL_ALIASES`.
- Post-patch CSVs are byte-identical in header. Phase 2a reads canonical CSV; xlsx variances are no longer exposed to 2a.

## Scorer-side fields verified preserved

v2 scorer's `analyze_references.load_sales_csv` reads (DictReader by-name): `sold_price, sell_through_pct, condition, papers, reference, make, title`. All present in post-patch CSV. No additional fields the scorer reads but Phase 2a would miss.

## Plan-review items

None. Header surface is fully understood; canonical map is proposable as-is.
