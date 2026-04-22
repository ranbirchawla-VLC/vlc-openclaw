# GRAILZEE_SYSTEM_STATE

**Repo path**: `/Users/ranbirchawla/.openclaw/workspace/GRAILZEE_SYSTEM_STATE.md`
**Branch**: `feature/grailzee-eval-v2` (single long-lived)
**Owner**: Supervisor chat updates at end of every session. Operator reviews the diff before the chat closes. Commits land on the same branch as the code changes they describe.
**Read at**: Start of every supervisor chat. Start of every Claude Code task. No inference from conversation history. This document is truth.

---

## Maintenance protocol

**Session open**: First action in every new supervisor chat or Claude Code task is to read this document. State the current cache schema and the last three entries in the decisions log back to the operator. If prior context conflicts with this document, stop and flag it. The document wins unless the operator overrides explicitly.

**Session close**: Before the chat closes or the task ships, update this document with the deltas. What changed in the cache schema, what decisions landed, what moved in or out of open work. Treat it like a git commit. Every substantive change gets recorded or it did not happen.

**Edit rules**: Sections 1, 2, 3, 5, 6, and 7 are overwritten in place. Section 4 (decisions log) is append-only. Never delete a decision. If a decision is superseded, add a new dated entry that references and overrides the prior.

---

## 1. Target architecture

The Grailzee analyzer is a deterministic Python pipeline. It reads bi-weekly Grailzee Pro reports, scores every reference with 3+ sales, and produces `analysis_cache.json` on Google Drive.

Strategy happens in Chat. The strategy session reads a CSV shortlist (produced by B.7, not yet built) and discusses the candidate set with the operator as a reading-partner flow. The LLM reads, patterns emerge, the operator marks references to keep or strike. The session writes `cycle_focus.json` as the output contract.

The Telegram bot reads `cycle_focus.json` for "what am I buying right now" and reads `analysis_cache.json` for ad-hoc deal evaluation ("should I buy this at this price").

Brand-floor judgment lives in the strategy session, not in the analyzer. Per-brand margin floors are held in `brand_floors.json` as strategy config. The analyzer does not compute brand-floor clearance. The deal evaluator looks up the brand's floor at runtime and computes clearance inline against the offered price.

The core split: Python does deterministic analysis, LLM does reading-partner conversation, operator holds all judgment. The April 16 implementation plan is the canonical intent document and governs anything this state document does not cover.

---

## 2. Repo and file layout

### Git repo: `/Users/ranbirchawla/.openclaw/workspace`

- **Code**: `skills/grailzee-eval/scripts/` (Phase 22 migration completed 2026-04-21 commit `286d58b`; the `-v2` suffix from the parallel-build phase is no longer in the tree)
- **Workspace-tracked config**: `state/brand_floors.json`, `state/analyzer_config.json`, schema design docs, other config per A.2
- **This document**: repo root, `GRAILZEE_SYSTEM_STATE.md`

### Google Drive runtime data

Base path: `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/`

- `state/analysis_cache.json`: analyzer output, bot deal-evaluator input
- `state/cycle_focus.json`: strategy session output, bot target-list input
- `state/cycle_outcome_<cycle_id>.json`: per-cycle trade rollup
- `state/trade_ledger.csv`: append-only, Grailzee-only
- `state/name_cache.json`: reference to display-name mapping
- `reports/`: raw Excel reports (archived, never deleted)
- `reports_csv/`: converted CSVs (canonical)
- `output/`: human-readable analyzer outputs

---

## 3. Cache schema as-shipped

**Verified**: cycle_2026-06, regenerated 2026-04-22T14:47:04 after B.6 revert. `schema_version: 2`. Total references scored: 1,229.

### Top-level keys

`schema_version`, `generated_at`, `source_report`, `cycle_id`, `market_window`, `premium_status`, `references`, `dj_configs`, `changes`, `breakouts`, `watchlist`, `brands`, `unnamed`, `summary`.

