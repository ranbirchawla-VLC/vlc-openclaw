# Grailzee Schema Design — Addendum v1.1

**Purpose**: Three confirmations from Ranbir and one new standing rule. Read alongside `grailzee_schema_design_v1.md`. This addendum supersedes v1 where they conflict.

---

## 1. Section 8 items confirmed

**Item 1 — Initial `brand_floors.json` content**: confirmed as proposed.

```json
{
  "schema_version": 1,
  "last_updated": "<phase-A-install-date>",
  "updated_by": "phase_a_install",
  "defaulted_fields": ["brands.Rolex.floor_pct", "brands.Tudor.floor_pct", "brands.Breitling.floor_pct", "brands.Cartier.floor_pct", "brands.Omega.floor_pct"],
  "brands": {
    "Rolex":     {"floor_pct": 5.0,  "tradeable": true, "asset_class": "watch"},
    "Tudor":     {"floor_pct": 10.0, "tradeable": true, "asset_class": "watch"},
    "Breitling": {"floor_pct": 10.0, "tradeable": true, "asset_class": "watch"},
    "Cartier":   {"floor_pct": 10.0, "tradeable": true, "asset_class": "watch"},
    "Omega":     {"floor_pct": 8.0,  "tradeable": true, "asset_class": "watch"}
  }
}
```

**Item 2 — Markdown sourcing brief**: keep. Ranbir and the dealer-call readers use it. Build step stays; the JSON version still deprecates per v1 Section 3.3.

**Item 3 — Capacity rolling window**: 30 days confirmed.

---

## 2. New standing rule: config defaults, no nulls

**Rule**: Config files never contain literal JSON `null` values. Every field has a concrete default at file creation. Fields currently at defaults are called out explicitly via a top-level `defaulted_fields` array so strategy can see at a glance what it has not yet set.

**Scope**: Applies to every config file (strategy-writable, read by analyzer/bot). Does NOT apply to cache, shortlist, or cycle_outcome files, which are data representations and legitimately carry `null` when underlying data doesn't exist (e.g., `realized_premium_pct: null` when no Vardalux sell exists in the 30-day window). Config is what SHOULD; data is what IS.

**Mechanism**:

1. Each config file has a top-level `defaulted_fields: ["dotted.path.1", "dotted.path.2", ...]` array listing which field paths are currently at their factory default.

2. When strategy writes a value through the cowork apply path, that field path is removed from `defaulted_fields`.

3. When the analyzer or bot reads the file, it can check `defaulted_fields` to know what is strategy-set vs. what is pending strategy attention.

4. The array starts populated at first-install with every field path listed. Empty array means everything is strategy-set.

**Applies to these files**:

- `analyzer_config.json` — all paths defaulted at install.
- `brand_floors.json` — all brand paths defaulted at install (per item 1 above).
- `sourcing_rules.json` — all paths defaulted at install.
- `cycle_focus.json` — default is "carry forward from last committed cycle." At first-install, defaults come from `analyzer_config.json` (target_margin_fraction) plus sensible starter values (capital_target, volume_target) Ranbir sets at Phase A.
- `monthly_goals.json`, `quarterly_allocation.json` — same carry-forward default; Phase A starter values.
- `capacity_context.json` ceilings section — defaults to "effectively unlimited" sentinels (e.g., `max_buys: 99, max_capital: 9999999`) with every path in `defaulted_fields`. Analyzer treats sentinels as "no ceiling enforced"; strategy overwrites with real numbers when cycle planning commits.

**Deprecated pattern**: the `placeholder: true` + null-values convention seen in the shipped bundle (e.g., `cycle_focus_current.json` in bundle cycle_2026-07) goes away. Placeholders get replaced by concrete defaults with `defaulted_fields` tracking.

---

## 3. Phase A task added

One task added to Phase A of the migration path (v1 Section 7):

**A.5 — Starter values for cycle/monthly/quarterly files.** At Phase A install, write initial `cycle_focus.json`, `monthly_goals.json`, `quarterly_allocation.json` with concrete starter defaults rather than placeholders. Ranbir supplies:

- `cycle_focus.capital_target` — default capital deployment per cycle
- `cycle_focus.volume_target` — default pieces per cycle
- `monthly_goals.capital_target` — monthly deployment target
- `monthly_goals.volume_target` — monthly pieces target
- `quarterly_allocation.total_capital` — quarterly capital envelope

If Ranbir wants to set these at the building chat level rather than here, the building chat prompts for them before running Phase A.5. Either way, the files never land with null values in production.

---

## 4. Items still for Ranbir

None. All three Section 8 items are resolved. Starter values in Phase A.5 can be set at the building-chat handoff — not required here.

---

*End of addendum. Schema is fully locked. Building chat reads v1 + v1.1 together.*
