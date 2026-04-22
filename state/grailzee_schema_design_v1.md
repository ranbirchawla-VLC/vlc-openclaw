# Grailzee Schema Design

**From**: Schema design chat session, 2026-04-21
**Scope**: State file inventory, field-by-field schemas, write/read paths, change-propagation rules. Supersedes the gap analysis as the input to the code change step.
**Not in scope**: Python code changes. Cowork apply-path plumbing. Strategy skill changes. Bot command wiring.
**Inputs carried**: Gap analysis v1 (locked). Eight outcomes, all levers, all data-path implications.

---

## 0. How to read this

Section 1 lists every state file that will exist. New, existing-unchanged, existing-modified, deprecated.

Section 2 specs each file's schema field-by-field, with source (who writes it) and consumers (who reads it).

Section 3 covers cache and brief changes. Cache grows new fields; brief gets repurposed (see skill call S1 below).

Section 4 covers ledger evolution.

Section 5 covers change propagation: when does a config change take effect, and where is that enforced.

Section 6 lists skill calls made and why. Under the "outcome questions to you, skill calls to me" rule, Ranbir reviews these rather than being asked.

Section 7 is the migration path from the current state to this schema, without data loss.

---

## 1. State file inventory

**Strategy-writable, read-only from analyzer/bot** (the config layer):

| File | Status | Purpose |
|---|---|---|
| `analyzer_config.json` | **NEW** | Analyzer tuning parameters: windows, margin, labor, premium model, signal thresholds, scoring floors. |
| `brand_floors.json` | **NEW** | Configured brand universe. Each entry: floor pct, tradeable flag, asset class, notes. References to brands not listed get `max_buy: null`. |
| `sourcing_rules.json` | **NEW** | Condition minimum, papers requirement, keyword include/exclude lists. |
| `cycle_focus.json` | **MODIFIED** | Current cycle's finalized target list. Entries grow from reference strings to objects with stamped predictions. One file, overwritten per cycle (see retention note below). |
| `cycle_targets/cycle_<id>.json` | **NEW** | Per-cycle snapshot of `cycle_focus.json` at the moment of strategy commit. Retained indefinitely. Grading lookup reads these. |
| `capacity_context.json` | **NEW** | Hybrid: strategy writes ceilings, cowork apply writes observed counts from ledger. Analyzer reads both. |
| `monthly_goals.json` | **EXISTING, UNCHANGED** | Month-boundary strategic goals. |
| `quarterly_allocation.json` | **EXISTING, UNCHANGED** | Quarter-boundary allocation. |

**Analyzer-writable** (the math layer):

| File | Status | Purpose |
|---|---|---|
| `analysis_cache.json` | **MODIFIED** | Full reference universe with math. Per-reference entries grow new fields (premium per-ref, edge vs market, brand_floor_cleared, predicted_nr_clear, condition mix, dollar-per-hour, capital required). |
| `analyzer_shortlist.json` | **NEW** | Top N (N <= 30) references passing all gates, ranked by dollar-per-labor-hour. The chat strategy session's input artifact. Ceiling is 30; if only 4 clear, 4 ship. Zero is valid. |
| `cycle_outcome_<cycle_id>.json` | **MODIFIED** | Per-cycle trade rollup. Per-close entries grow grading fields: `buy_cycle_id`, `predicted_nr_clear_prob`, `prediction_cleared`, `graded`, `holding_days`. |
| `run_history.json` | **EXISTING, UNCHANGED** | Analyzer run audit trail. |
| `name_cache.json` | **EXISTING, UNCHANGED** | Brand/model display lookup. Pure structural, not strategic. |

**Bot-writable** (the event layer):

| File | Status | Purpose |
|---|---|---|
| `trade_ledger.csv` | **MODIFIED** | Adds `buy_date`. Renames `date_closed` to `sell_date` for clarity. Adds `buy_cycle_id` and `sell_cycle_id` as two derived columns (both stored, both explicit). |

**Deprecated**:

| File | Status | Reason |
|---|---|---|
| `sourcing_brief.json` | **DEPRECATED** | Replaced by `analyzer_shortlist.json` (chat input) + enriched `cycle_focus.json` (bot reference). Brief's markdown version can stay as an optional output artifact if useful for dealer readability; the JSON version goes away. See skill call S1. |

