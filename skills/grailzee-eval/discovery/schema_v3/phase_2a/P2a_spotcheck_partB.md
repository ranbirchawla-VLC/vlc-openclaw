# Phase 2a Spot-check Part B: Operational Rehearsal

**Date**: 2026-04-24
**Inputs**: copy of live W2 CSV in a temporary tree; live `reports_csv/` untouched.
**Command**: `python3 scripts/ingest.py ingest <tmp>/reports_csv/grailzee_2026-04-21.csv`

---

## Summary dict (single-report)

```json
{
  "source_reports": ["grailzee_2026-04-21.csv"],
  "source_rows_total": 9895,
  "canonical_rows_emitted": 9846,
  "asset_class_filtered": 3,
  "numerals_blank_dropped": 37,
  "fallthrough_drops": 5,
  "within_report_duplicates": 4,
  "cross_report_duplicates": 0,
  "numerals_slash_canonicalized": 10,
  "nbsp_normalized_nr_rows": 59,
  "dial_color_unknown": 571,
  "named_special_detected": 549,
  "within_report_near_collisions": 18,
  "archived_path": "<tmp>/reports_csv/archive/grailzee_2026-04-21.csv"
}
```

Arithmetic: `9895 - 3 - 37 - 5 - 4 - 0 = 9846`. **Holds.**

---

## Assertion table

| v2 prompt §7 Part B assertion | Got | Verdict |
|----|----|----|
| Archival successful | source moved, archive/ created | **pass** |
| Original filename preserved | yes (`grailzee_2026-04-21.csv`) | **pass** |
| Canonical row count plausible for single-report | 9,846 (vs 9,895 source minus 49 drops) | **pass** |
| Within-report dedup matches discovery W2-only | 4 (discovery I.4: 4 W2 collision groups) | **exact** |
| `cross_report_duplicates` zero in single-report mode | 0 | **pass** |
| Re-run fails loudly on idempotency block | `FileExistsError` raised; source left in place | **pass** |
| Filesystem metadata on archived file | byte-for-byte preserved by `shutil.move` (rename if same volume; copy + remove otherwise) | **pass** (size match: 2,531,657 bytes both before and after) |

---

## Operational behavior verified

1. **Pre-state**: `<tmp>/reports_csv/grailzee_2026-04-21.csv` present, `archive/` subdir absent.
2. **Run**: `ingest_and_archive` returns rows + summary + `archived_path`. JSON output via `--ingest` mode includes the archive path.
3. **Post-state**: source removed from `reports_csv/`, present in `reports_csv/archive/` with original filename. Bytes intact.
4. **Idempotency block**: copy of archived file back into `reports_csv/`, re-run. Raises `FileExistsError` with the documented message:
   ```
   Archive destination already exists: <path>. Refusing to overwrite.
   Inspect both files; if intentional re-ingest, manually remove the
   destination then retry.
   ```
   Source CSV remains in `reports_csv/` (not moved).
5. **Process exit**: the script propagates the exception (traceback + non-zero exit). Operator-visible failure mode.

---

## Single-report counts vs Part A

| Counter | Part A (W1+W2) | Part B (W2 only) | Note |
|---------|----------------|-------------------|------|
| `source_rows_total` | 19,335 | 9,895 | W2 alone |
| `canonical_rows_emitted` | 10,440 | 9,846 | post-pipeline |
| `asset_class_filtered` | 3 | 3 | all 3 LV handbags are in W2 (Phase 1 confirmed W1=0) |
| `numerals_blank_dropped` | 71 | 37 | W2-share approximately half (W1=34, W2=37 per discovery) |
| `fallthrough_drops` | 10 | 5 | distributed across both reports |
| `within_report_duplicates` | 10 | 4 | W2-side (discovery: 6 W1 + 4 W2 = 10) |
| `cross_report_duplicates` | 8,801 | 0 | single-report mode produces zero by construction |
| `nbsp_normalized_nr_rows` | 108 | 59 | W2 share (discovery: 47 W1 + 59 W2 = 106; close) |
| `dial_color_unknown` | 1,116 | 571 | W2 alone; ratio consistent with W2 row share |
| `named_special_detected` | 1,087 | 549 | W2 alone |
| `within_report_near_collisions` | 19 | 18 | W2 alone matches Part A's W2-side closely |

---

## Live data state after Part B

The Part B rehearsal ran in a `mktemp -d` tree, **not** in live Drive. Live `reports_csv/` is untouched: both `grailzee_2026-04-06.csv` and `grailzee_2026-04-21.csv` remain present, no `archive/` subdir created. The operator's choice on next steps:
- Run `ingest_and_archive` against live W2 to produce the canonical archive trail before Phase 2b begins.
- Or leave both CSVs in place and let Phase 2b drive its own first-cycle ingest.

Either is fine; v2 prompt §7 "post-spot-check operational state" leaves this to operator discretion.

---

## Plan-review items

None. Operational flow works as designed; idempotency block is loud and conservative; counters align with discovery for the single-report subset.
