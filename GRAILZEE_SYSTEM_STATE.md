# GRAILZEE_SYSTEM_STATE

**Repo path**: `/Users/ranbirchawla/.openclaw/workspace/GRAILZEE_SYSTEM_STATE.md`
**Branch**: `feature/grailzee-eval-v2` (single long-lived)
**Owner**: Supervisor chat updates at end of every session. Operator reviews the diff before the chat closes. Commits land on the same branch as the code changes they describe.
**Read at**: Start of every supervisor chat. Start of every Claude Code task. No inference from conversation history. This document is truth.

---

## Maintenance protocol

**Session open**: First action in every new supervisor chat or Claude Code task is to read this document. State the current cache schema and the last three entries in the decisions log back to the operator. If prior context conflicts with this document, stop and flag it. The document wins unless the operator overrides explicitly.

**Session close**: Before the chat closes or the task ships, update this document with the deltas. What changed in the cache schema, what decisions landed, what moved in or out of open work. Treat it like a git commit. Every substantive change gets recorded or it did not happen.

**Edit rules**: Sections 1, 2, 3, 5, and 6 are overwritten in place. Section 4 (decisions log) is append-only. Never delete a decision. If a decision is superseded, add a new dated entry that references and overrides the prior.

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

- **Code**: `skills/grailzee-eval-v2/scripts/` (per April 16 plan; migrates to `skills/grailzee-eval/` at Phase 22)
- **Workspace-tracked config**: `state/brand_floors.json`, `state/analyzer_config.json`, other config per A.2
- **This document**: repo root, `GRAILZEE_SYSTEM_STATE.md`

### Google Drive runtime data

Base path: `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/`

- `state/analysis_cache.json` — analyzer output, bot deal-evaluator input
- `state/cycle_focus.json` — strategy session output, bot target-list input
- `state/cycle_outcome_<cycle_id>.json` — per-cycle trade rollup
- `state/trade_ledger.csv` — append-only, Grailzee-only
- `state/name_cache.json` — reference to display-name mapping
- `reports/` — raw Excel reports (archived, never deleted)
- `reports_csv/` — converted CSVs (canonical)
- `output/` — human-readable analyzer outputs

---

## 3. Cache schema as-shipped

**Verified**: cycle_2026-06, generated 2026-04-22T11:50:18. `schema_version: 2`.

### Top-level keys

`schema_version`, `generated_at`, `source_report`, `cycle_id`, `market_window`, `premium_status`, `references`, `dj_configs`, `changes`, `breakouts`, `watchlist`, `brands`, `unnamed`, `summary`.

### Per-reference fields (present in current cache)

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

**B.6 field (present in cache, scheduled for removal per 2026-04-23 decision)**:
- `brand_floor_cleared` — will be removed on next cache regeneration after B.6 revert.

---

## 4. Decisions log (append-only)

**2026-04-16** — April 16 implementation plan locked as canonical intent. Core design principles: Python does analysis, LLM does language and reading-partner judgment. Data determines priority, no hardcoded core references. Grailzee-only ledger (NR and Reserve accounts).

**2026-04-21** — Eight outcomes locked in outcomes-and-levers session:
1. Tight, conviction-ranked watchlist with explicit reasoning
2. Realized premium tracked per brand, separate from max_buy
3. Per-brand floors, absolute and asset-class-specific
4. Capacity-aware data tracked in state, no enforcement
5. Dollar-per-labor-hour ranking; strategy does capital math
6. Every close grades the system against predictions
7. Extensibility as a design constraint, not a build target
8. State files are the contract; bot is limited-write

**2026-04-21** — Brand floors locked: Rolex 5%, Tudor 10%, Breitling 10%, Cartier 10%, Omega 8%, default 10% for unlisted. Floors are absolute per-brand thresholds, not universal.

**2026-04-21** — B.2 redirect: `premium_vs_market_pct` sourced from Vardalux own ledger (most recent sale vs current median), not market data.

**2026-04-22** — B.6 v1 shipped to cache with `brand_floor_cleared` as own-ledger-gated bool (S4 cascade: B.3 primary, B.2 fallback). Uncommitted on working tree (11 modified files pending commit at this point).

**2026-04-23** — B.6 killed from the cache. Root cause analysis: own-ledger signals absent for roughly 80% of references because Vardalux trades approximately 20% of brands appearing in Grailzee Pro reports. B.6 as shipped silently suppressed most of the universe. The brand-floor question is a strategy-session judgment, not a cache field. Action: revert B.6 code changes, regenerate cache, brand-floor logic moves to `brand_floors.json` as strategy config read by the deal evaluator at runtime.

