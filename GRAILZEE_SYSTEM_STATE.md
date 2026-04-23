# GRAILZEE_SYSTEM_STATE

**Repo path**: `/Users/ranbirchawla/.openclaw/workspace/GRAILZEE_SYSTEM_STATE.md`
**Branch**: `feature/grailzee-eval` (single long-lived)
**Owner**: Supervisor chat updates at end of every session. Operator reviews the diff before the chat closes. Commits land on the same branch as the code changes they describe.
**Read at**: Start of every supervisor chat. Start of every Claude Code task. No inference from conversation history. This document is truth.

---

## Maintenance protocol

**Session open**: First action in every new supervisor chat or Claude Code task is to read this document. State the current cache schema and the last three entries in the decisions log back to the operator. If prior context conflicts with this document, stop and flag it. The document wins unless the operator overrides explicitly.

**Session close**: Before the chat closes or the task ships, update this document with the deltas. What changed in the cache schema, what decisions landed, what moved in or out of open work. Treat it like a git commit. Every substantive change gets recorded or it did not happen.

**Edit rules**: Sections 1, 2, 3, 5, 6, and 7 are overwritten in place. Section 4 (decisions log) is append-only. Never delete a decision. If a decision is superseded, add a new dated entry that references and overrides the prior.

---

## 1. Target architecture

The Grailzee analyzer is a deterministic Python pipeline. It reads bi-weekly Grailzee Pro reports, scores every reference with 3+ sales, and produces `analysis_cache.json` on Google Drive. After cache write, it emits a per-cycle CSV shortlist at `cycle_shortlist_<cycle_id>.csv` as the strategy-session input.

Strategy happens in Chat. The grailzee-cowork plugin copies the shortlist CSV into the outbound bundle it builds for the strategy session. Operator uploads the bundle to Chat. The strategy skill reads the CSV from inside the bundle and runs a reading-partner conversation with the operator. The LLM reads, patterns emerge, the operator marks references to keep or strike. The session writes `cycle_focus.json` as the output contract.

The Telegram bot reads `cycle_focus.json` for "what am I buying right now" and reads `analysis_cache.json` for ad-hoc deal evaluation ("should I buy this at this price").

Brand-floor judgment lives in the strategy session, not in the analyzer. Per-brand margin floors are held in `brand_floors.json` as strategy config, with a `default` record for unlisted brands. The analyzer does not compute brand-floor clearance. The deal evaluator looks up the brand's floor at runtime and computes clearance inline against the offered price.

The core split: Python does deterministic analysis, LLM does reading-partner conversation, operator holds all judgment. The April 16 implementation plan (`Grailzee_Eval_v2_Implementation.md`) is the canonical intent document and governs anything this state document does not cover.

---

## 2. Repo and file layout

### Git repo: `/Users/ranbirchawla/.openclaw/workspace`

- **Code**: `skills/grailzee-eval/scripts/` (Phase 22 migration landed 2026-04-21 commit 286d58b; v2 replaces v1, legacy deleted)
- **Workspace-tracked config**: `state/brand_floors.json`, `state/analyzer_config.json`, `state/sourcing_rules.json`, schema design docs
- **This document**: repo root, `GRAILZEE_SYSTEM_STATE.md`

### Google Drive runtime data

Base path: `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/`

- `state/analysis_cache.json`: analyzer output, bot deal-evaluator input
- `state/cycle_focus.json`: strategy session output, bot target-list input
- `state/cycle_shortlist_<cycle_id>.csv`: analyzer shortlist output, strategy-session reading-partner input (B.7)
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

### Sibling artifact: shortlist CSV (B.7)

Not a cache field. Written to `GrailzeeData/state/cycle_shortlist_<cycle_id>.csv` by `build_shortlist.run` after `write_cache.run` produces the cache. 23-column contract with the strategy session:

`brand, reference, model, signal, median, max_buy_nr, st_pct, volume, risk_nr, premium_vs_market_pct, realized_premium_pct, realized_premium_trade_count, confidence_trades, confidence_profitable, confidence_win_rate, confidence_avg_roi, confidence_avg_premium, confidence_last_trade, momentum_score, momentum_label, capital_required_nr, expected_net_at_median_nr, keep`

`confidence.*` and `momentum.*` flatten to scalar columns. Null ledger-derived fields write as empty string. `keep` is blank at generation, filled during the strategy session. Default sort `signal,volume_desc`, configurable via `--sort-key` on the standalone CLI only (not threaded through the orchestrator). Surfaced inside the cowork outbound bundle (per B.8 ship) as bare-name `cycle_shortlist.csv`. Source filename on Drive remains cycle-keyed.

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

