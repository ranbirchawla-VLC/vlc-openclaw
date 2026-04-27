# Schema v3 Decision Lock

**Date**: 2026-04-24
**Status**: Architecture and direction locked. Phase 1 findings closed. Phase 2 implementation prompt is the next deliverable.
**Session summary**: Phase 1 discovery ran clean against live W1+W2. All threshold-gated decisions resolved against evidence. One major discovery-doc drift (rolling-window overlap) absorbed. Seven schema decisions locked below.

---

## Locked decisions

1. **Keying**: four-axis tuple `(reference, dial_numerals, auction_type, dial_color)`. Cache schema v3.
2. **min_sales_for_scoring**: stays at 3. Accept 725 scoring-eligible buckets post-dedup. Cache grows as additional reports land in the rolling window.
3. **Dial color**: 4-axis route per headline ≥90% threshold (91.32% clean parse). Named compound dials carried as `named_special` metadata on the shortlist CSV, not split into keying values. Vocabulary bounded: Skeleton, Wimbledon, Panda, Mother of Pearl, Meteorite, Tiffany, Aventurine, Reverse Panda, Tapestry, Pavé, Linen, Celebration, Tropical.
4. **Unparseable dial-color rows** (392, 2.03%): `color=unknown` as a keying bucket value. Row stays in scoring.
5. **Blank dial_numerals rows** (72, 0.4%): dropped from scoring bucket construction. Rows remain in the report store.
6. **Slash-combined dial_numerals rows** (~18): take first value before the slash. `Arabic/Roman` canonicalizes to Arabic.
7. **W1-vs-W2 dial value divergences** (5 on 8,843 overlap): prefer W2.

## Standing principles carried

- §1.7 analytical-quality benchmark. No regression against LLM-only baseline.
- Iteration discipline on the additive side. Evidence-driven decisions; pre-locked thresholds adjust when family-stratified or shape-stratified evidence requires.
- Ingest-layer canonicalization is the new architectural standing principle. Downstream reads canonical field names only. Ordinal reads past column 9 forbidden.
- No em-dashes anywhere.
- Branch `feature/grailzee-eval-v2`. No commits without operator approval.

## Phase 2 spec inputs (seven, all ready to lock)

1. Header canonicalization map (source → canonical name). Full table in Phase 1 report Phase 1 output.
2. Asset-class filter: inch-pattern regex, filter before scoring. Zero false positives, zero real false negatives.
3. Dial-numerals canonicalization: five-rule cascade plus noise-tail handling per decisions 5 and 6.
4. Auction-type detection: regex `^No Reserve\s*-\s*` with Unicode-aware whitespace. NBSP normalization precedes detection.
5. Dedup logic: four-tuple key `(reference, sold_at, sold_for, auction_descriptor)`. Constructed AFTER NBSP normalization. Scales to N reports as the rolling window grows.
6. Four-axis schema: `(reference, dial_numerals, auction_type, dial_color)` with `color=unknown` as a valid keying value.
7. `named_special` metadata column on shortlist CSV. Thirteen-case vocabulary per Decision 3.

## Next step

Draft Phase 2 implementation prompt for Claude Code. Standard §1-§8 structure. Discovery-then-implementation gates preserved. Live spot-check against W1+W2 cache regeneration before close-out. Coverage vs current production documented as expected first-cycle state.

## Pointers

- `GRAILZEE_SYSTEM_STATE.md`: current production truth. Section 3 documents schema v2 (pre-this-work). Section 4 decisions log is append-only; schema v3 entries append when Phase 2 ships.
- `Grailzee_Eval_v2_Implementation.md`: canonical April 16 intent. Reference for Phase 2 scope against full-system architecture.
- `Grailzee_Schema_Discovery_Session_2026-04-24_v1.md`: original discovery capture. Eight decisions locked there; supersedes where noted.
- `skills/grailzee-eval/discovery/schema_v3/PHASE1_REPORT.md`: Phase 1 findings. Evidence base for all decisions above.
- `Grailzee_Schema_v3_Decision_Reasoning_2026-04-24_v1.md`: reasoning archive. Load only if re-opening a decision or investigating a first-cycle anomaly.

---

*End of decision lock. Load this plus state doc plus Phase 1 report at the start of the Phase 2 drafting session. Reasoning archive is not required for drafting.*
