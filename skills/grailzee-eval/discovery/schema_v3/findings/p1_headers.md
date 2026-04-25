# Phase 1: Header canonicalization map

## Full column inventory

| Position | W1 header | W2 header |
|---|---|---|
| 1 | `Sold at` * | `Sold At` * |
| 2 | `Auction` | `Auction` |
| 3 | `Make` | `Make` |
| 4 | `Model` | `Model` |
| 5 | `Reference Number` | `Reference Number` |
| 6 | `Sold For` | `Sold For` |
| 7 | `Condition` | `Condition` |
| 8 | `Year` | `Year` |
| 9 | `Papers` | `Papers` |
| 10 | `Box` | `Box` |
| 11 | `Dial` * | `Dial Numbers` * |
| 12 | `URL` | `URL` |

Asterisk marks positions where header text differs between W1 and W2.

## Variations detected

- Position 1: `Sold at` (W1) vs `Sold At` (W2) — case-only
- Position 11: `Dial` (W1) vs `Dial Numbers` (W2) — rename

## Proposed canonicalization map

All downstream reads use canonical names. Source-name lookup at ingest.

| Source name (any observed spelling) | Canonical name |
|---|---|
| `Sold at` | `sold_at` |
| `Sold At` | `sold_at` |
| `Auction` | `auction_descriptor` |
| `Make` | `brand` |
| `Model` | `model` |
| `Reference Number` | `reference` |
| `Sold For` | `sold_for` |
| `Condition` | `condition` |
| `Year` | `year` |
| `Papers` | `papers` |
| `Box` | `box` |
| `Dial` | `dial_numerals` |
| `Dial Numbers` | `dial_numerals` |
| `URL` | `url` |

## Planned ingest fields vs column positions

| Canonical | Source name | Observed position (W1=W2) |
|---|---|---|
| `reference` | `Reference Number` | 5 |
| `auction_descriptor` | `Auction` | 2 |
| `brand` | `Make` | 3 |
| `model` | `Model` | 4 |
| `sold_for` | `Sold For` | 6 |
| `condition` | `Condition` | 7 |
| `year` | `Year` | 8 |
| `papers` | `Papers` | 9 |
| `box` | `Box` | 10 |
| `dial_numerals` | `Dial / Dial Numbers` | 11 |
| `sold_at` | `Sold at / Sold At` | 1 |

Asset-class detection runs against `auction_descriptor` (position 2).
Dial-color parse runs against `auction_descriptor` (position 2).
All fields the planned ingest needs are within the first 11 columns.
URL at position 12 is not an ingest field.

**Ordinal-read requirement**: none past column 11. No ordinal reads
past column 9 as specified by the §5 constraint would require dropping
dial_numerals (position 11) and box (position 10). This is a drift
finding against §5; see report Drift section.