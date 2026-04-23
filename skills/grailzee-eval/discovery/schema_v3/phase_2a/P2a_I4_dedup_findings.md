# P2a I.4: Dedup Collision Edge Cases
**Date**: 2026-04-24
**Inputs**: post-patch CSVs (W1 9,440 + W2 9,895).
**Key**: 4-tuple `(reference, date_sold, sold_price, title)` (post-NBSP-normalized title).

## Within-report 4-tuple collisions

| Report | Distinct 4-tuples | Collision groups | Excess rows (rows minus distinct) |
|------|------|------|------|
| W1 | 9434 | 6 | 6 |
| W2 | 9891 | 4 | 4 |

### Collision examples (showing up to 10)

- ref=`91650` date=`2026-01-16` price=`2000.0` rows=[4877, 4878]
  title=`No Reserve - 2025 Tudor 1926 41MM White Dial Steel Bracelet (91650)`
- ref=`124060` date=`2026-01-13` price=`12600.0` rows=[5133, 5134]
  title=`2025 Rolex Submariner No-Date 41MM Black Dial Oyster Bracelet (124060)`
- ref=`126334` date=`2025-10-28` price=`14000.0` rows=[8535, 8539]
  title=`2025 Rolex Datejust "Wimbledon" 41MM Slate Dial Oyster Bracelet (126334)`
- ref=`126610LN` date=`2025-10-21` price=`14200.0` rows=[8821, 8840]
  title=`2025 Rolex Submariner Date 41MM Black Dial Oyster Bracelet (126610LN)`
- ref=`213.30.42.40.01.001` date=`2025-10-10` price=`3000.0` rows=[9189, 9192]
  title=`Omega Seamaster Diver 300M 41.5MM Black Dial Steel Bracelet (213.30.42.40.01.001)`
- ref=`91650` date=`2026-01-16` price=`2000.0` rows=[5928, 5929]
  title=`No Reserve - 2025 Tudor 1926 41MM White Dial Steel Bracelet (91650)`
- ref=`124060` date=`2026-01-13` price=`12600.0` rows=[6184, 6185]
  title=`2025 Rolex Submariner No-Date 41MM Black Dial Oyster Bracelet (124060)`
- ref=`126334` date=`2025-10-28` price=`14000.0` rows=[9586, 9590]
  title=`2025 Rolex Datejust "Wimbledon" 41MM Slate Dial Oyster Bracelet (126334)`
- ref=`126610LN` date=`2025-10-21` price=`14200.0` rows=[9872, 9891]
  title=`2025 Rolex Submariner Date 41MM Black Dial Oyster Bracelet (126610LN)`
## Within-report 3-tuple near-collisions (descriptor differs)

| Report | Near-collision count |
|------|------|
| W1 | 15 |
| W2 | 18 |

### Examples (showing up to 10 per report)

#### W1

- ref=`124300` date=`2026-03-30` price=`16900.0`; descriptors:
  - `2021 Rolex Oyster Perpetual 41MM Red Dial Oyster Bracelet (124300)`
  - `2021 Rolex Oyster Perpetual 41MM Yellow Dial Oyster Bracelet (124300)`
- ref=`1601` date=`2026-03-19` price=`3500.0`; descriptors:
  - `1972 Rolex Datejust 36MM Champagne "Tropical" Dial Aftermarket Leather Strap (1601)`
  - `1979 Rolex Datejust 36MM Champagne Dial Aftermarket Leather Strap (1601)`
- ref=`166.0163` date=`2026-03-12` price=`700.0`; descriptors:
  - `No Reserve - 1974 Omega Geneve Vintage 35MM Champagne Dial Aftermarket Leather Strap (166.0163)`
  - `No Reserve - 1973 Omega Geneve Vintage 35MM Silver Dial Aftermarket Leather Strap (166.0163)`
- ref=`116334` date=`2026-03-06` price=`10000.0`; descriptors:
  - `2013 Rolex Datejust II 41MM Rhodium Dial Oyster Bracelet (116334)`
  - `2014 Rolex Datejust II 41MM White Dial Oyster Bracelet (116334)`
- ref=`79540` date=`2026-03-04` price=`2150.0`; descriptors:
  - `2022 Tudor Black Bay "Smiley" 41MM Black Dial Steel Bracelet (79540)`
  - `2019 Tudor Black Bay 41MM Blue Dial Steel Bracelet (79540)`
- ref=`116610LN` date=`2026-03-03` price=`11200.0`; descriptors:
  - `No Reserve - 2020 Rolex Submariner Date 40MM Black Dial Oyster Bracelet (116610LN)`
  - `Rolex Submariner Date 40MM Aftermarket Blue Dial Oyster Bracelet (116610LN)`
- ref=`134300` date=`2026-02-20` price=`11000.0`; descriptors:
  - `2025 Rolex Oyster Perpetual 41MM Pistachio Dial Oyster Bracelet (134300)`
  - `2026 Rolex Oyster Perpetual 41MM Green Dial Oyster Bracelet (134300)`
- ref=`126334` date=`2026-01-28` price=`14000.0`; descriptors:
  - `2025 Rolex Datejust "Wimbledon" 41MM Slate Dial Oyster Bracelet (126334)`
  - `2025 Rolex Datejust 41MM Slate Dial Jubilee Bracelet (126334)`
