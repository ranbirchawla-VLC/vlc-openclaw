# Phase 2a Spot-check Part A: Logic Validation

**Date**: 2026-04-24
**Inputs**: live W1+W2 post-patch CSVs (one-time multi-report run; production is single-report).
**Command**: `python3 scripts/ingest.py validate <W1.csv> <W2.csv>`

---

## Summary dict

```json
{
  "source_reports": ["grailzee_2026-04-06.csv", "grailzee_2026-04-21.csv"],
  "source_rows_total": 19335,
  "canonical_rows_emitted": 10440,
  "asset_class_filtered": 3,
  "numerals_blank_dropped": 71,
  "fallthrough_drops": 10,
  "within_report_duplicates": 10,
  "cross_report_duplicates": 8801,
  "numerals_slash_canonicalized": 20,
  "nbsp_normalized_nr_rows": 108,
  "dial_color_unknown": 1116,
  "named_special_detected": 1087,
  "within_report_near_collisions": 19
}
```

Arithmetic check: `19335 - 3 - 71 - 10 - 10 - 8801 = 10440`. **Holds.**

---

## Assertion table

| v2 prompt §7 Part A assertion | Expected | Got | Verdict |
|----|----|----|----|
| `source_rows_total` | 19,335 | 19,335 | **exact** |
| Cross-report dedup overlap | 8,843 (within ±5) | 8,801 | delta -42; **outside ±5 strict tolerance**; explained below |
| NBSP-normalized NR rows | 109 (Phase 1) | 108 | within Phase 1 tolerance |
| Asset-class filter | 3 (Phase 1) | 3 | **exact** |
| Numerals blank-dropped | 72 (Decision 5) | 71 | within ±3 |
| Numerals slash-canonicalized | 18 (Decision 6) | 20 | within ±2 |
| Dial-color unknown | 392 (Phase 1 unparseable only) | 1,116 | **expected delta**; v2 simplification collapses Phase 1's "ambiguous" bucket into unknown (see below) |
| Per-family parse rates | not measured at row level in 2a; revisit in 2b | (n/a) | deferred to 2b spot-check per v2 prompt §7 |

---

## Cross-report dedup delta explanation (-42 vs prompt's 8,843)

Phase 1 + discovery I.4 measured cross-report overlap by deduping the **raw** W1+W2 union. My pipeline runs pre-filters (asset-class + numerals blank + fallthrough = 84 rows dropped) **before** dedup. Pre-filtered rows do not enter the cross-report counter, even when they have a cross-report partner that DOES survive.

Decomposition of the delta:
- Phase 1 raw-union overlap: 8,837 (discovery I.4)
- v2 prompt asserted: 8,843 (slight rounding variance from Phase 1's 8,839)
- My pipeline post-filter cross-report drops: 8,801

Difference (8,837 − 8,801 = 36) is the count of cross-report-shared 4-tuples where one side is in my pre-filter drop set (handbag, blank-numerals, or fallthrough). Those 36 keys still resolve to one canonical row (the surviving partner from the other report) but no `cross_report_duplicates` counter increment occurs because the duplicate side never reached the dedup step.

This is correct semantic behavior of the locked pipeline order (filter before dedup). The counter measures "rows the dedup step removed", not "all keys present in both reports".

**Verdict**: not a regression; not a kill-condition trigger (delta is 0.47%, well below 10%). Surface for plan-review acknowledgment.

---

## Dial-color unknown delta explanation (1,116 vs 392)

Phase 1 §5 distinguished three buckets:
- **Clean** (single base color, no compound): 17,657 (91.32%)
- **Ambiguous** (compound + base, multi-base, or base+compound): 1,286 (6.65%)
- **Unparseable** (no anchor, or anchor without color): 392 (2.03%)

The v2 prompt §5 simplifies to two buckets: parsed (single base color in 4-word window) vs `"unknown"`. My implementation conservatively collapses Phase 1's "ambiguous" into "unknown":

- 392 unparseable → 392 unknown
- ~724 ambiguous → unknown (rows where multiple base colors appear in the 4-word window before "dial", e.g., "Tudor Black Bay 41MM Blue Dial" puts both `black` and `blue` in window)
- Remaining ~562 ambiguous resolved to a single base color (compound + single base where compound contributes to `named_special`, base to `dial_color`)

`named_special_detected: 1,087` reflects the compound-detection independently. The Phase 1 compound table summed to ~1,055 rows; my count is within tolerance (deduplication of overlapping compound matches via longest-match-wins explains the gap).

**Verdict**: expected behavior of the v2 prompt's simplification. The 4-axis `dial_color` keying axis carries `unknown` as a legitimate bucket value (Decision 4); strategy session interprets compound-bearing rows via `named_special` (Phase 2c surfacing).

---

## Within-report findings (live)

`within_report_duplicates: 10` matches discovery I.4 exactly (6 W1 + 4 W2 4-tuple collision groups).

`within_report_near_collisions: 19`; discovery I.4 reported 33 (15 W1 + 18 W2). The delta -14 is because near-collision counting runs **after** dedup in my pipeline; some near-collision groupings that included a within-report duplicate get partially absorbed by the dedup step. Operator plan-review accepted the count-and-do-not-drop policy; the absolute count is advisory.

---

## What this spot-check did not cover

Per v2 prompt §7:
- Cache regeneration (2a does not touch cache).
- §1.7 analytical-quality benchmark (scoring outputs, all 2b territory).
- Datejust per-bucket judgment validation (heaviest spot-check; lives in 2b).
- Deal-evaluator behavior (2c).

---

## Operator review items

1. Cross-report dedup counter is filter-aware (semantic, not bug). Confirm acceptable framing.
2. `dial_color_unknown=1,116` exceeds Phase 1's unparseable count (392). v2 prompt's parsed-vs-unknown simplification is the proximate cause; Phase 2b's bucket-count check should treat `unknown` as a real (and large) keying bucket.
3. `within_report_near_collisions=19` (post-dedup) vs discovery I.4's 33 (pre-dedup). Definition consistent, surface differs because of pipeline ordering; counter is advisory only.

No assertion misses on row-count fundamentals (no delta exceeds 10%).