### Per-reference fields

**Market-derived (from `analyze_references`)**:
- `brand`, `model`, `reference`, `named`
- `median`, `max_buy_nr`, `max_buy_res`
- `risk_nr`, `signal` (Strong, Normal, Reserve, Careful, Pass, Low data)
- `volume`, `st_pct`
- `momentum` (dict: `score`, `label`)
- `trend_signal`, `trend_median_change`, `trend_median_pct`
- `condition_mix` (B.4)

**Ledger-derived (from `write_cache`)**:
- `confidence` (dict: `trades`, `profitable`, `win_rate`, `avg_roi`, `avg_premium`, `last_trade`)
- `premium_vs_market_pct`, `premium_vs_market_sale_count` (B.2)
- `realized_premium_pct`, `realized_premium_trade_count` (B.3)

**B.5 capital/net fields**:
- `capital_required_nr`, `capital_required_res`
- `expected_net_at_median_nr`, `expected_net_at_median_res`

No B.6 fields in the cache. `brand_floor_cleared` removed by the 2026-04-23 revert.

---

## 4. Decisions log (append-only)

**2026-04-16**: April 16 implementation plan locked as canonical intent. Core design principles: Python does analysis, LLM does language and reading-partner judgment. Data determines priority, no hardcoded core references. Grailzee-only ledger (NR and Reserve accounts).

**2026-04-21**: Eight outcomes locked in outcomes-and-levers session:
1. Tight, conviction-ranked watchlist with explicit reasoning
2. Realized premium tracked per brand, separate from max_buy
3. Per-brand floors, absolute and asset-class-specific
4. Capacity-aware data tracked in state, no enforcement
5. Dollar-per-labor-hour ranking; strategy does capital math
6. Every close grades the system against predictions
7. Extensibility as a design constraint, not a build target
8. State files are the contract; bot is limited-write

**2026-04-21**: Brand floors locked: Rolex 5%, Tudor 10%, Breitling 10%, Cartier 10%, Omega 8%, default 10% for unlisted. Floors are absolute per-brand thresholds, not universal.

**2026-04-21**: B.2 redirect: `premium_vs_market_pct` sourced from Vardalux own ledger (most recent sale vs current median), not market data.

**2026-04-22**: B.6 v1 shipped to working tree with `brand_floor_cleared` as own-ledger-gated bool (S4 cascade: B.3 primary, B.2 fallback). Never committed; remained in working tree awaiting review.

**2026-04-23**: B.6 killed from the cache. Root cause analysis: own-ledger signals absent for roughly 80% of references because Vardalux trades approximately 20% of brands appearing in Grailzee Pro reports. B.6 as shipped silently suppressed most of the universe. The brand-floor question is a strategy-session judgment, not a cache field. Action: revert B.6 code changes, regenerate cache, brand-floor logic moves to `brand_floors.json` as strategy config read by the deal evaluator at runtime.

**2026-04-23**: Strategy interface confirmed as reading-partner flow. Analyzer produces a CSV shortlist (via B.7, not yet built). Strategy session drops the CSV into Chat, LLM reads and discusses with the operator, operator marks references to keep or strike in conversation, session writes survivors to `cycle_focus.json`. Replaces priority_score tiering and the JSON sourcing brief.

**2026-04-23**: Auction type (NR vs Reserve) is not present in Grailzee Pro report source data. All cache signals (`median`, `st_pct`, `risk_nr`, `signal`) are blended across auction types. Permanent data limitation. Strategy session applies judgment to account for the blend, especially on Rolex and high-value references where Reserve weighting is heavier.

