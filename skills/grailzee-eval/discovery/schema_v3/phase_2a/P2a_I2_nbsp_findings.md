# P2a I.2: NBSP Distribution Spot-check
**Date**: 2026-04-24
**Runtime**: Python 3.12.10
**Inputs**: post-patch CSVs (W1 9,440 + W2 9,895 = 19,335 rows total).

## NBSP-tolerant NR detection

Regex `^No Reserve\s*-\s*` with `re.UNICODE` matches a leading `No Reserve` followed by NBSP-containing whitespace before the hyphen and after. Rows with NBSP in the prefix that the literal-space `startswith("No Reserve - ")` would miss:

| Report | NR-rows-via-NBSP-only |
|------|------|
| W1 | 47 |
| W2 | 59 |
| Combined | **106** |

Phase 1 reported 49 + 60 = 109 across W1+W2. This run: 47 + 59 = 106. **Delta from Phase 1.** Investigate.

## Per-field NBSP scan (all string fields)

Counts of rows where the field contains at least one U+00A0:

| Field | W1 | W2 |
|-----|-----|-----|
| `title` | 47 | 59 |

## Non-`title` NBSP occurrences

**None.** NBSP only appears in the `title` field. The Phase 2a normalization pass at pipeline step 3 only needs to clean `title` (and any field built from it) before regex match and dedup hash. Other string fields are NBSP-clean across W1+W2.

## Python `re.UNICODE` verification

Python 3.12.10. `re.compile(r"\s+", re.UNICODE).fullmatch("\u00a0")` returns: `<re.Match object; span=(0, 1), match='\xa0'>`.

Verdict: `\s` with `re.UNICODE` **does** catch U+00A0. Phase 2a regex `^No Reserve\s*-\s*` works without explicit NBSP listing.

Note: Python 3 `re` module uses Unicode by default for `str` patterns; `re.UNICODE` is technically a no-op for `str` patterns but kept explicit per Phase 2 Spec Input 4 for documentation clarity.

## Plan-review items

Surface above for operator review.
