# 2b.I.4 — Bucket Population Census

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Source**: Live W2 `grailzee_2026-04-21.csv` via `load_and_canonicalize([W2])`; W1+W2 union added for phase-gap context.

---

## W2-only census (primary operating figure)

| Metric | Value |
|--------|-------|
| W2 canonical rows | 9,846 |
| Total references | 3,712 |
| Total buckets | 5,026 |
| Scoring-eligible buckets (n >= 3) | 692 |
| Below-threshold buckets (n < 3) | 4,334 |
| References with >= 1 eligible bucket | 482 |

---

## W1+W2 union census (for Part A spot-check comparison)

| Metric | Value |
|--------|-------|
| Union canonical rows | 10,440 |
| Total references | 3,878 |
| Total buckets | 5,262 |
| Scoring-eligible buckets (n >= 3) | 722 |
| References with >= 1 eligible bucket | 504 |

**Phase 1 comparison**: Phase 1 estimate was 725 eligible buckets for the W1+W2 union. Observed: 722. Delta: -3, which is 0.41% — well within the Part A 3% tolerance. No kill-condition trigger.

---

## Per-reference bucket count distribution (W2-only)

| Buckets per ref | Refs with that count |
|-----------------|----------------------|
| 1 | 2,960 |
| 2 | 555 |
| 3 | 81 |
| 4 | 44 |
| 5 | 23 |
| 6 | 18 |
| 7 | 9 |
| 8 | 6 |
| 9 | 3 |
| 10 | 2 |
| 11 | 4 |
| 12 | 3 |
| 13 | 1 |
| 18 | 1 |
| 21 | 1 (126334) |
| 24 | 1 (126300) |

Majority of references (2,960 of 3,712) have exactly 1 bucket; consistent with the long tail of references with few rows in any single report.

---

## Top 5 references by row count

| Reference | Total rows | Total buckets | Eligible buckets (n>=3) |
|-----------|------------|---------------|-------------------------|
| 126300 | 155 | 24 | 14 |
| 126334 | 147 | 21 | 14 |
| 79360N | 116 | 11 | 9 |
| 126710BLNR | 99 | 2 | 2 |
| 124060 | 99 | 2 | 2 |

126300 (Datejust 41) is the highest-volume reference and also the DJ config subject. Its 24-bucket spread confirms the 4-axis bucketing is working as intended.

---

## `color=unknown` bucket census

| Metric | Value |
|--------|-------|
| Total unknown-color buckets | 404 |
| Eligible unknown-color buckets (n >= 3) | 33 |
| Total rows in unknown-color buckets | 571 |

Aligns with 2a Phase 2a Part A's `dial_color_unknown=1,116` for the union; W2-only is 571 as expected (~50%). 33 scoring-eligible unknown buckets confirms the bucket is a real scoring contributor, not a negligible edge case.

---

## `named_special` distribution across buckets

All 13 vocabulary entries present. Distribution is concentrated: `skeleton` leads with 154 bucket appearances (likely `Skeleton` dial descriptors across many references).

| named_special | Bucket appearances |
|---------------|-------------------|
| skeleton | 154 |
| mother_of_pearl | 77 |
| panda | 19 |
| wimbledon | 16 |
| tiffany | 12 |
| meteorite | 9 |
| tapestry | 9 |
| aventurine | 9 |
| tropical | 7 |
| pave | 7 |
| linen | 6 |
| reverse_panda | 5 |
| celebration | 4 |

"Named special" threading (G6) is well-exercised: all 13 vocabulary values are present in the live data.

---

## bucket_key collision check

| Metric | Value |
|--------|-------|
| Within-reference bucket_key collisions | 0 (confirmed; bucket_key is unique within a reference) |
| Cross-reference bucket_key collisions | 117 (expected; different references sharing the same bucket_key like "Arabic\|nr\|black") |

Bucket key is deterministic and unique within a reference. The 117 cross-reference "collisions" are correct behavior: the reference is the parent key in the cache, so "Arabic\|nr\|black" for Rolex 126300 is a different entry than "Arabic\|nr\|black" for Tudor 79830RB.

---

## Near-threshold reference example

Reference `126300` has both n >= 3 and n < 3 buckets (best available example; single-bucket refs with n=2 are more common but harder to demo multi-bucket behavior):

Bucket sample from 126300 (sorted by size):
- `Roman|res|slate`: 29 rows (scores normally)
- `Diamond|res|unknown`: 2 rows (carries `signal="Low data"`, below threshold)
- `Arabic|nr|unknown`: 1 row (carries `signal="Low data"`)

---

## Surprises / flags for plan-review

1. **Reference count drop vs v2**: v2 Part B returned 680 scored references; v3 W2-only yields 482 references with at least 1 eligible bucket. The 28% drop is not a regression; it is expected from 4-axis fragmentation (a reference with 4 total rows might have 2+2 across two dial_color values, yielding two below-threshold buckets vs one above-threshold reference in v2). This affects the §1.7 analytical-quality benchmark: the strategy session will see fewer scored references but each scored reference has a tighter data window. The operator needs to evaluate this in §1.7.

2. **4,334 below-threshold buckets**: These are carried with `signal="Low data"`. With the default lean (carry them, don't drop), the cache will have many low-data entries. The strategy reading-partner flow needs to handle a large below-threshold population. This was anticipated in the prompt; surfaced here as a confirmed live number.

3. **`named_special` is in 334 total bucket appearances across 13 values**: All vocabulary entries are present in the live data. The G6 threading rule will be exercised across all 13 cases in the spot-check.