**2026-04-23**: B.6 revert executed and verified. Eleven files restored to b5ab5fc (GRAILZEE_SYSTEM_STATE.md commit, parent 68d448e = B.5). Files reverted: `.claude/progress.md`, `skills/grailzee-eval/scripts/grailzee_common.py`, `skills/grailzee-eval/scripts/install_brand_floors.py`, `skills/grailzee-eval/scripts/write_cache.py`, four test files in `skills/grailzee-eval/tests/`, `state/brand_floors.json`, `state/grailzee_schema_design_v1.md`, `state/grailzee_schema_design_v1_1.md`. Test count 964 to 930 (B.5 baseline). All 930 passing on canonical Python 3.12.10. Cache regenerated on the two latest pricing-window CSVs; `brand_floor_cleared` absent, B.2 through B.5 fields intact.

**2026-04-22**: B.7 Phase 0 ships the brand_floors default record. `state/brand_floors.json` gains a top-level `default` record with shape `{"floor_pct": 10.0, "tradeable": true, "asset_class": "watch"}`, sibling to `brands`. `last_updated` updated, `updated_by` set to `b7_section_7_close`, `defaulted_fields` gains `default.floor_pct`. Five named brand floors unchanged. Closes Section 7 verification item. Read by the deal evaluator at runtime per the 2026-04-23 strategy-config decision.

**2026-04-22**: B.7 ships `build_shortlist.py` producing `cycle_shortlist_<cycle_id>.csv` in Drive STATE_PATH. 23-column CSV per locked spec; signal,volume_desc default sort; null ledger-derived fields write as empty strings; atomic write via tmp+fsync+os.replace; OTEL span `build_shortlist.run` with flat attrs `cycle_id`, `row_count`, `sort_key`, `output_path`. Wired as Step 16 of `run_analysis.py` after `write_cache.run`; orchestrator re-reads the just-written cache because `confidence`, `momentum`, B.2/B.3 enrichments are added by `write_cache` and never mutated back into the in-memory `all_results` dict. Sibling artifact to the cache; `schema_version` stays 2. CSV replaces `sourcing_brief.json` as the strategy reading-partner input per the 2026-04-23 decision; brief continues emitting during transition. Live regen on cycle_2026-06: 1,229 rows, all 23 columns; 10 of 1,229 refs have populated `confidence_*` fields (matches live ledger coverage). Spot-check Tudor 79830RB: confidence dict and B.5 fields match cache exactly.

**2026-04-22**: `build_brief.py` markdown footer `papers_required` linkage fixed. Pre-fix the footer hardcoded "Papers required on every deal." regardless of `sourcing_rules.json`. Post-fix it reads from `sourcing_rules['papers_required']` and emits "Papers required on every deal." or "Papers not required." accordingly, matching the JSON brief's top-level `sourcing_rules.papers_required` value. Per-target hardcoded `papers_required: True` (`build_brief.py:214`) is out of fix scope; flagged as Phase D backlog. Test count 930 → 957 (+27 net).

---

## 5. Open work

### B.8 (watchlist rename)

Rename `watchlist` to `emergent_refs` in cache schema and downstream consumers. Low complexity, sequenced after B.7.

### Open question: `max_buy_nr_realistic`

Discussed 2026-04-23 but not locked. The proposal: one new cache field that applies a flat percentage discount to median before computing the ceiling, capturing the "need to buy 5% under median" discipline for low-sell-through references.

```
max_buy_nr_realistic = (median × (1 − discount_pct / 100) − NR_FIXED) / (1 + target_margin)
```

Decision pending: whether to add this field, what `discount_pct` to use, whether to scale discount by `st_pct` or keep flat. Operator leaning toward flat 5% discount, strategy session judges reachability in conversation. Not blocking B.7.

---

## 6. Backlog

From `Vardalux_Grailzee_Backlog.md` (April 21 baseline), updated for the 2026-04-23 B.6 kill and revert.

### Dropped (obsoleted by 2026-04-23 kill)

