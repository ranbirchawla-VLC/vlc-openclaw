# Schema Rework Phase 1 Discovery Report

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2` (no commits, no production code changes)
**Data set**: `reports/Grailzee Pro Bi-Weekly Report - April W1.xlsx` + W2.xlsx, parsed in place
**Discovery scripts**: `skills/grailzee-eval/discovery/schema_v3/` (load.py + discover.py; per-phase findings at `findings/p[1-6]_*.md`)

---

## Executive summary

Phase 1 ran all six investigation phases against the live W1 and W2 workbooks. The headline outcomes:

- **Three-axis keying tuple is confirmed buildable** from header-name lookups with no ordinal reads. All ingest fields land within columns 1 through 11; name-lookup is sufficient.
- **Auction-type prefix detection works** once NBSP tolerance is added. Combined NR rate across W1+W2 is **21.11%** (1,912 W1 + 2,169 W2), matching the discovery doc's ~22% target.
- **Dial-numerals canonicalizes cleanly**. Noise tail is 0.13% of rows (6 distinct typo-and-specialty variants). W1-vs-W2 value-identity check on 8,843 overlapping sales shows 99.94% identical.
- **Asset-class inch-pattern detection has 0 false positives and 0 real false negatives** across W1+W2. Three LV handbag rows in W2 confirmed; zero in W1.
- **Dial-color headline clean parse is 91.32%**, clearing the ≥90% threshold for the 4-axis route. But stratification shows Datejust family at 78.12% and Oyster Perpetual at 74.88%, both below the threshold. Compound cases (Wimbledon 201 rows, Panda 173, Mother of Pearl 160, Skeleton 396) are material on Datejust-family references. The headline is a composite that masks a family-specific quality floor; the operator adjudicates whether the headline or the family split is the load-bearing threshold.
- **Major finding: each Grailzee Pro report is a 6-month rolling window, not a discrete bi-weekly window.** W1 covers 2025-10-06 to 2026-04-06; W2 covers 2025-10-21 to 2026-04-21. 8,839 sales appear in both reports (93% overlap). The discovery doc's "13,190 sales" figure counts duplicates. Post-dedup union is 10,486 unique sales.
- **Coverage regression**: at post-dedup three-axis keying with current `min_sales_for_scoring=3`, **725 buckets are scoring-eligible**; below current production's 1,229 references. The discovery doc's "1,330 exceeds 1,229" conclusion was based on duplicate-inflated counts. The §1.7 analytical-quality benchmark implication needs operator review before Phase 2 ships.

**Test counts**: eval 957 passed, cowork 193 passed (Python 3.12.10). Both match the state-doc expectation. No code, test, or schema changes.

---

## Phase 1: Header canonicalization map

### Full column inventory

| Position | W1 header | W2 header |
|---|---|---|
| 1 | `Sold at` * | `Sold At` * |
| 2 | `Auction` | `Auction` |
| 3 | `Make` | `Make` |
| 4 | `Model` | `Model` |
| 5 | `Reference Number` | `Reference Number` |
| 6 | `Sold For` | `Sold For` |
| 7 | `Condition` | `Condition` |
| 8 | `Year` | `Year` |
| 9 | `Papers` | `Papers` |
| 10 | `Box` | `Box` |
| 11 | `Dial` * | `Dial Numbers` * |
| 12 | `URL` | `URL` |

Both workbooks: 12 columns, primary sheet `Auctions Sold`, plus 7 aggregate sheets including `Sales Auction Type`.

### Variations detected

- Position 1: `Sold at` (W1) vs `Sold At` (W2); case-only.
- Position 11: `Dial` (W1) vs `Dial Numbers` (W2); rename.

No other variations. URL stayed at position 12 across both; Box stayed at position 10.

### Proposed canonicalization map

| Source name (any observed spelling) | Canonical name |
|---|---|
| `Sold at`, `Sold At` | `sold_at` |
| `Auction` | `auction_descriptor` |
| `Make` | `brand` |
| `Model` | `model` |
| `Reference Number` | `reference` |
| `Sold For` | `sold_for` |
| `Condition` | `condition` |
| `Year` | `year` |
| `Papers` | `papers` |
| `Box` | `box` |
| `Dial`, `Dial Numbers` | `dial_numerals` |
| `URL` | `url` |

### Ordinal-read constraint

The §5 text says "no ordinal reads past column 9" and §3.1 asks for confirmation that the planned ingest can be served entirely by header-name lookup. **Confirmed**: header-name lookup covers every ingest field. The ordinal positions listed above are inventory metadata only; the Phase 2 ingest code reads by header name. No ordinal dependency past column 9 (or at all, if strict) is required.

---

## Phase 2: Auction type parsing

### NR row counts

| Report | Rows | NR rows | NR % |
|---|---|---|---|
| W1 | 9,440 | 1,912 | 20.25% |
| W2 | 9,895 | 2,169 | 21.92% |
| Combined | 19,335 | 4,081 | **21.11%** |

Discovery-doc target: ~22%. Combined matches within 0.9 percentage points.

### NBSP finding (plan-review §6.6)

The literal prefix `"No Reserve - "` (with ASCII space) misses 49 W1 rows and 60 W2 rows where the source carries a **non-breaking space (U+00A0) in place of the ASCII space** between the hyphen and the first letter of the watch name. Examples:

- `No Reserve -\xa0Norqain Adventure Chrono Day/Date 41MM ...`
- `No Reserve -\xa02023 Rolex Sea-Dweller Deepsea "James Cameron" ...`

All 109 NBSP rows are genuine NR auctions, not ambiguous. Semantics are preserved; only the whitespace character is different. Pre-fix counts (using literal-space `startswith`) were W1=1,863 and W2=2,109 and would have miscategorized these rows as RES. **Phase 2 implementation requirement**: the NR detection must use either regex `^No Reserve\s*-\s*` with Unicode-aware whitespace or an explicit NBSP-to-space normalization at ingest.

After applying the regex-based detection, mid-string "No Reserve" occurrences drop to 0 in both reports. The prefix is an unambiguous NR signal once whitespace is normalized.

### Cross-check against `Sales Auction Type` aggregate sheet

Both workbooks carry a `Sales Auction Type` sheet broken down by month and auction-format combination. Sample W2 April 2026 rows:

- Classic / No Reserve / Standard 4 to 7 Day: 28.7%
- Classic / No Reserve / 24 Hour Flash: 2.18%
- Premium / No Reserve / Standard: 4.26%
- (NR sub-total: ~35.14%)

Sample W1 March 2026 rows: Classic NR standard 24.5%, Classic NR flash 2.77%, Premium NR standard 6.48%, Premium NR flash 0.18%, sub-total ~33.93%.

The aggregate sheet reports a higher NR share than the row-level detection (~33% vs ~21%). Header text reads "% of sales per auction type" which is ambiguous between row-share and dollar-share. Row-level detection against the `No Reserve -` prefix gives 21.11%, matching the discovery doc's "approximately 22% NR by sales percentage" claim. The most plausible reconciliation is that the aggregate is dollar-weighted and NR auctions skew lower-priced, inflating the dollar share relative to the row share. **No impact on Phase 2 implementation**: row-level prefix detection is the right signal for keying.

### Plan-review §6.6 disposition

Mid-string "No Reserve" without the literal prefix: **0 genuine ambiguous rows** after NBSP normalization. The 109 NBSP rows are NR and the normalized regex captures them unambiguously. Phase 2 ingest uses the regex-based detection.

---

## Phase 3: Dial numerals parsing

### W1 canonicalized distribution (column `Dial`)

| Count | Pct | Canonical bucket |
|---|---|---|
| 6,250 | 66.21% | No Numerals |
| 2,051 | 21.73% | Arabic Numerals |
| 871 | 9.23% | Roman Numerals |
| 216 | 2.29% | Diamond Numerals |
| 34 | 0.36% | `_blank` |
| 9 | 0.10% | `_noise` |
| 9 | 0.10% | `_slash_combined` |

### W2 canonicalized distribution (column `Dial Numbers`)

| Count | Pct | Canonical bucket |
|---|---|---|
| 6,519 | 65.88% | No Numerals |
| 2,183 | 22.06% | Arabic Numerals |
| 894 | 9.03% | Roman Numerals |
| 237 | 2.40% | Diamond Numerals |
| 40 | 0.40% | `_blank` |
| 13 | 0.13% | `_noise` |
| 9 | 0.09% | `_slash_combined` |

### Canonicalization rules applied

1. Lowercase, strip whitespace, strip trailing `.,;`.
2. Exact match against the four canonical singulars plus common plural/singular variants.
3. Slash-combined: split on `/`, canonicalize each part; if all parts map to the same bucket, assign; otherwise mark `_slash_combined` for plan-review.
4. Keyword fallback: substring match on `arabic`, `roman`, `diamond`, `no numeral`.
5. Everything else to `_noise`.

### Noise tail

Combined noise across both reports (6 distinct values, ~13 rows total):

- `No Numbers` (7 rows, W1: 3, W2: 7; "Numbers" for "Numerals" typo)
- `Sapphire Numerals` (2 in W1)
- `Plexiglass` (1 in W1)
- `Abaric Numerals` (1 in W1; typo of "Arabic")
- `Other` (1 in W1)
- `Gemstone Numerals` (1 in W1)
- `Diamond` alone (1 in W1; maps to Diamond Numerals via keyword fallback)

### Slash-combined

Approximately 9 rows per report, all variants of `Arabic/Roman Numerals` or `Roman/Arabic Numerals` (and one `Diamond/Sapphire Numerals`). Plan-review disposition (§6.5): 0.09% of rows; below the 5% threshold the discovery prompt set for re-opening the keying-axis decision. Ships as `_slash_combined` metadata bucket or as whichever of the two values the ingest prefers; either keeps the keying-axis decision.

### W1-vs-W2 value-identity check

Matched 8,843 rows on the composite key `(Reference Number, Sold at/Sold At, Sold For)`:

- Identical dial value: 8,838 (99.94%)
- Divergent dial value: 5 (0.06%)

Sample divergences (all are cycle-identical sales where one report says `No Numerals` and the other says `Roman Numerals`):

- `ref=116334, sold_at=2026-03-06, sold_for=$10,000`: W1 `No Numerals` vs W2 `Roman Numerals`
- `ref=126334, sold_at=2026-01-28, sold_for=$14,000`: W1 `No Numerals` vs W2 `Roman Numerals`
- `ref=126300, sold_at=2026-01-21, sold_for=$11,000`: W1 `No Numerals` vs W2 `Roman Numerals`
- `ref=126334, sold_at=2026-01-14, sold_for=$14,000`: W1 `Roman Numerals` vs W2 `No Numerals`
- `ref=126300, sold_at=2025-11-19, sold_for=$10,100`: W1 `No Numerals` vs W2 `Roman Numerals`

Source-side data-quality issue, not a parsing issue. Five sales flipped classification between the two pull dates. 99.94% stability supports the canonicalization-map assumption that the W1 `Dial` and W2 `Dial Numbers` columns carry identical underlying data.

### Plan-review §6.5 disposition

Noise tail is 0.13% of rows, well under the 5% threshold. Dial-numerals remains a valid keying axis. `_blank` (0.36%) and `_slash_combined` (0.09%) need a Phase 2 decision on bucketing: recommend mapping `_blank` rows to `unknown_numerals` as a fifth bucket (32+40=72 rows total) rather than dropping, and folding `_slash_combined` to whichever half is primary (convention: first value before the slash).

---

## Phase 4: Asset class detection

### Inch-pattern matches

| Report | Total rows | Matches | Makes |
|---|---|---|---|
| W1 | 9,440 | 0 | (none) |
| W2 | 9,895 | 3 | Louis Vuitton (3) |

W2 matches are `Neverfull Reversible 11 x 18IN`, `On My Side 9.6 x 12 x 5.5IN`, `Liv Pochette 5.3 x 9.6IN`. All three are confirmed Louis Vuitton handbags with dimensional descriptors. Discovery-doc expectation of 3 LV rows in W2 confirmed. Zero handbag rows in W1 (expected).

### False-positive check

Zero matches whose `Make` is a watch-only brand. The inch pattern does not coincidentally fire on watch descriptors.

### False-negative check (revised)

The audit's first-pass false-negative check flagged 20 W1 rows and 22 W2 rows on brands in a `HANDBAG_MAKES` set (Hermès, Dior, Chanel). **Inspection shows all flagged rows are watches, not handbags** (Hermès H08 39MM, Dior Bagheera 24MM Quartz, Chanel J12 41MM, etc.). Hermès, Dior, and Chanel are dual-category brands that make both watches and handbags. Their watch SKUs use `MM` size notation (same as every watch descriptor); only the handbag SKUs use the inch pattern. The inch-pattern detector is correctly selective. **Zero genuine false negatives.**

### Filter behavior

Phase 2 implementation: set `asset_class = "handbag"` for rows matching the inch pattern, else `asset_class = "watch"`. Scoring pipeline filters on `asset_class == "watch"`. The 3 handbag rows remain in the report store but are excluded from scoring, bucket construction, confidence, and premium calculations.

### Plan-review

No plan-review item surfaced by Phase 4. Detector is clean.

---

## Phase 5: Dial color audit (the gated investigation)

### Parse rule

1. Require literal `dial` in the Auction descriptor (case-insensitive) as an anchor. No anchor maps to `unparseable`.
2. Scan for base-color vocabulary (26 colors) within a 4-word window preceding `dial`.
3. Scan for compound dial names (31 known names) anywhere in the descriptor.
4. Classification:
   - `clean`: exactly one base color, no compound qualifier.
   - `ambiguous`: compound hit OR multiple base colors OR base color plus compound qualifier.
   - `unparseable`: no anchor, or anchor without color vocabulary.

Base color vocabulary: black, white, silver, blue, green, red, yellow, pink, purple, orange, brown, grey, gray, gold, champagne, cream, ivory, tan, slate, teal, turquoise, rhodium, anthracite, salmon, copper, bronze.

Compound names: mother of pearl, mother-of-pearl, mop, skeleton, skeletonized, wimbledon, tiffany, stella, tapestry, meteorite, aventurine, malachite, lapis, onyx, jade, opal, panda, reverse panda, tropical, linen, waffle, pave, pavé, gem-set, diamond pave, diamond dial, sunburst, sunray, celebration, palm, chromalight.

### Headline parse-rate

| Bucket | Count | Pct |
|---|---|---|
| Clean unambiguous color | 17,657 | **91.32%** |
| Ambiguous | 1,286 | 6.65% |
| Unparseable | 392 | 2.03% |
| Total | 19,335 | |

### Route decision against pre-locked thresholds

**Headline clean parse-rate: 91.32%** clears the 90% threshold.
**Pre-locked route on headline alone: color joins as fourth keying axis (4-axis schema).**

### Stratification by reference family

| Family | Total | Clean | Ambiguous | Unparseable | Clean pct |
|---|---|---|---|---|---|
| other | 12,243 | 11,332 | 693 | 218 | 92.56% |
| sport_rolex | 3,506 | 3,406 | 87 | 13 | **97.15%** |
| datejust | 1,540 | 1,203 | 304 | 33 | **78.12%** |
| tudor_sport | 1,401 | 1,233 | 158 | 10 | 88.01% |
| oyster_perpetual | 645 | 483 | 44 | 118 | **74.88%** |

Sport Rolex families trade at 97% clean parse. The dimension is a near-no-op there because most sport models are color-uniform (black dial submariner, etc.) and the descriptor is short and regular. Datejust and Oyster Perpetual, the families where color matters most per the discovery doc, show 78% and 75% clean parse; both **below the 90% headline threshold** when viewed in isolation.

### Compound cases (plan-review §6.3)

| Compound | Rows |
|---|---|
| skeleton | 396 |
| wimbledon | 201 |
| panda | 173 |
| mother of pearl | 160 |
| meteorite | 27 |
| tiffany | 26 |
| aventurine | 23 |
| reverse panda | 20 |
| tapestry | 17 |
| pavé | 15 |
| linen | 15 |
| celebration | 13 |
| tropical | 13 |

Four compound cases are material: Wimbledon, Panda, Mother of Pearl, and Skeleton (together 930 rows). **Wimbledon and Tiffany in particular carry meaningfully different market value from the base color they parse to.** A Wimbledon dial Datejust (green-grey striated) trades at a premium over a plain green Datejust; a Tiffany dial Rolex (robin's egg blue) trades at a large premium over a plain blue Rolex. The parser flags these as `ambiguous` (compound + base color), so they are NOT included in the 91.32% clean rate. The clean-rate is honest.

But the Phase 2 keying decision is the inverse question: do we want a `color=green, compound_flag=wimbledon` bucket, or a `color=wimbledon` dedicated bucket, or a `color=unknown` bucket? The 4-axis schema route per the pre-locked thresholds needs a policy on compound cases before Phase 2 ships.

### Base-color distribution among clean rows (top 10)

| Color | Count |
|---|---|
| black | 7,144 |
| white | 3,076 |
| blue | 2,692 |
| silver | 1,382 |
| green | 763 |
| grey | 655 |
| champagne | 540 |
| brown | 410 |
| gold | 392 |
| red | 227 |

### Recommendation on dial-color route

**Headline route is "4-axis schema" per the pre-locked thresholds.** Three caveats the operator must adjudicate before Phase 2 locks:

1. **Family-specific parse rates**: Datejust 78% and Oyster Perpetual 75% both fall short of 90%. The discovery doc said "Datejust-family references are where the dimension provides signal exactly where it should." Those families are also where the parser is weakest. The 91% headline is carried by sport Rolex (97%) and the "other" family (92%), which the operator said are nearly color-uniform and therefore low-signal for dial-color. There is an argument that the operator's actual high-value families fail the threshold and the headline clean rate is a wrong-question answer.
2. **Compound-case policy**: Wimbledon, Tiffany, Panda, and named-special dials (930 rows total across W1+W2) must get a Phase 2 rule. Options: (a) treat as dedicated colors, which Phase 1 didn't evaluate; (b) treat as ambiguous metadata with no bucket split; (c) include them in the keying but expect the strategy session to interpret them. Each option is a distinct decision on the analytical-quality floor.
3. **Anchor-less descriptors**: 392 unparseable rows lack the word "dial" entirely. Samples include vintage descriptors that predate the current template. Phase 2 needs a decision on handling: drop from scoring (coverage loss) vs assign a default color vs pool to a color-unknown bucket.

The discovery-doc pre-locked decision says ≥90% → 4-axis. Honoring the lock: Phase 2 ships with `dial_color` as a fourth keying axis, compound cases grouped under their compound name (e.g., `wimbledon` becomes its own color value), and unparseable rows assigned `color=unknown`. Operator adjudicates whether the Datejust 78% sub-threshold warrants reconsideration before Phase 2 drafts the schema.

---

## Phase 6: Coverage simulation

### Concatenated (with duplicates, matches discovery-doc method)

Keying on `(Reference Number, dial_numerals, auction_type)`, counting every row including the 8,839 cross-report duplicates:

- Total buckets: 4,692
- Scoring-eligible (>=3 sales): **1,332**
- Sales in scoring-eligible buckets: **13,194**
- Handbag-pattern filtered: 3
- Distinct references: 3,904

Discovery-doc headline was 1,330 buckets across 13,190 sales. **Confirmed within rounding** (1,332 vs 1,330; 13,194 vs 13,190).

### Post-deduplication (major finding, not anticipated by discovery doc)

Each Grailzee Pro report is a **6-month rolling window**, not a discrete bi-weekly window:

- W1 date range: 2025-10-06 to 2026-04-06
- W2 date range: 2025-10-21 to 2026-04-21
- Overlap (match on `reference, sold_at, sold_for, auction`): **8,839 sales**
- W1 unique keys: 9,434. W2 unique keys: 9,891. Union: 10,486 unique sales.

Deduplicating to union-unique sales and rebuilding buckets:

- Total buckets: 4,692 (unchanged; keys are the same)
- Scoring-eligible (>=3 sales): **725** (down from 1,332 at pre-dedup)
- Sales in scoring-eligible: 5,892 (down from 13,194)

**725 scoring-eligible buckets after dedup is below current production's 1,229 references**, which contradicts the discovery doc's conclusion that the W1+W2 two-report cache "exceeds current production scoring count."

### Bucket size distribution (post-dedup)

| Bucket sales | Buckets |
|---|---|
| 1 | (derived from 4,692 total minus below) |
| 2 | (1,349 - 725 = 624) |
| 3-4 | 254 |
| 5-9 | 229 |
| 10-24 | 202 |
| 25-49 | 59 |
| 50-99 | 24 |
| 100+ | 12 |

Threshold sensitivity (post-dedup, three-axis keying):

| min_sales | Scoring-eligible buckets | Sales in eligible |
|---|---|---|
| 1 | 4,692 | 10,483 |
| 2 | 1,349 | 7,140 |
| 3 | **725** | 5,892 |
| 4 | 471 | 5,130 |
| 5 | 350 | 4,646 |

At `min_sales=2`, coverage reaches 1,349 buckets, slightly above the current production's 1,229 reference-level count but with noisier signal (buckets of 2 sales have median equal to the simple average of two points). At `min_sales=3`, coverage is 725 buckets, significantly below production.

Ref-only keying (current production shape) on the dedupped W1+W2 union:

| min_sales | Refs scoring-eligible |
|---|---|
| 2 | 1,310 |
| 3 | 716 |

716 refs at min=3 on the dedupped W1+W2 data is significantly below the current production cache's 1,229. The shortfall is not attributable to the new keying axes; it is attributable to the historical-window cutoff implicit in the two-report set. Current production was built from `grailzee_2026-03-23.csv` (a single report) and scored 1,229 refs, meaning the current cache has access to more reference-level data than the proposed two-report dedup union provides. Possible reasons: the older report carries different date ranges, or the current cache uses a different canonicalization path that preserves more references, or the `grailzee_2026-03-23.csv` export had higher total row count.

### Datejust per-bucket medians (post-dedup reliance; phase 6 output uses concatenated for comparability to discovery-doc, numbers below preserve concatenated semantics)

For the sample references the prompt named, pulling from the concatenated (with duplicates) bucket set:

**126300 (307 rows, blended median $10,200)**

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Arabic Numerals | NR | 2 (<min) | $14,800 |
| Arabic Numerals | RES | 2 (<min) | $9,500 |
| Diamond Numerals | RES | 4 | $10,750 |
| No Numerals | NR | 34 | $10,100 |
| No Numerals | RES | 156 | $10,150 |
| Roman Numerals | NR | 9 | $10,200 |
| Roman Numerals | RES | 100 | $10,400 |

**126334 (291 rows, blended median $14,200)**

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 17 | $15,000 |
| No Numerals | NR | 17 | $13,650 |
| No Numerals | RES | 160 | $14,375 |
| Roman Numerals | NR | 13 | $14,200 |
| Roman Numerals | RES | 84 | $14,000 |

**126234 (72 rows, blended median $11,725)**

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 9 | $11,000 |
| No Numerals | NR | 6 | $10,000 |
| No Numerals | RES | 30 | $11,714 |
| Roman Numerals | NR | 2 (<min) | $10,201 |
| Roman Numerals | RES | 25 | $12,100 |

**16013 (65 rows, blended median $5,000)**; a vintage Datejust with diamond-set dial variants

| dial_numerals | auction_type | n | median |
|---|---|---|---|
| Diamond Numerals | RES | 30 | $5,000 |
| No Numerals | NR | 6 | $4,300 |
| No Numerals | RES | 23 | $5,700 |
| Roman Numerals | RES | 4 | $4,325 |
| `_blank` | RES | 2 (<min) | $6,700 |

Signal commentary: the per-bucket medians for 126300 show a tight range ($9,500 to $14,800) but the 14,800 bucket (Arabic Numerals NR) has only 2 sales and does not meet the min-sales threshold. At min=3, 126300 has 5 eligible buckets with medians between $10,100 and $10,750; three-axis keying does not produce meaningfully different medians from reference-only. On 126334, Diamond Numerals RES at $15,000 vs No Numerals RES at $14,375 shows a $625 delta (~4%), which is modest but real. Dial-numerals signal on Datejust is directionally correct but muted in the 2026 data slice.

On 16013 (vintage 36MM Datejust), the Diamond Numerals RES bucket ($5,000, n=30) sits below the No Numerals RES bucket ($5,700, n=23). This is counterintuitive (diamond-set dials usually trade at premium) and may reflect aftermarket diamond-set dials being discounted in the current market, or sample noise. The median alone does not tell the full story.

### 126300.126334 reference samples with 116234 exception

The prompt's sample included 116234. That reference does not appear in the Datejust top-volume set in W1+W2; 126234 (next-generation 36MM Datejust) was substituted in the output and produces the more data-rich view.

### Plan-review §6.4 disposition

Bucket-size distribution surfaced above. At current `min_sales_for_scoring=3`, post-dedup coverage is 725 buckets. If the operator lowers the threshold to 2, coverage jumps to 1,349 buckets at the cost of noisier per-bucket medians (median of two points equals their average). Operator decision required in Phase 2 drafting.

### Plan-review §6.8 disposition

Per-bucket medians on Datejust references are measurably distinct from reference-only blended medians on 126334 (Diamond vs No Numerals, $15,000 vs $14,375) and the 16013 edge case shows the keying surfaces an anomaly worth operator review. Directionally the sharpening is present. Whether it is "meaningfully sharper" against the §1.7 bar is an operator judgment call against real trading outcomes, not a data-side determination.

---

## Drift findings consolidated

Where Phase 1 evidence diverges from the discovery doc:

1. **Column count**: discovery doc said "Aug1 (10 columns) and Feb W1 (11 columns) had no dial column. April W1 added a `Dial` column at position 10. April W2 renamed it to `Dial Numbers`." **Actual April W1 column count is 12** (headers include URL at position 12); Dial is at position 11, not 10. Neither value affects Phase 2 ingest because ingest is header-name-driven, but the discovery doc's position-10 claim for Dial is off by one.

2. **Each report is a 6-month rolling window** (not a bi-weekly discrete period). Discovery doc implicitly treats W1 and W2 as non-overlapping bi-weekly periods and says "combined W1+W2 = 13,190 sales across 1,330 buckets." Correct statement is "concatenated W1+W2 (with 8,839 duplicates) = 13,194 sales across 1,332 scoring-eligible buckets; post-dedup unique = 10,486 sales across 725 scoring-eligible buckets." Both counts are meaningful depending on whether Phase 2 ingest dedupes or not. Phase 2 MUST dedupe to avoid double-counting the same sale.

3. **NBSP in NR prefix**: discovery doc did not anticipate the 109 rows with `\xa0` after the hyphen. Phase 2 prefix detection must normalize this whitespace or use a Unicode-whitespace regex. Without the fix, ~0.56% of NR rows silently misclassify as RES.

4. **Coverage regression at current threshold**: discovery doc concluded "1,330 exceeds 1,229 (current production) with cleaner per-bucket signal." Post-dedup at `min_sales=3`, three-axis coverage is 725 buckets, below production 1,229. Ref-only post-dedup at `min_sales=3` is 716 refs. The discovery-doc "higher-coverage path" conclusion does not hold under dedup. Phase 2 drafting must confront this.

5. **Phase 5 family stratification**: discovery doc called dial-color parseability "unconfirmed" and noted compound cases. Phase 1 confirms the headline 91% but also surfaces family-specific parse rates: Datejust 78%, Oyster Perpetual 75%. Neither of those families' isolated parse rates clears the ≥90% threshold. The pre-locked thresholds apply to a headline; the Datejust family that operator says is "exactly where the dimension matters most" is where the parser is weakest.

6. **116234 absent from top Datejust references in W1+W2**: discovery doc suggested 116234 as a sample ref. In W1+W2 data, 116234 does not appear in the top 10 Datejust refs. 126234 (next-gen 36MM Datejust) substituted in Phase 6 output.

7. **5 W1-vs-W2 dial value divergences** on identical sales (same reference, same date, same price, same auction descriptor). Source-side data-quality issue, not a parsing issue. Phase 2 should decide precedence: W2's `Dial Numbers` rename is presumably the newer and more carefully curated data; default to W2 on tie, or last-seen-wins, or whichever operator prefers.

---

## Plan-review §6 surfacing items

- **§6.1 (discovery script location)**: scripts live at `skills/grailzee-eval/discovery/schema_v3/` per default. Two files (`load.py`, `discover.py`) plus `findings/` subdirectory. No production directory touched. Operator picks final location; default stands.
- **§6.2 (discovery script lifetime)**: default is delete at Phase 2 close-out. No current consumer outside Phase 1 will reference these scripts; the canonicalization map and the dial-color rule set are the durable artifacts, and they land in the Phase 2 ingest code.
- **§6.3 (compound dial-color cases)**: addressed in Phase 5. 930 rows across four material compounds. Operator must decide on compound handling before Phase 2 ships `dial_color` as a keying axis.
- **§6.4 (bucket-size threshold)**: current `min_sales_for_scoring=3`. Post-dedup coverage at 725 vs production 1,229 raises a threshold question Phase 2 must address.
- **§6.5 (dial-numerals noise tail size)**: 0.13% combined. Below 5% threshold. Keying axis stands.
- **§6.6 (auction-type ambiguous rows)**: 109 NBSP rows captured as NR via regex-based detection. Zero genuine ambiguous rows remain after normalization.
- **§6.7 (W1 vs W2 value-identity)**: 99.94% identical on 8,843 overlap rows. 5 divergences on Datejust references, all source-side data-quality noise.
- **§6.8 (Datejust per-bucket signal sharpness)**: directionally sharper; operator adjudicates against §1.7 benchmark.
- **§6.9 (unanticipated)**: rolling-window overlap (drift finding 2), NBSP finding (drift finding 3), coverage regression (drift finding 4), family-stratified color parse (drift finding 5).

---

## Test count sanity check

- Eval tests: **957 passed** on Python 3.12.10 in 30.45 seconds. Matches state-doc baseline.
- Cowork tests: **193 passed** on Python 3.12.10 in 0.59 seconds. Matches state-doc baseline.

No unexpected drift. No tests run from discovery scripts (they are not part of the production test surface per §7).

---

## Git status confirmation

```
 M .claude/progress.md
 M skills/nutrios/openclaw.json
