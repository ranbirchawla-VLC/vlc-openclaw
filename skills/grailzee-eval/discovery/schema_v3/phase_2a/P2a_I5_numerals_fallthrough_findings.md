# P2a I.5: Dial-numerals Fall-through Audit
**Date**: 2026-04-24
**Inputs**: post-patch CSVs (W1 9,440 + W2 9,895).

## Five-rule cascade applied

1. Blank/None → drop (Decision 5).
2. lowercase + strip + strip-trailing punctuation.
3. Slash-combined → take first segment (Decision 6); canonicalize via rules 4 and 5 below.
4. Exact match against canonical vocabulary (`arabic numerals`/`arabic numeral`/`arabic`, similarly for roman/diamond/no numerals).
5. Substring keyword fallback (`arabic`, `roman`, `diamond`, `no numeral`).
6. Fall-through: surfaces here.

## Distribution

| Bucket | W1 | W2 |
|------|------|------|
| `Arabic` | 2057 | 2189 |
| `Roman` | 874 | 897 |
| `Diamond` | 216 | 237 |
| `No Numerals` | 6250 | 6519 |
| `_blank` | 34 | 40 |
| `_fallthrough` | 9 | 13 |
| (slash-combined input) | 10 | 10 |

Slash-combined rows are reported separately because they fold into the corresponding canonical bucket per Decision 6 rather than dropping. Phase 1 reported approximately 9 per report (~18 total).

## Phase 1 baseline reconciliation

Phase 1 noise tail (combined): 6 distinct values, ~13 rows (`No Numbers`, `Sapphire Numerals`, `Plexiglass`, `Abaric Numerals`, `Other`, `Gemstone Numerals`). Note: `No Numbers` matches the keyword `no numeral` (substring `no numer` is missing the `al` though; Phase 1 listed it under noise but the substring `no numeral` is not in `no numbers`, so `No Numbers` does fall through here). Re-classify under this cascade:

| Report | Decision-5 drops (blank) | Fall-through count |
|------|------|------|
| W1 | 34 | 9 |
| W2 | 40 | 13 |
| Combined | **74** | **22** |

Phase 1 expected: 72 blank-dropped (Decision 5) and 18 slash-canonicalized (Decision 6). This run blanks: 74; slash-combined inputs: 20.

## Fall-through corpus

| Raw value | Count |
|------|------|
| `No Numbers` | 10 |
| `Sapphire Numerals` | 4 |
| `Plexiglass` | 2 |
| `Abaric Numerals` | 2 |
| `Other` | 2 |
| `Gemstone Numerals` | 2 |

### Per-row examples (up to 30)

- `W1` ref=`PAM01075` raw=`Plexiglass`
- `W1` ref=`79230N` raw=`No Numbers`
- `W1` ref=`M79230N` raw=`No Numbers`
- `W1` ref=`IW377719` raw=`Abaric Numerals`
- `W1` ref=`6917` raw=`Sapphire Numerals`
- `W1` ref=`343.SS.6599.NR.1233` raw=`Sapphire Numerals`
- `W1` ref=`SBT8A81.EB0335` raw=`Other`
- `W1` ref=`6917` raw=`Gemstone Numerals`
- `W1` ref=`42010N` raw=`No Numbers`
- `W2` ref=`79230N` raw=`No Numbers`
- `W2` ref=`79230N` raw=`No Numbers`
- `W2` ref=`79230N` raw=`No Numbers`
- `W2` ref=`79230N` raw=`No Numbers`
- `W2` ref=`PAM01075` raw=`Plexiglass`
- `W2` ref=`79230N` raw=`No Numbers`
- `W2` ref=`M79230N` raw=`No Numbers`
- `W2` ref=`IW377719` raw=`Abaric Numerals`
- `W2` ref=`6917` raw=`Sapphire Numerals`
- `W2` ref=`343.SS.6599.NR.1233` raw=`Sapphire Numerals`
- `W2` ref=`SBT8A81.EB0335` raw=`Other`
- `W2` ref=`6917` raw=`Gemstone Numerals`
- `W2` ref=`42010N` raw=`No Numbers`
## Recommendation

Surface fall-through corpus to operator for cascade extension or drop-rule decision before Phase 2a implementation locks the cascade.

Leading options per v2 prompt §4 I.5:
- Expand cascade with additional keyword aliases (e.g., `numbers` → `Numerals`).
- Drop fall-through rows (treat as Decision-5-equivalent).
- Carry as a `_fallthrough` metadata flag and let strategy review.

## Plan-review items

Operator decision needed on fall-through handling.
