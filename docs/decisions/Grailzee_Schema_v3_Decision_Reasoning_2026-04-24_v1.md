# Schema v3 Decision Reasoning Archive

**Date**: 2026-04-24
**Purpose**: Archival record of reasoning behind the seven locked schema v3 decisions. Load only if a decision re-opens or a first-cycle run surfaces an anomaly tracing to one of these decisions. Not required for Phase 2 drafting.

---

## Decision 1: min_sales=3, accept 725 buckets

**Options**: (a) lower min_sales to 2 → 1,349 buckets with noisier signal; (b) widen historical window beyond April-W1-forward; (c) accept 725.

**Why (c)**: lowering min_sales to 2 produces a median statistically equal to the average of two points. Cosmetic coverage at the cost of per-bucket trust. Fails §1.7 in spirit if not in measurement. Widening the window re-opens a locked decision for coverage gains that may be marginal given per-bucket signal cleanliness is already the higher-quality axis.

**Uncertainty band**: original supervisor-chat reasoning was "dropouts were artificially scoring on co-mingled data." Phase 1 report offers a different and more plausible explanation at line 375: the production cache was built from a single older report (`grailzee_2026-03-23.csv`) whose 6-month window pulled sales the W1+W2 dedupped union doesn't contain. Some fraction of the 513 dropped references had real sales in pre-October 2025 data. Not enough to flip the decision because the cache grows as W3, W4 land. First-cycle output should be expected to be thinner than prior LLM-only output; the cache fills over 2-3 cycles.

**Re-open trigger**: first-cycle run shows active-trade references missing from the cache. Lead option on re-open is (b).

## Decision 2: 4-axis schema, dial_color as keying

**Options**: (a) 4-axis uniformly per headline ≥90%; (b) 3-axis with color as bucket metadata because Datejust 78% and OP 75% fall below threshold; (c) per-family routing.

**Why (a)**: dial color matters most on Rolex and Tudor where operator applies strategy-session judgment during keep/strike. Datejust 78% parse quality is handled by the strategy session's keep/strike pass, which is the architectural safety net. Per-family routing (c) would move judgment into the schema where the strategy layer already handles it; violates the Python-for-analysis / LLM-for-reading-partner / operator-for-judgment split.

Supervisor push toward (c) was overweighted. The pre-locked thresholds apply to headline; the family split informs operator judgment during strategy sessions, not schema structure.

**First-cycle watch**: Datejust family references carry more per-bucket dial-color noise than sport references. If keep/strike pass is tripping on this more than expected, revisit.

## Decision 3: named_special metadata, not keying values

**Why not keying**: vocabulary is bounded (13 cases) but volume is uneven. Four compounds (Wimbledon, Panda, MoP, Skeleton) total 930 rows; long tail totals ~170 rows. At min=3, Skeleton (396) would form dedicated buckets but most others would not. Metadata lets strategy session see compound presence during keep/strike without forcing bucket splits the data doesn't support.

**Volume-independence**: Tiffany at 26 rows gets the same metadata flag as Wimbledon at 201 because the premium is per-row, not volume-weighted.

## Decision 4: color=unknown as keying bucket (392 unparseable rows)

**Shape distinction from Decision 5**: dial-color unparseable means the color exists in the physical watch but the Grailzee descriptor doesn't expose it parseably. 2.03% of universe across many references. At min=3, some references will accumulate enough unknown-color rows to form dedicated unknown buckets.

**Why (c) unknown-as-bucket vs (a) drop**: dropping loses real coverage (2% of universe). Defaulting to most-common color for family (b) invents data the schema can't justify. unknown-as-bucket preserves the row and lets strategy session interpret via the flag.

## Decision 5: blank dial_numerals dropped (72 rows)

**Shape distinction from Decision 4**: blank dial_numerals is seller-side field-population failure, not a parsing failure. The `Dial` column is empty. 72 rows is too few to form dedicated buckets at min=3 per reference. An `unknown_numerals` keying value that never scores adds noise to the schema without contributing signal.

**Kept in report store**: the rows aren't deleted; they just don't participate in bucket construction. Ledger-row-vs-report-row cross-check (future) can still find them.

## Decision 6: slash-combined takes first value (~18 rows)

Grailzee seller convention is primary-first. Arabic/Roman → Arabic. Mechanical. Zero signal loss at 0.09% of rows.

## Decision 7: W1-vs-W2 divergences prefer W2

99.94% stability across 8,843 overlap rows. 5 divergences are source-side data-quality noise. Newer pull is the safer default.

---

## Phase 1 observations carried forward (not decisions, preserved context)

### NBSP in NR prefix
109 rows use U+00A0 (non-breaking space) after the hyphen in the NR prefix. Phase 2 NR detection must use regex with Unicode-aware whitespace. **Order of operations matters**: dedup key includes the auction descriptor, so NBSP normalization must happen BEFORE dedup hash construction or same-auction rows appearing with different whitespace in W1 vs W2 will silently fail to dedup.

### 16013 vintage Datejust diamond-numerals anomaly
Per-bucket median for Diamond Numerals RES ($5,000, n=30) sits below No Numerals RES ($5,700, n=23) on the same reference. Counterintuitive (diamond-set dials typically trade at premium). Likely reflects aftermarket diamond-set dials trading at discount, or sample noise in the 2026 data slice. Not a Phase 2 blocker. Flagged for strategy-session interpretation on first cycle run.

### Coverage methodology caveat
Discovery doc's "1,330 exceeds 1,229" claim was duplicate-inflated. Post-dedup at the same three-axis keying: 1,332 pre-dedup → 725 post-dedup. Ref-only post-dedup at min=3 is 716. Production's 1,229 came from a single older report (`grailzee_2026-03-23.csv`) whose 6-month window does not equal the W1+W2 union's 6.5-month window. Coverage comparison is not apples-to-apples; per-bucket signal cleanliness comparison IS apples-to-apples, and the new keying wins there.

### Rolling-window and dedup scaling
Each Grailzee Pro report covers a 6-month rolling window (W1: 2025-10-06 → 2026-04-06; W2: 2025-10-21 → 2026-04-21; 8,839 sales overlap). Phase 2 dedup logic must scale to N reports. Four-tuple key stays; union grows as W3, W4, etc. land.

### Family parse rates (kept for Decision 2 re-open, if ever)
- sport_rolex: 97.15% clean (near-color-uniform references; low-signal for dial-color)
- tudor_sport: 88.01%
- datejust: 78.12% (below threshold; high-signal family where parser is weakest)
- oyster_perpetual: 74.88% (below threshold)
- other: 92.56%

---

*End of reasoning archive. This document preserves the "why" behind the locked decisions. The decision lock document preserves the "what" and is sufficient for Phase 2 drafting on its own.*