**2026-04-23** — Strategy interface confirmed as reading-partner flow. Analyzer produces a CSV shortlist (via B.7, not yet built). Strategy session drops the CSV into Chat, LLM reads and discusses with the operator, operator marks references to keep or strike in conversation, session writes survivors to `cycle_focus.json`. Replaces priority_score tiering and the JSON sourcing brief.

**2026-04-23** — Auction type (NR vs Reserve) is not present in Grailzee Pro report source data. All cache signals (`median`, `st_pct`, `risk_nr`, `signal`) are blended across auction types. Permanent data limitation. Strategy session applies judgment to account for the blend, especially on Rolex and high-value references where Reserve weighting is heavier.

---

## 5. Open work

### Immediate: B.6 revert cascade

The working tree has 11 modified files from the B.6 v1 build. Per 2026-04-23 kill decision, these do not get committed. Revert actions:

- `git checkout` on the 11 modified files to restore B.5 state
- Regenerate `analysis_cache.json` on a current report to drop `brand_floor_cleared` from per-reference entries
- Remove B.6-specific tests; test count returns from 964 toward the pre-B.6 baseline
- `brand_floors.json` stays in place as strategy config (not an analyzer dependency after revert)

### B.7 (shortlist)

Build `build_shortlist.py` producing a CSV for the strategy session. Per 2026-04-23 decision, this replaces `sourcing_brief.json` (JSON, priority-tiered) with a CSV suitable for the reading-partner flow.

Tentative CSV columns (confirm at plan-review): brand, reference, model, signal, median, max_buy_nr, st_pct, volume, risk_nr, `premium_vs_market_pct`, `realized_premium_pct`, `realized_premium_trade_count`, `confidence.*` flattened, `keep`. Sort key configurable at strategy-session invocation.

### B.8 (watchlist rename)

Rename `watchlist` to `emergent_refs` in cache schema and downstream consumers. Low complexity, sequenced after B.7.

### Open question: `max_buy_nr_realistic`

Discussed 2026-04-23 but not locked. The proposal: one new cache field that applies a flat percentage discount to median before computing the ceiling, capturing the "need to buy 5% under median" discipline for low-sell-through references.

```
max_buy_nr_realistic = (median × (1 − discount_pct / 100) − NR_FIXED) / (1 + target_margin)
```

Decision pending: whether to add this field, what `discount_pct` to use, whether to scale discount by `st_pct` or keep flat. Operator leaning toward flat 5% discount, strategy session judges reachability in conversation. Not blocking B.7.

---

## 6. Backlog (retargeted post-B.6 kill)

From `Vardalux_Grailzee_Backlog.md` (April 21 version). Items affected by the 2026-04-23 B.6 kill are retargeted or dropped.

### Dropped or retargeted (per 2026-04-23 kill)

- **BRAND_FLOORS_FACTORY_CONTENT lift** — no longer needed as B.6 gate logic. Retarget: if the deal evaluator's runtime brand-floor lookup needs a shared constant, lift at that point. Otherwise drop.
- **B.7 HIGH/MEDIUM/LOW mapping** — moot. Reading-partner CSV flow does not tier references at analyzer time; strategy sorts the whole list.
- **B.7 top-30 ceiling vs all-HIGH-plus-MEDIUM** — moot. Strategy session decides row count per session.
- **B.7 capital_target null fallback** — simplified. Analyzer does not do capital math; strategy does.

### Triggers on B.7 build

- **Markdown footer inconsistency in `build_brief.py:207`** — fix as part of B.7's replacement.

### Triggers on post-B.6 cleanup (now triggered by B.6 revert instead)

- **`analyzer_config.premium_model.*` subtree**: zero consumers since A.2. Remove or wire per decision on B.3 lookback externalization.
- **`apply_premium_adjustment`**: dead since B.1. Delete.
- **`adjusted_max_buy`**: dead since B.1. Delete co-dead with parent.
- **`premium_model.min_trade_count`**: hardcoded 10 in `calculate_presentation_premium`. Retriggers if function is removed in the cleanup sweep.

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

Phase A cleanup items (A.cleanup.1 through A.cleanup.3) all landed. M-prefix ledger reference normalization resolved. Schema doc staleness on B.2/B.3 resolved. Exhaustive-shape test anti-pattern addressed during B.5. B.6 shipped then reverted per 2026-04-23 kill.

---

## 7. Verification items for first session using this document

Remove entries from this section after each is confirmed. Add new entries only for verifications needed before the next session can rely on a section.

- None currently. Document was written 2026-04-23 against verified repo state (HEAD 68d448e, cache cycle_2026-06 generated 2026-04-22, 964 test count in canonical env including B.6 tests).

---

*End of document.*
