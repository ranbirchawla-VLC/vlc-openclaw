# Phase 2b Fixup Patch; summary bucket counts

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Scope**: add seven bucket-level count fields to `summary`; one session, commit-ready after operator approval.
**Status**: tests green, em-dash clean, no commit yet per repo CLAUDE.md.

---

## Files changed

| File | Line count (after) | Change |
|------|--------------------|--------|
| `scripts/write_cache.py` | 338 | Add `total_bucket_count` and six signal counts (`strong_bucket_count`, `normal_bucket_count`, `reserve_bucket_count`, `caution_bucket_count`, `pass_bucket_count`, `low_data_bucket_count`) to the summary dict. Reference buckets only; DJ config buckets excluded to match the `total_references` precedent. Factual rollup; no reference-level synthesis. |
| `tests/test_write_cache.py` | 643 | New `TestSummaryBucketCounts` class. Helpers: `_bucket(signal, ...)` and `_bucketed_args(tmp_path, ref_buckets, dj_buckets=None)`. Three tests: parametrized single-signal count (6 cases), sum-matches-total, DJ-config-bucket-exclusion regression. |

Net test delta: **+8** (6 parametrized per-signal cases + sum-matches-total + DJ exclusion). Matches spec's "+7 or +8" bound.

---

## Two-sentence summary

Patch adds a seven-field factual rollup to the cache summary: total bucket count and per-signal bucket counts for Strong / Normal / Reserve / Careful / Pass / Low data. Reference buckets only; DJ config buckets are excluded so the counts present one view over one dataset (following the existing `total_references` precedent).

---

## Verification

| Step | Status |
|------|--------|
| Full pytest run on canonical Python 3.12.10 | 981 passed, 96 skipped, 0 failed (45s) |
| Spec bound (+7 or +8 tests) | Matched: +8 |
| Em-dash sweep on modified files | Clean |
| Ripped-fields regression (pre-existing `test_per_signal_counts_absent`) | Still passes; patch adds new `*_bucket_count` fields but does not re-introduce ripped `strong_count` / `normal_count` / `reserve_count` / `caution_count` names |

---

## Design notes

- **DJ config buckets are excluded**. Precedent: `total_references = len(ref_entries)` already excludes DJ configs. Counting DJ config buckets in the summary would present a second view over the same 126300 sales (DJ configs are a keyword-based re-slicing of 126300's rows, not a distinct dataset). Test `test_dj_config_buckets_excluded` pins this explicitly.
- **"Caution" field name vs "Careful" signal value**. Matches the pre-rip v2 convention where `caution_count` counted buckets with signal `"Careful"`. The field name stays "caution"; the literal signal value remains `"Careful"`.
- **No escalation-trigger violations**. The rollups are bucket-level counts only. Zero reference-level aggregation, zero judgment. Each field is a simple `sum(1 for bd in all_ref_buckets if bd.get("signal") == "<label>")`.

---

## Specific things to verify before commit

1. **DJ config exclusion decision**. I read the spec's "including DJ config buckets if DJ config buckets contribute to summary elsewhere; verify during build" as: since DJ configs don't contribute to any other summary field (`total_references`, `hot_references`, etc. all come from the reference or changes/breakouts paths), they don't contribute here either. Confirm this reading, or I flip the inclusion and the test.
2. **Field name set**. Seven new fields in `summary`: `total_bucket_count`, `strong_bucket_count`, `normal_bucket_count`, `reserve_bucket_count`, `caution_bucket_count`, `pass_bucket_count`, `low_data_bucket_count`. Confirm the names.
3. **Commit scope**. This patch stacks on top of the fixup rip from earlier in the session. Proposed commit scope: all fixup work (rip + three bug fixes + summary counts) as one commit, or the rip and the patch as two separate commits? Operator call.

---

*End of patch close-out.*
