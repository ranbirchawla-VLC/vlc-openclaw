# Phase 6: Coverage simulation

Keying tuple: `(Reference Number, dial_numerals, auction_type)`
min_sales_for_scoring (from analyzer_config.json): 3

Total rows scanned: 19335
Handbag-pattern excluded: 3
Scoring-universe rows: 19332
Total buckets: 4692

## Bucket size distribution

| Bucket sale count | Buckets |
|---|---|
| 1 | 560 |
| 2 | 2800 |
| 3-4 | 629 |
| 5-9 | 406 |
| 10-24 | 202 |
| 25-49 | 59 |
| 50-99 | 24 |
| 100+ | 12 |

**Scoring-eligible buckets (>= 3 sales): 1332**

### Comparison to production cycle_2026-06

- Production cache (reference-only keying, full historical window):
  1,229 references scored
- New W1+W2 cache (three-axis keying, W1+W2 window only):
  1332 scoring-eligible buckets
- Discovery-doc headline: 1,330 buckets across 13,190 sales

## Bucket count broken down by axis

- Distinct `reference` values: 3904
- Distinct `(reference, dial_numerals)`: 4092
- Distinct `(reference, auction_type)`: 4500
- Distinct `(reference, dial_numerals, auction_type)`: 4692

## Datejust-family per-bucket medians

### Reference 126300.0

Rows: 307. Blended median: $10,200

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Arabic Numerals | NR | 2 (<min) | $14,800 |
| Arabic Numerals | RES | 2 (<min) | $9,500 |
| Diamond Numerals | RES | 4 | $10,750 |
| No Numerals | NR | 34 | $10,100 |
| No Numerals | RES | 156 | $10,150 |
| Roman Numerals | NR | 9 | $10,200 |
| Roman Numerals | RES | 100 | $10,400 |

### Reference 126334.0

Rows: 291. Blended median: $14,200

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 17 | $15,000 |
| No Numerals | NR | 17 | $13,650 |
| No Numerals | RES | 160 | $14,375 |
| Roman Numerals | NR | 13 | $14,200 |
| Roman Numerals | RES | 84 | $14,000 |

### Reference 126234.0

Rows: 72. Blended median: $11,725

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 9 | $11,000 |
| No Numerals | NR | 6 | $10,000 |
| No Numerals | RES | 30 | $11,714 |
| Roman Numerals | NR | 2 (<min) | $10,201 |
| Roman Numerals | RES | 25 | $12,100 |

### Reference 16013.0

Rows: 65. Blended median: $5,000

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 30 | $5,000 |
| No Numerals | NR | 6 | $4,300 |
| No Numerals | RES | 23 | $5,700 |
| Roman Numerals | RES | 4 | $4,325 |
| _blank | RES | 2 (<min) | $6,700 |

### Reference 1601.0

Rows: 54. Blended median: $4,250

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 7 | $4,000 |
| No Numerals | NR | 6 | $3,100 |
| No Numerals | RES | 39 | $4,400 |
| Roman Numerals | RES | 2 (<min) | $3,700 |

### Reference 6917.0

Rows: 53. Blended median: $3,600

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 13 | $4,000 |
| No Numerals | RES | 30 | $3,525 |
| Roman Numerals | RES | 6 | $2,800 |
| _noise | RES | 4 | $4,195 |

### Reference 126333.0

Rows: 52. Blended median: $15,650

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 8 | $15,950 |
| No Numerals | NR | 3 | $12,302 |
| No Numerals | RES | 21 | $15,000 |
| Roman Numerals | RES | 20 | $16,724 |

### Reference 16233.0

Rows: 42. Blended median: $6,700

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | NR | 2 (<min) | $5,931 |
| Diamond Numerals | RES | 19 | $6,793 |
| No Numerals | RES | 13 | $6,700 |
| Roman Numerals | RES | 8 | $4,875 |

### Reference 69173.0

Rows: 41. Blended median: $5,000

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Arabic Numerals | RES | 2 (<min) | $5,295 |
| Diamond Numerals | NR | 2 (<min) | $3,100 |
| Diamond Numerals | RES | 23 | $5,000 |
| No Numerals | RES | 8 | $5,000 |
| Roman Numerals | RES | 6 | $4,900 |

### Reference 126331.0

Rows: 40. Blended median: $15,600

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 6 | $15,245 |
| No Numerals | NR | 4 | $14,850 |
| No Numerals | RES | 15 | $15,100 |
| Roman Numerals | NR | 2 (<min) | $13,350 |
| Roman Numerals | RES | 13 | $17,200 |