---

## 2. Schema-by-schema specifications

### 2.1 `analyzer_config.json`

**Writer**: strategy session via cowork apply path.
**Readers**: `run_analysis` (all analyzer phases that use tunable constants).
**Change-propagation**: cycle-boundary (next analyzer run reads the latest).

```json
{
  "schema_version": 1,
  "last_updated": "2026-04-21T...",
  "updated_by": "cycle_planning:cycle_2026-07",

  "windows": {
    "pricing_reports": 2,
    "trend_reports": 6
  },

  "margin": {
    "per_trade_target_margin_fraction": 0.05,
    "monthly_return_target_fraction": 0.10
  },

  "labor": {
    "hours_per_piece": 1.5
  },

  "premium_model": {
    "lookback_days": 30,
    "close_count_floor": 5,
    "recent_weighted": true
  },

  "scoring": {
    "min_sales_for_scoring": 3,
    "risk_reserve_threshold_fraction": 0.40,
    "signal_thresholds": {
      "strong_max_risk_pct": 10,
      "normal_max_risk_pct": 20,
      "reserve_max_risk_pct": 30,
      "careful_max_risk_pct": 50
    }
  }
}
```

Fields correspond to today's hardcoded constants in `grailzee_common.py` and `build_brief.py`. Exhaustive list; no constants stay in code once this file exists.

### 2.2 `brand_floors.json`

**Writer**: strategy session.
**Readers**: `analyze_references` (gates `max_buy` computation), `build_brief` (gates shortlist membership).
**Change-propagation**: cycle-boundary.

```json
{
  "schema_version": 1,
  "last_updated": "2026-04-21T...",
  "updated_by": "cycle_planning:cycle_2026-07",

  "brands": {
    "Rolex":     {"floor_pct": 5.0,  "tradeable": true,  "asset_class": "watch"},
    "Tudor":     {"floor_pct": 10.0, "tradeable": true,  "asset_class": "watch"},
    "Breitling": {"floor_pct": 10.0, "tradeable": true,  "asset_class": "watch"},
    "Cartier":   {"floor_pct": 10.0, "tradeable": true,  "asset_class": "watch"},
    "Omega":     {"floor_pct": 8.0,  "tradeable": true,  "asset_class": "watch"}
  }
}
```

Rules:
- A brand listed with `tradeable: true` produces `max_buy` in the cache.
- A brand listed with `tradeable: false` appears in the cache with `max_buy: null` (explicitly excluded, not merely absent).
- A brand NOT listed at all surfaces in the cache with `max_buy: null` AND is flagged in `analyzer_shortlist.unfamiliar_brands` for strategy review.
- `floor_pct` is the absolute minimum premium (realized over recent closes) required for a reference in this brand to reach the shortlist. Pass/fail gate, not a cross-disqualifier per L3.1.
- `asset_class` is extensibility bookkeeping for future non-watch work. Not computed on today.

### 2.3 `sourcing_rules.json`

**Writer**: strategy session.
**Readers**: `build_brief` / future `build_shortlist`.
**Change-propagation**: cycle-boundary.

```json
{
  "schema_version": 1,
  "last_updated": "2026-04-21T...",

  "condition_minimum": "Very Good",
  "papers_required": true,

  "keyword_filters": {
    "include": ["full set", "complete set", "box papers", "BNIB", "like new", "excellent", "very good", "AD", "authorized"],
    "exclude": ["watch only", "no papers", "head only", "international", "damaged", "for parts", "aftermarket", "rep", "homage"]
  }
}
```

Note: `platform_priority` from today's `SOURCING_RULES` dict stays hardcoded in `build_brief`. It's sourcing behavior, not math tunable. See skill call S2.

### 2.4 `cycle_focus.json`