- **BRAND_FLOORS_FACTORY_CONTENT lift**: no longer needed as B.6 gate logic. If the deal evaluator's runtime brand-floor lookup ever needs a shared constant, revisit at that point.
- **B.7 HIGH/MEDIUM/LOW mapping**: moot. Reading-partner CSV flow does not tier references at analyzer time; strategy sorts the whole list.
- **B.7 top-30 ceiling vs all-HIGH-plus-MEDIUM**: moot. Strategy session decides row count per session.
- **B.7 capital_target null fallback**: simplified. Analyzer does not do capital math; strategy does.

### Ready to execute (triggered by 2026-04-23 B.6 revert)

- **`apply_premium_adjustment` dead code**: zero callers since B.1. Delete.
- **`adjusted_max_buy` helper**: dead in production (was only called by `apply_premium_adjustment`); co-dead with parent. Delete bundled.
- **`analyzer_config.premium_model.*` subtree**: zero live consumers since A.2. Decision needed: wire the hardcoded constants in `calculate_presentation_premium` to read from the subtree, or remove the subtree. Decision previously blocked on B.3 lookback externalization; B.3 shipped without externalizing, so lean is remove.
- **`premium_model.min_trade_count` hardcoded 10** in `calculate_presentation_premium`: resolves if the parent function gets removed in this cleanup sweep.

### Triggers on Phase D start (added during B.7)

- **Per-target hardcoded `papers_required: True` in `build_brief.py:214`**: each target entry hardcodes True regardless of `sourcing_rules.papers_required`. The B.7 footer fix corrected the markdown footer (line 275); the per-target field is out of scope for that fix and lives inside the broader sourcing_brief surface that Phase D replaces. Fix or remove with the JSON brief deprecation.

### Triggers on Phase C start

- `resolved_cache_ref` null-in-pipeline artifact (low priority)
- Pipeline `today` threading (historical cycle replay)
- References below `min_sales_for_scoring` that are actively traded (M21010 and similar)
- March 2026 pre-A.6 ledger rows with blank `buy_date`

### Triggers on Phase D start

- Cowork KNOWN_ISSUES #2 (`is_cycle_focus_current` logic)
- Cowork KNOWN_ISSUES #3 (`sourcing_brief` path mismatch, now deprecated with B.7 CSV shortlist)

### Triggers before Z.1 (Honeycomb wire-up)

- Cowork OTEL audit and instrumentation
- Strategy-docs migration to `cycle_focus.json`; remove bundle alias

### Triggers on Schema v2 work (post-Phase D)

- `QUALITY_CONDITIONS` externalization to schema
- `us_inventory_only` + `never_exceed_max_buy` promotion to config
- Schema doc v1 vs v1_1 consolidation
- `condition_mix` enum revision (excellent bucket empty, vintage separate)
- Per-condition medians (v2.0 territory)

### Opportunistic cleanup (no hard trigger)

- `--name-cache` threading decision in `backfill_ledger`
- Per-hook failure granularity in `hook_failed` span
- `RUN_HISTORY_PATH` unused import in `write_cache.py:32`
- Test hermeticity: 26 callers of `build_outbound_bundle(tmp_path)` rely on real repo state
- Pro report data quality (inventory-suffixed refs in source CSV)
- Duplicate M79000N-0002 ledger row

### Resolved (for record)

Phase A cleanup items (A.cleanup.1 through A.cleanup.3) all landed. M-prefix ledger reference normalization resolved. Schema doc staleness on B.2/B.3 resolved. Exhaustive-shape test anti-pattern addressed during B.5. B.6 shipped then reverted per 2026-04-23 kill. B.7 shortlist CSV shipped 2026-04-22 with brand_floors default record (Phase 0) and build_brief markdown footer `papers_required` linkage fix bundled.

---

## 7. Verification items for first session using this document

Remove entries as each is confirmed. Add new entries only for verifications needed before the next session can rely on a section.

(All prior verification items closed by B.7 Phase 0 on 2026-04-22: `state/brand_floors.json` carries the five named brand floors plus a top-level `default` record at 10% for unlisted brands.)

---

*End of document.*