?? audit.md
?? skills/grailzee-eval/discovery/
?? skills/nutrios/logs/
```

`.claude/progress.md`, `skills/nutrios/openclaw.json`, and `skills/nutrios/logs/` pre-existed this task. `audit.md` is the 2026-04-24 production-readiness audit report from the prior task in this branch. `skills/grailzee-eval/discovery/` is this task's deliverable. **No production code, test, schema, or state-file changes.**

---

## No em-dashes confirmed

Report scanned for em-dashes before emission. Long-break punctuation uses semicolons or sentence breaks. Discovery scripts (`load.py`, `discover.py`) likewise em-dash-free.

---

## Recommendation to operator

### Dial-color route selection

**Headline clean parse rate (91.32%) clears the ≥90% threshold. Per the pre-locked decision, dial_color joins as the fourth keying axis.**

Three items require operator adjudication before Phase 2 drafts:

1. **Family-stratified parse quality**: Datejust 78% and Oyster Perpetual 75%. These are the families where dial-color carries signal per operator input. The headline rate is carried by sport families that are near-color-uniform (low-signal for the dimension). The pre-locked thresholds apply to headline; operator decides whether the family split re-opens the route decision.
2. **Compound-case policy**: Wimbledon (201 rows), Panda (173), Mother of Pearl (160), Skeleton (396); total 930 rows of named compounds that trade at meaningfully different prices from the base color they parse to. Phase 2 needs a rule: dedicated compound buckets, base color plus compound flag, or strategy-session interpretation.
3. **Unparseable rows policy**: 392 rows (2.03%) lack a `dial` anchor or color vocabulary. Assign `color=unknown`, or drop, or default to most-common color for the family. Phase 2 decision.

### Items that would re-open a locked decision

- **Coverage regression** (drift finding 4) is the sharpest re-opener. If the §1.7 analytical-quality benchmark requires scoring-eligible bucket count to match or exceed current production's 1,229, the current `min_sales=3` + W1+W2 dedup combination does not satisfy. Options for Phase 2: (a) lower `min_sales` to 2; (b) include older reports beyond the April W1 cutoff; (c) accept the coverage reduction as a trade for per-bucket signal quality; (d) evaluate whether the current 1,229 is truly scoring quality output or coverage inflation. Each option is a distinct re-opening of a locked decision (historical cutoff, keying, or threshold).
- **Rolling-window dedup** (drift finding 2). Phase 2 ingest must dedupe across reports. This is a new ingest-layer requirement the discovery doc did not specify. It is small and mechanical but belongs in the Phase 2 spec explicitly.
- **NBSP prefix** (drift finding 3). Phase 2 NR detection must use regex `^No Reserve\s*-\s*` or equivalent, not literal `startswith("No Reserve - ")`. Small implementation detail, named here so it does not get missed.

### Drift findings that do not re-open

Column count (drift 1), 116234 substitution (drift 6), and five dial-value divergences (drift 7) are source-side observations with no Phase 2 action required beyond "use header-name lookup" and "prefer W2 on tie". They belong in the Phase 2 spec appendix but do not re-open any pre-locked decision.

### Items ready for Phase 2 to lock

- Header canonicalization map (Phase 1 output).
- Asset-class detection rule (inch-pattern regex, zero false-positives, zero real false-negatives).
- Dial-numerals canonicalization rules (five-rule cascade, 0.13% noise tail).
- Auction-type detection (regex with NBSP tolerance).

---

*End of Phase 1 discovery report.*
