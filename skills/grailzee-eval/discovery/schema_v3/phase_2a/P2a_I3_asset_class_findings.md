# P2a I.3: Asset-class False-positive Scan
**Date**: 2026-04-24
**Inputs**: post-patch CSVs (W1 9,440 + W2 9,895).

## Candidate regex

```python
INCH_RE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)+\s*IN\b")
```

Matches `<num>(\s*x\s*<num>)+\s*IN` (uppercase `IN`) with one or more `x`-separated dimensions. Watch descriptors use uppercase `MM` for size and never the dual-dimension pattern; the regex is structurally exclusive to multi-dimension dimensional descriptors.

## Matches

| Report | Match count |
|------|------|
| W1 | 0 |
| W2 | 3 |
| Total | **3** |

### Match corpus

- `W2` make=`Louis Vuitton` ref=`On My Side MM M53826` matched `9.6 x 12 x 5.5IN`: `2011 Louis Vuitton On My Side 9.6 x 12 x 5.5IN Leather Gold-Color Hardware Leather Strap (On My Side MM M53826)`
- `W2` make=`Louis Vuitton` ref=`Pochette Liv` matched `5.3 x 9.6IN`: `Louis Vuitton Liv Pochette 5.3 x 9.6IN Damier Azur Coated Canvas Steel Hardware Leather Strap (Pochette Liv)`
- `W2` make=`Louis Vuitton` ref=`M28351` matched `11 x 18IN`: `2025 Louis Vuitton Neverfull Reversible 11 x 18IN Leather/Textile Steel Hardware Leather Strap (M28351)`

Phase 1 found 0 + 3 = 3 matches (W1=0, W2=3). This run: 0 + 3 = 3. **Match.**

## False-positive check

**Zero false positives.** No watch-only brand matched the inch pattern.

## False-negative scan (dual-category brands without inch match)

Phase 1's first-pass false-negative flag was 20 W1 + 22 W2 rows on Hermès/Dior/Chanel; inspection showed all flagged rows were watches (MM-size descriptors), not handbags. Re-running here:

| Report | Dual-cat rows w/o inch match | of which `MM`-sized | of which neither MM nor IN |
|------|------|------|------|
| W1 | 55 | 55 | 0 |
| W2 | 58 | 58 | 0 |


All dual-category rows without inch match carry MM size descriptors (watches). **Zero genuine false negatives.**

## Single-dimension `<n>IN` near-misses (for completeness)

W1: 0, W2: 0


These rows do NOT match the locked multi-dimension regex. Surfaced for review only; if any are genuine handbags they would be filter-misses worth widening the regex for.

## Recommendation

Lock the multi-dimension pattern as-is. Phase 1 verdict reproduced exactly (3 matches in W2, all LV; 0 in W1; 0 FP; 0 genuine FN).

## Plan-review items

None if the single-dimension count is empty or all watch-brand. Surface above otherwise.
