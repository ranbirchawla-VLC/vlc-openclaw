# Phase 3: Dial numerals parsing

## W1 (column: `Dial`)

Total rows: 9440
Distinct raw values: 19

### Raw value distribution (top 25)

| Count | Raw value |
|---|---|
| 6247 | `No Numerals` |
| 2033 | `Arabic Numerals` |
| 871 | `Roman Numerals` |
| 211 | `Diamond Numerals` |
| 34 | `(blank)` |
| 16 | `Arabic Numbers` |
| 6 | `Arabic\/Roman Numerals` |
| 3 | `No numerals` |
| 3 | `No Numbers` |
| 3 | `Diamonds Numerals` |
| 3 | `Roman\/Arabic Numerals` |
| 2 | `Sapphire Numerals` |
| 2 | `Arabic numerals` |
| 1 | `Plexiglass` |
| 1 | `Diamond\/Sapphire Numerals` |
| 1 | `Abaric Numerals` |
| 1 | `Other` |
| 1 | `Diamond` |
| 1 | `Gemstone Numerals` |

### After canonicalization

| Count | Pct | Canonical bucket |
|---|---|---|
| 6250 | 66.21% | `No Numerals` |
| 2051 | 21.73% | `Arabic Numerals` |
| 871 | 9.23% | `Roman Numerals` |
| 216 | 2.29% | `Diamond Numerals` |
| 34 | 0.36% | `_blank` |
| 9 | 0.10% | `_noise` |
| 9 | 0.10% | `_slash_combined` |

### Noise tail (6 distinct values)

| Count | Raw value |
|---|---|
| 3 | `No Numbers` |
| 2 | `Sapphire Numerals` |
| 1 | `Plexiglass` |
| 1 | `Abaric Numerals` |
| 1 | `Other` |
| 1 | `Gemstone Numerals` |

## W2 (column: `Dial Numbers`)

Total rows: 9895
Distinct raw values: 20

### Raw value distribution (top 25)

| Count | Raw value |
|---|---|
| 6515 | `No Numerals` |
| 2165 | `Arabic Numerals` |
| 894 | `Roman Numerals` |
| 232 | `Diamond Numerals` |
| 40 | `(blank)` |
| 17 | `Arabic Numbers` |
| 7 | `No Numbers` |
| 6 | `Arabic\/Roman Numerals` |
| 3 | `No numerals` |
| 3 | `Diamonds Numerals` |
| 3 | `Roman\/Arabic Numerals` |
| 2 | `Sapphire Numerals` |
| 1 | `No Numeral` |
| 1 | `Plexiglass` |
| 1 | `Diamond\/Sapphire Numerals` |
| 1 | `Abaric Numerals` |
| 1 | `Other` |
| 1 | `Arabic numerals` |
| 1 | `Diamond` |
| 1 | `Gemstone Numerals` |

### After canonicalization

| Count | Pct | Canonical bucket |
|---|---|---|
| 6519 | 65.88% | `No Numerals` |
| 2183 | 22.06% | `Arabic Numerals` |
| 894 | 9.03% | `Roman Numerals` |
| 237 | 2.40% | `Diamond Numerals` |
| 40 | 0.40% | `_blank` |
| 13 | 0.13% | `_noise` |
| 9 | 0.09% | `_slash_combined` |

### Noise tail (6 distinct values)

| Count | Raw value |
|---|---|
| 7 | `No Numbers` |
| 2 | `Sapphire Numerals` |
| 1 | `Plexiglass` |
| 1 | `Abaric Numerals` |
| 1 | `Other` |
| 1 | `Gemstone Numerals` |

## Canonicalization rules applied

1. Lowercase, strip whitespace, strip trailing `.,;`.
2. Exact match first against the four canonical singulars and
   common plural/singular variants.
3. Slash-combined: split on `/`, canonicalize each part; if all
   parts map to the same bucket, assign; otherwise mark
   `_slash_combined` for plan-review.
4. Keyword fallback: substring match on `arabic`, `roman`,
   `diamond`, `no numeral`.
5. Everything else → `_noise`.

## W1-vs-W2 value-identity check

For rows that match on both `Reference Number` AND `Sold at`/`Sold At`
AND `Sold For`, compare the W1 `Dial` value to the W2 `Dial Numbers` value.
(Rows overlap only if the same sale appears in both reports; the two
reports cover different bi-weekly windows, so overlap is expected to be
small or zero.)

- Overlap rows (match on ref + sold_at + sold_for): 8843
- Identical dial value: 8838
- Divergent dial value: 5

Sample divergences:
- `(116334.0, datetime.datetime(2026, 3, 6, 0, 0), 10000.0)`: W1=`No Numerals` vs W2=`Roman Numerals`
- `(126334.0, datetime.datetime(2026, 1, 28, 0, 0), 14000.0)`: W1=`No Numerals` vs W2=`Roman Numerals`
- `(126300.0, datetime.datetime(2026, 1, 21, 0, 0), 11000.0)`: W1=`No Numerals` vs W2=`Roman Numerals`
- `(126334.0, datetime.datetime(2026, 1, 14, 0, 0), 14000.0)`: W1=`Roman Numerals` vs W2=`No Numerals`
- `(126300.0, datetime.datetime(2025, 11, 19, 0, 0), 10100.0)`: W1=`No Numerals` vs W2=`Roman Numerals`