**Writer**: strategy session (on cycle commit).
**Readers**: `evaluate_deal` (bot's "should I buy this" lookup, reads `targets[]`), `roll_cycle` (grading lookup).
**Change-propagation**: cycle-boundary. Overwritten on each strategy commit.

```json
{
  "schema_version": 2,
  "cycle_id": "cycle_2026-07",
  "cycle_date_range": {"start": "2026-04-20", "end": "2026-05-03"},
  "committed_at": "2026-04-21T...",
  "committed_by": "cycle_planning:2026-04-21",

  "capital_target": 30000,
  "volume_target": 4,
  "target_margin_fraction": 0.05,

  "targets": [
    {
      "reference": "M79230B",
      "brand": "Tudor",
      "model": "Black Bay 58",
      "max_buy_nr": 2500,
      "max_buy_res": 2450,
      "predicted_nr_clear_prob": 0.75,
      "expected_net_at_median": 420,
      "dollar_per_hour": 280,
      "capital_required": 2500,
      "notes": "High ST, warming momentum, brand floor cleared at 14%."
    }
  ],

  "brand_emphasis": ["Tudor", "Breitling"],
  "brand_pullback": ["Rolex"],
  "notes": "Focus on Tudor Black Bay family and Breitling Superocean at acquisition."
}
```

Target entry fields:
- `reference`, `brand`, `model` — identity
- `max_buy_nr`, `max_buy_res` — cycle-locked, inherited from analyzer at commit time
- `predicted_nr_clear_prob` — L6.2 binary prediction stamped at commit
- `expected_net_at_median`, `dollar_per_hour`, `capital_required` — L5.3 ranking inputs carried through for bot's decision context (B.5 removed `dollar_per_hour`; cycle_focus target shape reconciled at C.1 plan-review; see §7)
- `notes` — strategic context for the target

### 2.5 `cycle_targets/cycle_<id>.json`

**Writer**: strategy session commit (at same moment `cycle_focus.json` is written, a copy gets archived here).
**Readers**: `roll_cycle` on subsequent cycles (grading lookup by buy_cycle_id).
**Change-propagation**: write-once per cycle. Never overwritten.

**Schema**: identical to `cycle_focus.json`. The file exists purely for retention. Grading a close that bought in cycle_2026-07 needs to read `cycle_targets/cycle_2026-07.json` even when the current cycle_focus.json is on cycle_2026-09.

Write pattern: on strategy commit, cowork apply writes both `cycle_focus.json` (current working copy) and `cycle_targets/cycle_<id>.json` (archived copy). Identical content, different lifetimes.

### 2.6 `capacity_context.json`

**Writer**: hybrid.
- Strategy writes `ceilings` section on cycle commit.
- Cowork apply writes `observed` section from the ledger at bundle time, each time a bundle is built.
**Readers**: `build_shortlist` / `build_brief` (factors into ranking and surface).
**Change-propagation**: ceilings at cycle-boundary; observed counts refresh on each cowork bundle build (every time the analyzer runs).

```json
{
  "schema_version": 1,
  "cycle_id": "cycle_2026-07",

  "ceilings": {
    "written_at": "2026-04-21T...",
    "written_by": "cycle_planning:cycle_2026-07",
    "rolling_window_days": 30,
    "by_brand": {
      "Tudor":  {"max_buys": 6, "max_capital": 25000},
      "Rolex":  {"max_buys": 2, "max_capital": 30000}
    },
    "by_reference": {
      "M79230B": {"max_buys": 3, "max_capital": 8000}
    }
  },

  "observed": {
    "computed_at": "2026-04-21T...",
    "rolling_window_days": 30,
    "window_start": "2026-03-22",
    "window_end": "2026-04-21",
    "by_brand": {
      "Tudor":  {"buys_count": 4, "capital_deployed": 11200}
    },
    "by_reference": {
      "M79230B": {"buys_count": 2, "capital_deployed": 5500}
    }
  }
}
```

Rule: analyzer reads both sections, does not write either. The file can be present with only one section populated (first-cycle case: ceilings set but no observed data yet). Consumers must handle missing sections gracefully.

See skill call S3 for writer-semantics decision.

### 2.7 `analyzer_config.json` change to `cycle_focus.json`: prediction stamping

Already covered in 2.4. Flagging the interaction: `analyzer_config.premium_model.close_count_floor` controls whether per-reference realized-premium surfaces in the cache. That premium is an input the strategy session uses when computing `predicted_nr_clear_prob` for each target. The prediction number lands in `cycle_focus.targets[*].predicted_nr_clear_prob`, not in the analyzer output.

Analyzer does not predict. Strategy predicts. Analyzer grades (via `roll_cycle`).

---

## 3. Cache and shortlist changes

### 3.1 `analysis_cache.json` per-reference entry (extended)

Current entry carries: `brand`, `model`, `reference`, `named`, `median`, `max_buy_nr`, `max_buy_res`, `risk_nr`, `signal`, `volume`, `st_pct`, `momentum`, `confidence`, `trend_signal`, `trend_median_change`, `trend_median_pct`.

New fields (per locked levers):

| Field | Source | Lever |
|---|---|---|
| `brand_floor_cleared` | bool (per brand_floors.json lookup against `premium_vs_market_pct`) | L3.1 |
| `premium_vs_market_pct` | float, always present (zero-floored). Most-recent Vardalux sell vs current median: `(sell - median) / median * 100`, 1 decimal. 0.0 when no sell on reference or most-recent at/below median. Same-`sell_date` tiebreak: highest `sell_price`. DJ configs inherit parent. | L2 edge |
| `premium_vs_market_sale_count` | int, always present. Total Vardalux sales on the reference (all-time, no window). Distinguishes "zero because no data" from "zero because all clearings were at/below median". DJ configs inherit parent. | L2 edge |
| `realized_premium_pct` | float or null. 30-day windowed (`sell_date` inclusive) version of `premium_vs_market_pct`: most-recent in-window sell vs current median, same formula. Null when no in-window sell (no close-count floor). Negative values permitted (no zero-floor; differs from B.2). DJ configs inherit parent. | L2.1 |
| `realized_premium_trade_count` | int, always present. Count of Vardalux trades where `sell_date` is within the last 30 days (inclusive). DJ configs inherit parent. | L2.2 |
| `capital_required_nr` | float, always present on scored refs. `max_buy_nr + 49` (Grailzee NR platform fee only; no shipping, no cost-of-capital; strategist layers those). | L5.4 |
| `capital_required_res` | float, always present on scored refs. `max_buy_res + 99` (Grailzee Res platform fee). | L5.4 |
| `expected_net_at_median_nr` | float, always present on scored refs. `median - capital_required_nr`. Gross of shipping. Negative allowed. | L5.3 |
| `expected_net_at_median_res` | float, always present on scored refs. `median - capital_required_res`. Gross of shipping. Negative allowed. | L5.3 |
| `condition_mix` | object `{excellent: N, very_good: N, like_new: N, new: N, below_quality: N}` | L1.3 |
| `capacity_observed` | object `{by_brand: {count, capital}, by_reference: {count, capital}}` read-through from capacity_context | L4 |

Fields deprecated / repurposed:
- `apply_premium_adjustment` is removed from the pipeline entirely. `max_buy_nr` and `max_buy_res` stay at plain-median-based values always. Premium lives in `realized_premium_pct`. See gap analysis Q8.
- `max_buy_nr` and `max_buy_res` become `null` for references in brands that are either `tradeable: false` or not in `brand_floors.json` at all.

### 3.2 `analyzer_shortlist.json` (new)

**Writer**: analyzer (`build_shortlist` phase, replaces `build_brief` JSON output).
**Readers**: strategy session (chat input).
**Change-propagation**: rewritten each analyzer run.

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-21T...",
  "cycle_id": "cycle_2026-07",
  "source_cache": "analysis_cache.json",
  "ceiling": 30,

  "shortlist": [
    {
      "reference": "M79230B",
      "brand": "Tudor",
      "model": "Black Bay 58",
      "max_buy_nr": 2500,
      "max_buy_res": 2450,
      "median": 3100,
      "expected_net_at_median": 420,
      "dollar_per_hour": 280,
      "capital_required": 2500,
      "signal": "Strong",
      "trend_signal": "Momentum",
      "momentum": {"score": 2, "label": "Heating Up"},
      "realized_premium_pct": 12.3,
      "realized_premium_trade_count": 6,
      "premium_vs_market_pct": 8.5,
      "brand_floor_cleared": true,
      "brand_floor_pct": 10.0,
      "condition_mix": {"excellent": 3, "very_good": 2, "like_new": 1, "new": 0, "below_quality": 1},
      "volume": 18,
      "sell_through": 0.69,
      "capacity_observed": {
        "by_brand": {"count": 4, "capital_deployed": 11200},
        "by_reference": {"count": 2, "capital_deployed": 5500}
      }
    }
  ],

  "unfamiliar_brands": [
    {
      "brand": "Panerai",
      "reference_count": 4,
      "references": ["PAM00010", "PAM00089", "PAM01312", "PAM01359"],
      "median_price_range": [5400, 9200],
      "note": "Not in brand_floors.json. Strategy to decide whether to configure."
    }
  ],

  "summary": {
    "shortlist_size": 4,
    "shortlist_ceiling": 30,
    "references_passing_floor": 4,
    "references_scored_total": 1229,
    "unfamiliar_brand_count": 1
  }
}
```

Shortlist gate logic:
1. Reference must be in a brand listed in `brand_floors.json` with `tradeable: true`.
2. Reference's signal must not be Pass or Low data.
3. Reference's `realized_premium_pct` must be non-null AND >= `brand_floor_pct` (L3.1 floor), OR `realized_premium_pct` is null (no recent in-window sell) AND `premium_vs_market_pct` >= `brand_floor_pct` (L2 edge fallback when own-ledger has no recent clearing).
4. If more than 30 references pass, rank by `dollar_per_hour` DESC, take top 30. If fewer than 30 pass, ship what passes. (B.5 removed `dollar_per_hour`; ranking field reconciled at B.7 plan-review; see §7.)

See skill call S4 for rule 3 fallback semantics.

### 3.3 `sourcing_brief.json` deprecation

The existing brief mixed chat-input and bot-reference roles into one file. Splitting them:
- Chat input → `analyzer_shortlist.json`
- Bot reference → enriched `cycle_focus.targets` (bot reads cycle_focus, not brief)

Markdown output version of the brief can stay if it's useful for human readability on the dealer-call side, but no downstream consumer reads the JSON brief after this change. See skill call S1.

---

## 4. Ledger evolution

### 4.1 New ledger columns

Current: `["date_closed", "cycle_id", "brand", "reference", "account", "buy_price", "sell_price"]`.

New: `["buy_date", "sell_date", "buy_cycle_id", "sell_cycle_id", "brand", "reference", "account", "buy_price", "sell_price"]`.

Changes:
- `date_closed` renamed to `sell_date` for clarity.
- `buy_date` added (ISO date). Required for L6.1 grading and L6.2 holding-time analysis.
- `cycle_id` split into two explicit fields:
  - `buy_cycle_id` = `cycle_id_from_date(buy_date)` — used for grading lookup (which target-list entry stamped this trade's prediction)
  - `sell_cycle_id` = `cycle_id_from_date(sell_date)` — used for cycle_outcome rollup (which cycle the close closed in)

Both stored explicitly. Deriving at read time would work but two readers compute it twice, and an explicit column removes any ambiguity about semantics. See skill call S5.

### 4.2 Migration of existing ledger rows

Existing 14 rows have `date_closed` only. No `buy_date`. Options for backfill:
- Leave `buy_date` empty for legacy rows. Grading skips them (they predate the prediction system anyway).
- Best-effort: for the two most recent trades (the March 2026 closes), Ranbir can fill in buy_date manually if those trades had meaningful predictions to grade against. Older trades, leave empty.

Rule: missing `buy_date` on a ledger row disables grading for that row but does not remove it from cycle_outcome rollups. Rollups use `sell_date` (always present).

See skill call S6 for legacy handling.

### 4.3 `ledger_manager.log` signature change

Today: `log <brand> <ref> <account> <buy> <sell> [--date YYYY-MM-DD]`.
New: `log <brand> <ref> <account> <buy> <sell> [--buy-date YYYY-MM-DD] [--sell-date YYYY-MM-DD]`.

Defaults: if `--sell-date` omitted, use today. If `--buy-date` omitted, prompt (bot-side) or fail (script-side). No silent fallback.

---

## 5. Change-propagation rules

Each file has a change-propagation semantics; stating them explicitly prevents drift.

| File | Propagation | Rationale |
|---|---|---|
| `analyzer_config.json` | Cycle-boundary (next analyzer run picks it up). | L3.3. Cycles stable during their span. |
| `brand_floors.json` | Cycle-boundary. Off-cycle changes require explicit analyzer re-run. | L3.3. |
| `sourcing_rules.json` | Cycle-boundary. | L3.3. |
| `cycle_focus.json` | Rewritten on strategy commit. Every commit archives a copy to `cycle_targets/cycle_<id>.json`. | L6.1 grading lookup. |
| `capacity_context.json` | Ceilings at cycle-boundary. Observed counts refresh every analyzer run (hybrid). | L4.3 + cowork apply behavior. |
| `analysis_cache.json` | Rewritten on every analyzer run. | Output, not config. |
| `analyzer_shortlist.json` | Rewritten on every analyzer run. | Output. |
| `cycle_outcome_<id>.json` | Written once per cycle by `roll_cycle`. Immutable after write. | Grading record. |
| `trade_ledger.csv` | Appended by bot on sale log. | Event stream. |
| `cycle_targets/cycle_<id>.json` | Write-once. Never overwritten. | Retention for grading. |

Off-cycle change path (for any cycle-boundary file): strategy commits the new config, operator triggers an explicit cowork analyzer run, new cache and shortlist generate. Clean separation from scheduled biweekly runs.

---

## 6. Skill calls made

Per the "outcome questions to you, skill calls to me" rule, these are decisions I made rather than asked. Each has one-line rationale; flag any to revisit.

**S1. `sourcing_brief.json` deprecated; markdown optional.** The JSON brief served two roles (chat input + bot reference); splitting them is cleaner. Markdown readable version can stay if useful for human dealer-call readability; no code reads it.

**S2. Platform priority stays hardcoded in `build_brief` / `build_shortlist`.** Everything else in today's SOURCING_RULES moves to `sourcing_rules.json` config. Platform order changes rarely and is behavior, not math.

**S3. Capacity context writer semantics: hybrid.** Strategy writes ceilings (per-brand and per-reference). Cowork apply computes observed counts from the ledger at bundle build time. Both land in the same file under separate top-level keys. Analyzer reads both. Rationale: ceilings are strategic calls; observed counts are deterministic math and cowork already has the ledger in hand.

**S4. Brand-floor gate fallback when recent own-ledger data is absent.** Shortlist gate rule 3 allows `premium_vs_market_pct` to stand in for `realized_premium_pct` when no in-window (30-day) Vardalux sell exists on the reference. Rationale: absence of recent clearings shouldn't disqualify a reference whose most-recent all-time sell outperforms the Grailzee channel baseline. The all-time edge metric (B.2) is always present, so use it as the gate when the windowed metric (B.3) is null.

**S5. Ledger stores both `buy_cycle_id` and `sell_cycle_id` explicitly.** Deriving at read time works but creates two semantics for "cycle_id" on one row. Explicit is cheaper to reason about; storage cost is negligible.

**S6. Legacy ledger rows backfilled best-effort, no requirement.** Rows without `buy_date` still enter cycle_outcome rollups (using `sell_date` for sell-cycle attribution). Grading skipped for those rows. Clean fallback for the 14 existing closes.

**S7. DJ-configs inherit parent reference's brand floor.** DJ 126300 as one reference with config breakouts; Rolex floor applies to 126300 as a whole; each config gets `brand_floor_cleared: true` or `false` based on the parent. Simpler than independent floors per config breakout, which would require per-config premium tracking.

**S8. On-demand evaluation for unfamiliar brands surfaces data, no YES/NO/MAYBE.** Consistent with analyzer behavior: unfamiliar brands get data without `max_buy`. Bot's `evaluate_deal` on a reference in an unfamiliar brand returns a "surface-only" response (median, volume, sell-through, risk, but no decision verdict) and flags the brand for strategy review.

**S9. Momentum catalogue uses all 7 labels.** Cooling Fast, Cooling, Softening, Stable, Warming, Heating Up, Hot. Handoff's 6-label list gets corrected in the schema step, not renegotiated.

---

## 7. Migration path

Phases to move from current state to this schema. Each phase independently verifiable.

**Phase A — config files and ledger (pure additive, no behavior change):**
1. Create `analyzer_config.json` from current hardcoded constants. All values match today's code.
2. Create `brand_floors.json` with initial brand list: Rolex 5%, Tudor 10%, Breitling 10%, Cartier 10%, Omega 8% (per Outcome 2 working assumption). Ranbir reviews the initial list before first write.
3. Create `sourcing_rules.json` from current `SOURCING_RULES` dict (minus platform_priority).
4. Add `buy_date` column to `trade_ledger.csv`. Existing rows get empty buy_date. Update `ledger_manager.log` to accept the new arg.

At this phase, nothing breaks. Analyzer reads new configs but produces identical output (same constants, different source).

**Phase B — cache and brief (additive fields, subtractive computations):**
5. Disable `apply_premium_adjustment` call in `run_analysis`. Max_buy stays at plain-median values.
6. Add new cache fields: `brand_floor_cleared`, `premium_vs_market_pct`, `realized_premium_pct`, `realized_premium_trade_count`, `dollar_per_hour`, `expected_net_at_median`, `capital_required`, `condition_mix`, `capacity_observed`. All null for first run where the inputs don't yet exist.

   *Shipped 2026-04-21 (B.2, B.3, + normalization follow-up): `premium_vs_market_pct` is always-present float, zero-floored; sibling field `premium_vs_market_sale_count` added for null-vs-zero disambiguation; `realized_premium_pct` null means no in-window (30-day) sell — no close-count floor. Ledger-to-cache joins route through `resolve_to_cache_ref` for Tudor per-piece inventory IDs. §3.1 table is authoritative for current shape.*

   *Shipped 2026-04-22 (B.5, amended): four per-channel capital/net fields: `capital_required_{nr,res}`, `expected_net_at_median_{nr,res}`. Originally specced with a fifth field `dollar_per_hour`; removed pre-commit because `hours_per_piece` is operationally constant across references, making the divisor a rank-invariant scalar carrying no information beyond `expected_net_at_median_nr` alone. All four fields are floats, always present on scored refs (nullability deferred to B.6 brand-floor gate). `capital_required_*` uses platform-fee-only decomposition (`PLATFORM_FEE_NR=49`, `PLATFORM_FEE_RES=99`), gross of shipping; contrast with `profit_nr` / `breakeven_nr` which roll in shipping. Shipping, cost-of-capital, and other transaction costs are strategist-owned. `analyzer_config.labor.hours_per_piece` kept as dormant config pending post-Phase-B decision. §3.1 table is authoritative.*
7. Implement `build_shortlist` replacing `build_brief` JSON output. Markdown stays unchanged for now.
8. Gate `max_buy` on brand_floors: references in non-tradeable or unlisted brands get `max_buy: null`.

At this phase, bot and chat see richer data. The shortlist replaces the brief as chat input.

**Phase C — predictions and grading (operational, requires one cycle to validate):**
9. Upgrade `cycle_focus.json` target entries from strings to objects. Strategy session stamps predictions at commit.
10. Implement `cycle_targets/cycle_<id>.json` write-on-commit.
11. Extend `roll_cycle` to grade closes against target-list entries (lookup by buy_cycle_id + reference).
12. Extend cycle_outcome entries with grading fields.

At this phase, the prediction loop is live. First cycle produces first graded closes.

**Phase D — capacity context:**
13. Implement `capacity_context.json` read by analyzer. Strategy writes ceilings. Cowork apply writes observed counts at bundle time.

**Rollback**: each phase is behind a flag or a read-if-present pattern. Delete the new file, old code path resumes.

---

## 8. Items for Ranbir's review

Revised under the "outcome questions to you" rule. Only the initial brand_floors content and whether the markdown sourcing brief stays as an output need your call; everything else is locked by gap analysis or S1-S9.

1. **Initial `brand_floors.json` content.** Proposed: Rolex 5%, Tudor 10%, Breitling 10%, Cartier 10%, Omega 8%. Confirm or correct before first write. Any additional brands you want included at phase A (Grand Seiko notwithstanding)?

2. **Markdown sourcing brief: keep or drop?** If you or any dealer-call reader actually reads it, keep. If nobody does, drop and simplify `build_shortlist` to one output.

3. **Rolling window for capacity context: confirm 30 days.** Matches L4.2. Sanity check against your actual sourcing rhythm.

Everything else is a skill call I've made (S1-S9). Flag any to revisit; otherwise these carry into the code-change step.

---

*End of schema design. Ready to discuss and lock. No code changes proposed below this line until schema is locked.*