**2026-04-23 (amended)**: Reading-partner flow mechanics clarified. The grailzee-cowork plugin (`build_bundle.py`) uses an explicit 10-role manifest, not a directory glob. The shortlist CSV is added to that manifest as role 11 in a separate cowork-side task. Operator uploads the bundle to Chat; the strategy skill reads the CSV from inside the bundle rather than receiving the CSV as a separately-dropped file. Amends the 2026-04-23 reading-partner flow entry above.

**2026-04-23**: `state/brand_floors.json` gains a `default` record with full shape `{"floor_pct": 10.0, "tradeable": true, "asset_class": "watch"}`. Deal evaluator uses this record for unlisted brands at runtime. Closes Section 7 verification item carried from the B.6 revert.

**2026-04-23**: B.7 shipped. New script `skills/grailzee-eval/scripts/build_shortlist.py` produces per-cycle CSV shortlist at `GrailzeeData/state/cycle_shortlist_<cycle_id>.csv`. 23-column contract with the strategy session. Orchestrator passes `cycle_id` (derived via `cycle_id_from_csv`) to `build_shortlist.run`; only the references sub-dict is re-read from the just-written cache file. Standalone CLI is the only path that derives `cycle_id` from the cache's own top-level field. Plan-review called for in-memory `all_references` from the orchestrator; build inverted because pre-cache `all_results` lacks B.2/B.3/B.5 enrichments, and the correct on-disk read was caught by live spot-check. Default sort `signal,volume_desc`. `--sort-key` on standalone CLI only, not threaded through the orchestrator. Null ledger-derived fields write as empty string. `build_brief.py:275` markdown footer fix landed in the same commit, reads from `sourcing_rules.papers_required` instead of hardcoding the string. Line 214 per-target hardcode stays; flagged for Phase D rework. Test count 930 to 957 on canonical Python 3.12.10. Plan projected 945; the 12-test delta is boundary coverage (unknown-sort-field, empty-references, zero-stays-zero, parent-directory creation, signal-order explicit lock). Cowork-side role 11 addition is a separate round-trip.

**2026-04-24**: B.8 shipped. Cowork plugin gains role 11 `cycle_shortlist` in `grailzee-cowork/grailzee_bundle/build_bundle.py`, sourced from Drive `state/cycle_shortlist_<cycle_id>.csv`. Loud failure at bundle-build time via the existing `_read_required` pattern when the CSV is missing. cycle_id derived from `cache["cycle_id"]` (option (b) of plan-review item 1; reuses the established line-373 pattern, no new derivation code). In-bundle arcname is bare `cycle_shortlist.csv`, matching the convention of every other in-bundle artifact (`analysis_cache.json`, `sourcing_brief.json`, `cycle_focus.json`, `trade_ledger.csv`); cycle scope carried by bundle filename and the manifest's cycle_id field. Source filename on Drive remains `cycle_shortlist_<cycle_id>.csv`. Manifest position: inserted after `latest_report_csv`, before the `previous_cycle_outcome*` block (current-cycle artifacts grouped, conditional historical block stays trailing). OTEL: `cycle_shortlist_loaded` flat boolean attribute set on the caller's ambient span via `get_current_span().set_attribute(...)` after the successful `_read_required`, silent no-op outside any span context. Mirrors the B.7-era pattern in `build_shortlist.py:217`. No new bundle-build span; cowork OTEL audit (backlog) remains the path to wrap `build_outbound_bundle` in a span and surface this attribute. Cowork test count 184 to 193 (+9: 3 manifest/path, 1 byte-fidelity, 2 loud-failure, 1 role-9 regression, 2 OTEL); existing role-set literal in `test_happy_path_builds_bundle_with_all_roles` mutated from 11 to 12 entries. Eval side regression check: 957 to 957. Live spot-check methodology: tmp GrailzeeData tree seeded by copying live Drive files into it with a stub `sourcing_brief_<cycle_id>.json` written to paper over the live role-9 gap; validates the role-11 code path against live bytes but does not validate the full live bundle build, which remains blocked on the sourcing_brief Drive-state gap (now in backlog as separate audit). Corrects the 10-role count from the 2026-04-23 amended entry; pre-B.8 actual was 11 always-present plus 1 conditional from A.7's `previous_cycle_outcome_meta`. Post-B.8: 12 always-present plus 1 conditional. Watchlist rename re-labeled from B.8 to B.9 to resolve naming collision with this ship.

