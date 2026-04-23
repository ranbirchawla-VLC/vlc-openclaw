# Part B; W2-only operational rehearsal (2b fixup)

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Source**: live `GrailzeeData/reports_csv/grailzee_2026-04-21.csv` copied into a `mktemp -d` tree; live Drive untouched.
**Script**: `discovery/schema_v3/phase_2b/fixup_part_b.py`
**Raw output**: `fixup_part_b_raw.txt`

---

## Run shape

| Metric | Value |
|--------|-------|
| cycle_id | cycle_2026-08 |
| Unnamed references | 3,690 |
| References in cache | 3,712 |
| DJ configs in cache | 8 |
| Total buckets | 5,026 |
| Cache file size | 5,175,016 bytes |

## Schema and top-level shape

- `schema_version == 3`: PASS
- All 14 expected top-level keys present: PASS

## Summary block

Summary keys emitted: `breakout_count, emerged_count, hot_references, premium_status, total_references, unnamed_count, watchlist_count`.

- Per-signal reference counts (`strong_count`, `normal_count`, `reserve_count`, `caution_count`) absent: PASS
  (Ripped from `_best_signal` removal; cross-bucket signal aggregation is judgment.)

## Per-reference shape (3,712 refs)

- Leaked ripped fields: 0: PASS
- Missing keep-list fields: 0: PASS
- `confidence` key present on every reference: 3,712 / 3,712: PASS (values may be null when no ledger match)
- `trend_signal is None` on single-CSV run: 3,712 / 3,712: PASS (bug 2 fix; was `"No prior data"` string pre-fixup)

## DJ config shape (8 configs)

- Leaked ripped fields: 0: PASS
- `trend_signal` null: 8 / 8: PASS (bug 2 applied consistently to DJ path)
- `confidence` null: 8 / 8: PASS (no per-config ledger join)

## bucket_key audit (5,026 buckets)

- Mixed-case keys: 0: PASS (bug 1 fix verified end-to-end)

## Filesystem effects

- `analysis_cache.json` written at configured path: PASS
- `run_history.json` appended: not explicitly asserted
- Temp tree cleaned up on success: yes

Live `GrailzeeData/` untouched at script exit.

## Verdict

Part B passes cleanly. End-to-end pipeline produces a v3 cache matching the fixup contract: no judgment-creep fields at reference level, no ripped summary counts, trend nulls applied consistently, bucket keys uniformly lowercase.