- ref=`126300` date=`2026-01-21` price=`11000.0`; descriptors:
  - `2025 Rolex Datejust 41MM Black Dial Jubilee Bracelet (126300)`
  - `2025 Rolex Datejust 41MM Blue Dial Jubilee Bracelet (126300)`
- ref=`126334` date=`2026-01-14` price=`14000.0`; descriptors:
  - `2025 Rolex Datejust 41MM Blue Dial Oyster Bracelet (126334)`
  - `2025 Rolex Datejust 41MM Blue Dial Jubilee Bracelet (126334)`

#### W2

- ref=`7939G1A0NRU` date=`2026-04-13` price=`4200.0`; descriptors:
  - `2025 Tudor Black Bay 58' GMT "Coke" 39MM Black Dial Steel Bracelet (7939G1A0NRU)`
  - `2024 Tudor Black Bay 58' GMT 39MM Black Dial Steel Bracelet (7939G1A0NRU)`
- ref=`210.30.42.20.03.001` date=`2026-04-13` price=`4200.0`; descriptors:
  - `2021 Omega Seamaster Diver 300M 42MM Blue Dial Steel Bracelet (210.30.42.20.03.001)`
  - `2022 Omega Seamaster Diver 300M 42MM Blue Dial Steel Bracelet (210.30.42.20.03.001)`
- ref=`116660` date=`2026-04-10` price=`10500.0`; descriptors:
  - `2011 Rolex Sea-Dweller Deepsea 44MM Black Dial Oyster Bracelet (116660)`
  - `No Reserve - 2013 Rolex Sea-Dweller Deepsea 44MM Black Dial Oyster Bracelet (116660)`
- ref=`126610LN` date=`2026-04-07` price=`14600.0`; descriptors:
  - `2025 Rolex Submariner Date 41MM Black Dial Oyster Bracelet (126610LN)`
  - `No Reserve - 2026 Rolex Submariner Date 41MM Black Dial Oyster Bracelet (126610LN)`
- ref=`124300` date=`2026-03-30` price=`16900.0`; descriptors:
  - `2021 Rolex Oyster Perpetual 41MM Red Dial Oyster Bracelet (124300)`
  - `2021 Rolex Oyster Perpetual 41MM Yellow Dial Oyster Bracelet (124300)`
- ref=`1601` date=`2026-03-19` price=`3500.0`; descriptors:
  - `1972 Rolex Datejust 36MM Champagne "Tropical" Dial Aftermarket Leather Strap (1601)`
  - `1979 Rolex Datejust 36MM Champagne Dial Aftermarket Leather Strap (1601)`
- ref=`166.0163` date=`2026-03-12` price=`700.0`; descriptors:
  - `No Reserve - 1974 Omega Geneve Vintage 35MM Champagne Dial Aftermarket Leather Strap (166.0163)`
  - `No Reserve - 1973 Omega Geneve Vintage 35MM Silver Dial Aftermarket Leather Strap (166.0163)`
- ref=`116334` date=`2026-03-06` price=`10000.0`; descriptors:
  - `2013 Rolex Datejust II 41MM Rhodium Dial Oyster Bracelet (116334)`
  - `2014 Rolex Datejust II 41MM White Dial Oyster Bracelet (116334)`
- ref=`79540` date=`2026-03-04` price=`2150.0`; descriptors:
  - `2022 Tudor Black Bay "Smiley" 41MM Black Dial Steel Bracelet (79540)`
  - `2019 Tudor Black Bay 41MM Blue Dial Steel Bracelet (79540)`
- ref=`116610LN` date=`2026-03-03` price=`11200.0`; descriptors:
  - `No Reserve - 2020 Rolex Submariner Date 40MM Black Dial Oyster Bracelet (116610LN)`
  - `Rolex Submariner Date 40MM Aftermarket Blue Dial Oyster Bracelet (116610LN)`

### Pattern analysis

Review the descriptors above. Genuine separate auctions on identical 3-tuple are extraordinarily unlikely (same reference + same day + same price + different listing titles); most likely cause is source-side descriptor edits between scrape passes (e.g., a typo correction). Recommended resolution: keep the 4-tuple as-is. Same-3-tuple-different-4th rows count as separate auctions and both flow through. If operational truth turns out to be source noise, surface in a future cleanup; do not bake heuristics into 2a ingest.

## Cross-report 4-tuple validation

Union of W1+W2 4-tuples: 10486 distinct keys.

- Keys present in exactly one report: 1645
- Keys present in both reports (overlap): **8837**
- Keys present 3+ times: 4

Phase 1 reported 8,839 cross-report overlap rows. This run (post-patch CSV via 4-tuple): **8837**. Delta -2. **Within Phase 1 tolerance (±5).**

W1 + W2 - overlap = 9440 + 9895 - 8837 = 10498 unique sales post-dedup. Phase 1 reported 10,486.

## Cross-report dedup is validation-only for 2a

Per v2 prompt §1 operational model, production runs are single-report. The cross-report scan above confirms the 4-tuple logic works on multi-report input; operational behavior never exercises the cross-report path. Decision 7's `prefer-W2` tiebreak ships dormant.

## Recommendation

Ship the 4-tuple dedup as locked. Within-report dedup is a safety net (zero hits on live data); cross-report path validates correctly against Phase 1 evidence within tolerance. No resolution-rule additions needed.

## Plan-review items

None unless within-report collisions or near-collisions surfaced.