**2026-04-24**: `max_buy_nr_realistic` open question closed. No new cache field. Reasoning: the question was "how does Vardalux systematically discipline buy prices when sell-through is weak," and the proposed field bakes judgment into the cache. Violates the locked April 16 principle (Python does analysis, judgment lives in strategy) and repeats the B.6 failure mode (judgment-in-cache that silently distorts consumer behavior). The cache already carries the three facts strategy needs to apply this discipline in conversation: `max_buy_nr` (formula's answer at median), `st_pct` (sell-through signal telling you how much to trust the formula), and `risk_nr` (historical probability of a sub-breakeven hammer, the strongest single signal for this specific use). All three already flatten into the shortlist CSV. Strategy applies the haircut visually during the keep/strike pass. Deal evaluator behavior unchanged; bot answers against `max_buy_nr` as today and exposes `st_pct` and `risk_nr` in its response so the operator has the facts to override in the moment. Avoids a two-ceiling problem on the bot side (which ceiling is authoritative). No code change, no schema change, no open work item.

**2026-04-24**: B.9 deferred. Discovery completed (read-only audit, 957 / 193 test counts unchanged). Discovery surfaced 16-file rename surface (5 code, 5 test, 6 live doc) plus 5 judgment calls (filename `analyze_watchlist.py`, function name `detect_watch_list`, OTEL span name `analyze_watchlist.run`, OTEL attribute `watchlist_count`, envelope key `{"watchlist": [...], "count": N}`) plus required closed-object schema-pin update at `test_write_cache.py:142`. Original Section 5 "low complexity" label was inaccurate. Reasoning for deferral: zero functional change, zero analytical-quality improvement, two higher-value items present in Ready-to-execute backlog (live sourcing_brief Drive-state gap blocking the operating loop today; cleanup trio of dead-code deletes). B.9 reclassified from Section 5 (Open work) to Section 6 (Ready to execute backlog). Discovery inventory not preserved in any committed artifact; if B.9 ever comes off backlog, plan task should attempt to locate prior discovery before re-running. Independent finding from B.9 discovery: schema design docs (`grailzee_schema_design_v1.md`, `v1_1.md`) are silent on the `watchlist` cache key entirely. Surfaced as backlog candidate for Schema v2 work, not in scope for B.9 itself. Independent finding: `.claude/progress.md:81` carries stale "B.8 - watchlist - emergent_refs" label from before the renumbering; self-correcting on next progress update.

---

## 5. Open work

No open work items. Section 5 is empty pending operator selection from Section 6 backlog.

The recommended next pick from "Ready to execute" is the live `sourcing_brief_cycle_2026-06.json` Drive-state gap. It blocks Section 7's only verification item and blocks the live reading-partner flow today. See Section 6.

---

## 6. Backlog

From `Vardalux_Grailzee_Backlog.md` (April 21 baseline), updated for the 2026-04-23 B.6 kill, revert, B.7 ship, 2026-04-24 B.8 ship, 2026-04-24 max_buy_nr_realistic closure, and 2026-04-24 B.9 deferral.

### Dropped (obsoleted by 2026-04-23 decisions)

- **BRAND_FLOORS_FACTORY_CONTENT lift**: no longer needed as B.6 gate logic. If the deal evaluator's runtime brand-floor lookup ever needs a shared constant, revisit at that point.
- **B.7 HIGH/MEDIUM/LOW mapping**: moot. Reading-partner CSV flow does not tier references at analyzer time; strategy sorts the whole list.
- **B.7 top-30 ceiling vs all-HIGH-plus-MEDIUM**: moot. Strategy session decides row count per session.
- **B.7 capital_target null fallback**: simplified. Analyzer does not do capital math; strategy does.
- **`max_buy_nr_realistic` cache field**: closed 2026-04-24. Judgment-in-cache violates architecture; strategy applies the discipline in conversation using existing `max_buy_nr`, `st_pct`, and `risk_nr`.

### Ready to execute

Order below reflects recommended priority. Sourcing_brief gap is at the top because it blocks the live operating loop. Cleanup trio second because it removes dead code that confuses future work. B.9 last because it's a cosmetic rename with no functional or analytical-quality impact.

- **Live `sourcing_brief_cycle_2026-06.json` Drive-state gap** (recommended next pick): file does not exist on Drive; live `python3 -m grailzee_bundle.build_bundle --grailzee-root <drive>` fails with `Missing sourcing_brief for cycle_2026-06` before reaching the new role-11 check. Pre-dates B.8; surfaced during B.8 live spot-check. Audit: confirm whether the per-cycle brief producer is running, or whether the per-cycle naming has drifted from what `build_bundle.py` expects. Phase D-adjacent (role 9 is slated for deprecation), but blocking the live reading-partner flow today. Recommend separate small audit task ahead of Phase D rather than folding into the larger `build_brief.py` rework.
- **`apply_premium_adjustment` dead code**: zero callers since B.1. Delete.
- **`adjusted_max_buy` helper**: dead in production (was only called by `apply_premium_adjustment`); co-dead with parent. Delete bundled.
- **`analyzer_config.premium_model.*` subtree**: zero live consumers since A.2. Decision needed: wire the hardcoded constants in `calculate_presentation_premium` to read from the subtree, or remove the subtree. Decision previously blocked on B.3 lookback externalization; B.3 shipped without externalizing, so lean is remove.
- **`premium_model.min_trade_count` hardcoded 10** in `calculate_presentation_premium`: resolves if the parent function gets removed in this cleanup sweep.
- **B.9 (watchlist rename)**: rename `watchlist` to `emergent_refs` in cache schema and downstream consumers. Discovery completed 2026-04-24 (read-only). Surface area: 16 files (5 code, 5 test, 6 live doc), excludes 1 archival doc (`Grailzee_Eval_v2_Implementation.md`). Five judgment calls: filename, function name, OTEL span name, OTEL attribute, envelope key. Required closed-object schema-pin update at `test_write_cache.py:142`. Plan task should locate prior discovery before re-running. Cosmetic rename; no functional or analytical-quality impact. Defer until Section 6 higher-value items are cleared.

### Triggers on Phase D start

- **`build_brief.py:214` per-target hardcoded `papers_required: True`**: inconsistent with line 85 sourcing_rules-driven field. Fix as part of Phase D sourcing_brief removal and `build_brief.py` broader rework. Surfaced during B.7 co-review.
- `resolved_cache_ref` null-in-pipeline artifact (low priority)
- Pipeline `today` threading (historical cycle replay)
- References below `min_sales_for_scoring` that are actively traded (M21010 and similar)
- March 2026 pre-A.6 ledger rows with blank `buy_date`
- Cowork KNOWN_ISSUES #2 (`is_cycle_focus_current` logic)
- Cowork KNOWN_ISSUES #3 (`sourcing_brief` path mismatch, now deprecated with B.7 CSV shortlist)
- Remove role 9 `sourcing_brief` from cowork bundle manifest; remove JSON emission from `build_brief.py`; update strategy skill docs

### Triggers before Z.1 (Honeycomb wire-up)

- Cowork OTEL audit and instrumentation. Two analyzer-side artifacts (`build_shortlist.run`, B.8 cowork role 11) now emit `*_loaded` attributes that fall into silent no-op without an ambient span. Audit becomes the path to wrap `build_outbound_bundle` in a span and surface these.
- Strategy-docs migration to `cycle_focus.json`; remove bundle alias

### Triggers on Schema v2 work (post-Phase D)

- `QUALITY_CONDITIONS` externalization to schema
- `us_inventory_only` + `never_exceed_max_buy` promotion to config
- Schema doc v1 vs v1_1 consolidation
- `condition_mix` enum revision (excellent bucket empty, vintage separate)
- Per-condition medians (v2.0 territory)
- **Schema-doc completeness audit**: `grailzee_schema_design_v1.md` and `v1_1.md` are silent on the `watchlist` cache key (and possibly other as-shipped fields). Surfaced by B.9 discovery 2026-04-24 as independent gap.

### Opportunistic cleanup (no hard trigger)

- `--name-cache` threading decision in `backfill_ledger`
- Per-hook failure granularity in `hook_failed` span
- `RUN_HISTORY_PATH` unused import in `write_cache.py:32`
- Test hermeticity: 26 callers of `build_outbound_bundle(tmp_path)` rely on real repo state
- Pro report data quality (inventory-suffixed refs in source CSV)
- Duplicate M79000N-0002 ledger row

### Resolved (for record)

Phase A cleanup items (A.cleanup.1 through A.cleanup.3) all landed. M-prefix ledger reference normalization resolved. Schema doc staleness on B.2/B.3 resolved. Exhaustive-shape test anti-pattern addressed during B.5. B.6 shipped then reverted per 2026-04-23 kill. B.7 shipped 2026-04-23 (shortlist CSV, brand_floors default record, build_brief footer fix). B.8 shipped 2026-04-24 (cowork role 11 cycle_shortlist, bare arcname, cycle_id from cache). `max_buy_nr_realistic` open question closed 2026-04-24 (no new cache field; judgment stays in strategy). B.9 deferred to backlog 2026-04-24 (discovery complete, deferred for prioritization reasons; not resolved, deferred).

---

## 7. Verification items for first session using this document

Remove entries as each is confirmed. Add new entries only for verifications needed before the next session can rely on a section.

- **Live cowork bundle build, end-to-end**: once the sourcing_brief Drive-state gap is resolved, confirm the first live `python3 -m grailzee_bundle.build_bundle --grailzee-root <drive>` produces a bundle containing both role 9 `sourcing_brief.json` and role 11 `cycle_shortlist.csv` with byte-fidelity to source. This is the closure on B.8's deferred full-flow validation.

---

*End of document.*
