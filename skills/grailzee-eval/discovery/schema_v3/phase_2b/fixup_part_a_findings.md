# Part A; W1+W2 union logic validation (2b fixup)

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Source**: live `GrailzeeData/reports_csv/grailzee_2026-04-06.csv` + `grailzee_2026-04-21.csv`
**Script**: `discovery/schema_v3/phase_2b/fixup_part_a.py`

---

## Ingest census

| Metric | Value |
|--------|-------|
| Source rows (W1+W2) | 19,335 |
| Canonical rows (union, post-dedup) | 10,440 |

Matches Phase 2a Part A exactly (19,335 / 10,440). Ingest layer unchanged by fixup.

## Bucket census

| Metric | Value | Phase 2b I.4 | Delta |
|--------|-------|--------------|-------|
| Total references | 3,878 | 3,878 | 0 |
| Total buckets | 5,262 | 5,262 | 0 |
| Buckets with volume >= 3 | 722 | 722 | 0 |
| References with >=1 n>=3 bucket | 504 | 504 | 0 |

Zero drift from Phase 2b I.4. The `bucket_key` lowercase change in the fixup does not merge any buckets (source data comes in case-consistent from `ingest.py`).

## Signal distribution (all 5,262 buckets)

| Signal | Count |
|--------|-------|
| Low data | 4,780 |
| Strong | 152 |
| Careful | 134 |
| Normal | 105 |
| Reserve | 89 |
| Pass | 2 |

`scored_buckets` (signal != Low data) = 482. 722 n>=3 minus 482 scored = 240 buckets where n>=3 but `analyze_reference` still sets Low data (VG+-filter downstream behavior inherited from v2; unchanged by fixup).

## Fixup-specific audits

**Mixed-case bucket_keys**: 0 across 5,262 buckets. Bug 1 verified.

**References with missing keep-list or leaked ripped fields (pre-write_cache)**: 0 across 3,878 references. `analyze_buckets.score_all_references` emits exactly `{brand, model, reference, named, buckets}` at the reference level; no `premium_vs_market_*`, `realized_premium_*`, or flat market fields present. Fixup rip verified at the `all_results` layer.

## DJ configs

8 configs emitted: Blue/Oyster (4 buckets), Slate/Oyster (4), White/Oyster (4), Green (2), Black/Oyster (3), Silver (2), Slate/Jubilee (3), Blue/Jubilee (2). All use four-axis bucket construction.

## Verdict

Part A passes cleanly. Bucket construction and reference-level shape match expectations; no regressions from the rip; lowercase fix applied cleanly; no ripped fields leak into the `all_results` layer.
