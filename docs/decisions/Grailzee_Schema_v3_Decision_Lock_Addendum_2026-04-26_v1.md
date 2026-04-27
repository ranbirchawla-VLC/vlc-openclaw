# Schema v3 Decision Lock — Addendum

**Date**: 2026-04-26
**Predecessor**: `Grailzee_Schema_v3_Decision_Lock_2026-04-24_v1.md` (seven schema decisions)
**Source session**: 2b drafting / execution / fixup (close-out: `Grailzee_Schema_v3_Phase_2b_Session_Closeout_2026-04-24_v1.md`)
**Status**: Four architectural decisions locked at 2b. One process decision adopted as standing supervisor practice. Read with v1 at the start of any 2c session.

---

## Locked decisions (additive to v1)

### 8. V3-only, no dual-emit, no back-compat shim

**Statement.** The analyzer writes schema v3 only. The v2 cache shape is not preserved or recreated. Consumers break at 2b ship and restore in 2c. Tests that pin v2 shape carry `2c-restore` skip markers.

**Reasoning.** Operator-directed "build fast to the future, safely with testing." Dual-emit doubles maintenance and forces the cache to carry a shape that is being deprecated. Back-compat shims hide drift instead of surfacing it. The clean break with explicit skip markers makes consumer-restoration scope visible and finite — the inventory of `2c-restore` skips is the work surface.

**Locked at**: 2b scope alignment.

---

### 9. No reference-level market aggregates in the cache

**Statement.** The reference is not a single thing in v3. It is a set of buckets plus an own-ledger summary (`confidence` dict) plus reference-level trend (no bucketed history yet). Any "representative median" or "representative signal" across buckets is synthesis, not fact, and belongs in the strategy-session reading-partner pass or in the consumer's own logic.

**Reasoning.** A reference like Tudor 79830RB carries four buckets with medians spanning $3,050 to $3,900 and signals from Strong to Reserve. A single representative median or signal collapses the discipline the bucket keying was built to enforce. Reintroducing reference-level synthesis as cache fields repeats the B.6 failure mode (judgment-in-cache that silently distorts consumer behavior).

**Locked at**: 2b fixup, after code-review surfaced `_dominant_median` and `_best_signal` as synthesis drift.

---

### 10. Ledger-to-market premium comparison moves to strategy-session time

**Statement.** `premium_vs_market_*` and `realized_premium_*` are not cache fields in v3. At strategy-session time, the reading-partner has the ledger entry (with its bucket keying) and the cache bucket's median; comparison happens in conversation.

**Reasoning.** Premium comparison requires bucket-keyed ledger entries and bucket-keyed market medians. Both are facts the cache and ledger carry. The comparison itself is a synthesis: which bucket does this trade match, what does "premium" mean when the reference has black-NR and white-RES buckets at different price path, when does the comparison even apply. Synthesis is reading-partner territory. The cache stays facts.

**Locked at**: 2b fixup.

---

### 11. Signal labels are sort-convenience, not ground truth

**Statement.** Per-bucket `signal` (Strong / Normal / Reserve / Careful / Pass / Low data) stays in the cache as a CSV sort aid and at-a-glance cycle read. The LLM reading-partner reads medians, volumes, risk, st_pct, and condition_mix natively and classifies its own way in conversation. Bucket-level signal counts ship as the summary rollup shape (`strong_bucket_count` through `low_data_bucket_count` plus `total_bucket_count`). No reference-level signal synthesis.

**Reasoning.** Signal labels are heuristic. Treating them as ground truth in downstream code (e.g., "filter to Strong only") rebuilds the judgment-in-cache problem at the consumer layer instead of the cache layer. The reading-partner can disagree with the label based on the underlying numbers; preserving that disagreement is the point of the architecture.

**Locked at**: 2b fixup; codified by summary-counts patch.

---

## Standing process decision (adopted 2026-04-24)

### Opus for architectural-gap-sensitive workstreams

**Statement.** Use Opus for Claude Code build sessions where architectural intent can drift silently — architecture-shaping refactors, novel domain logic, contract design, fall-back logic where the spec permits multiple synthesis paths. Use Sonnet for tight-scope well-specified work with known-good patterns — listings, bug fixes against known-good code, skill edits, consumer restorations following established patterns.

**Reasoning.** 2b on Sonnet produced `_dominant_median` and `_best_signal` synthesis drift that should have been caught at plan-review and was not. The build model could not see that the spec permitted decisions it shouldn't make. 2b fixup on Opus executed cleanly and flagged the summary-counts gap proactively. Opus token cost premium is small next to a review-fixup loop.

**Standing application.** Recorded in supervisor practice. Each Code prompt names model choice with rationale.

---

## Implications for 2c (carried to planning)

- Wave 1: `build_shortlist.py` Sonnet (well-specified bucket-row CSV reshape). `evaluate_deal.py` Opus (bucket-matching fall-back logic carries the synthesis risk Decision 9 closed off in the cache and that needs not to reappear in the matcher). Strategy skill drafted Chat-side.
- Wave 2: `build_summary.py`, `build_brief.py`, `build_spreadsheet.py`, `analyze_brands.py` — Sonnet, well-specified consumer restorations.
- Strategy skill carries the premium-comparison capability Decision 10 moved out of the cache. Minimum-viable scope for Monday is bucket-aware narration; full scope is bucket narration plus ledger-to-market premium in conversation.
- Consumer behavior must not gate on signal value (Decision 11). Sort by signal: yes. Filter by signal: no.
- The `2c-restore` skip-marker inventory (Decision 8) is the canonical scope check for Wave 1 + Wave 2 completion.

---

## Decision count after this addendum

- Schema decisions (v1): 7
- Implementation-emergent (2a, state doc Section 4): 4
- Architectural (2b, this addendum): 4
- **Total locked schema/architectural**: 15

Process decisions (this addendum): 1.

---

## Pointers

- `Grailzee_Schema_v3_Decision_Lock_2026-04-24_v1.md`: parent decision lock, seven schema decisions.
- `Grailzee_Schema_v3_Phase_2b_Session_Closeout_2026-04-24_v1.md`: full 2b narrative, including the architectural decisions captured here.
- `GRAILZEE_SYSTEM_STATE.md`: current production truth. Section 4 decisions log to be appended at 2b commit time.
- `AGENT_ARCHITECTURE.md`: canonical OpenClaw agent reference. Standing read for all Code prompts.

---

*End of addendum. Load this plus v1 plus state doc plus 2b close-out at the start of the next supervisor chat.*
