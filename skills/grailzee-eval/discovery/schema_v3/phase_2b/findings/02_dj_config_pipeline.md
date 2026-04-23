# 2b.I.2 — DJ Config Pipeline

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Purpose**: Map current DJ config flow; confirm G5 inheritance rule; sketch 2b bucket-construction path.

---

## Current v2 flow

```
analyze_references.score_all_references(all_sales, name_cache, sell_through)
  -> For ref == "126300": dj_sales = ref_sales  (raw sale dicts)
  -> score_dj_configs(dj_sales):
       for each sale: classify_dj_config(sale["title"]) -> config_name (e.g. "Black/Oyster")
       group by config_name
       for each config with len(sales) >= 3: analyze_reference(cfg_sales) -> market metrics
       returns: {config_name: {"brand": "Rolex", "model": f"DJ 41 {cfg_name}", "reference": "126300", ...metrics}}

write_cache.write_cache(all_results, ...):
  -> For each DJ config entry: inherit from parent 126300 entry:
       cfg_entry["premium_vs_market_pct"] = parent_pvm_pct
       cfg_entry["premium_vs_market_sale_count"] = parent_pvm_count
       cfg_entry["realized_premium_pct"] = parent_rp_pct
       cfg_entry["realized_premium_trade_count"] = parent_rp_count
  -> NOTE: confidence is NOT inherited; DJ configs compute no confidence (no ledger join for sub-configs)
```

Current DJ configs (`DJ_CONFIGS` in `grailzee_common.py`, 9 entries):
`Black/Oyster, Blue/Jubilee, Blue/Oyster, Slate/Jubilee, Slate/Oyster, Green, Wimbledon, White/Oyster, Silver`

---

## Why v2 uses raw CSV for DJ, not CanonicalRow dial_color

v2 `score_dj_configs` uses keyword matching on `title` (auction descriptor) because the raw CSV from `ingest_report.py` had no parsed `dial_color` field. This is the data-quality limitation documented in STATE §4 2026-04-23: "Auction type (NR vs Reserve) is not present in Grailzee Pro report source data... all cache signals are blended."

Phase 2a `ingest.py` resolves this: `CanonicalRow` carries `dial_color` (parsed by `parse_dial_color`), `auction_type`, and `dial_numerals`. So in v3, DJ config bucket construction does NOT need keyword matching on raw titles; it uses the standard 4-axis group-by on the CanonicalRow subset where `classify_dj_config(row.auction_descriptor) == config_name`.

---

## Field inheritance table (v2 actual -> v3 target)

| Field | v2 source | v3 source (G5 rule) |
|-------|-----------|---------------------|
| `brand` | hardcoded "Rolex" in `score_dj_configs` | reference-level (from parent 126300) |
| `model` | f"DJ 41 {cfg_name}" in `score_dj_configs` | reference-level |
| `reference` | "126300" hardcoded | reference-level |
| `named` | n/a (not in DJ configs today) | reference-level (inherited from parent) |
| `confidence` | null (no ledger join for sub-configs) | reference-level (inherit from parent 126300 confidence) |
| `premium_vs_market_pct` | inherited from parent | reference-level (inherit) |
| `premium_vs_market_sale_count` | inherited from parent | reference-level (inherit) |
| `realized_premium_pct` | inherited from parent | reference-level (inherit) |
| `realized_premium_trade_count` | inherited from parent | reference-level (inherit) |
| `median` | from `analyze_reference(cfg_sales)` | per-bucket (from DJ-filtered `CanonicalRow` subset) |
| `max_buy_nr/res` | from `analyze_reference` | per-bucket |
| `risk_nr`, `signal` | from `analyze_reference` | per-bucket |
| `volume`, `st_pct` | from `analyze_reference` | per-bucket |
| `condition_mix` | from `analyze_reference` | per-bucket |
| `capital_required_*`, `expected_net_*` | from `analyze_reference` | per-bucket |
| `trend_signal`, `trend_median_*`, `momentum` | n/a (DJ configs absent from trends today) | per-bucket null (trends run per canonical reference, not per DJ config) |

---

## v3 DJ bucket construction sketch

```python
# In analyze_buckets.py: build_dj_configs(dj_canonical_rows, parent_reference_record)
dj_classified: dict[str, list[CanonicalRow]] = defaultdict(list)
for row in dj_canonical_rows:  # all CanonicalRow where row.reference == "126300"
    cfg = classify_dj_config(row.auction_descriptor)
    if cfg is not None:
        dj_classified[cfg].append(row)

result = {}
for cfg_name, cfg_rows in dj_classified.items():
    # Same 4-axis bucket construction as regular references
    buckets = build_buckets(cfg_rows)  # reuses T2 helper
    result[cfg_name] = {
        # Inherit reference-level fields from parent
        "brand": parent_reference_record.brand,
        "model": f"DJ 41 {cfg_name}",
        "reference": "126300",
        "named": parent_reference_record.named,
        "confidence": parent_reference_record.confidence,
        "premium_vs_market_pct": parent_reference_record.premium_vs_market_pct,
        # ... other ledger-level fields from parent
        # Own buckets
        "buckets": buckets,
    }
```

---

## Confirm: inheritance rule is achievable without reshaping the DJ code path

Yes. The only change is the source of rows (CanonicalRow subset vs raw sale dicts) and the output shape (buckets dict vs flat market fields). The `classify_dj_config(auction_descriptor)` call remains unchanged; it runs on `CanonicalRow.auction_descriptor` which is the already-NBSP-normalized title. `min_sales_for_scoring=3` applies per-bucket, same as regular references.

No new code path is needed beyond reusing T2 (bucket construction helper) and T3 (per-bucket scorer). DJ bucket construction is ~10 lines on top of what T2 and T3 establish.

---

## W2 live census: 126300 buckets

From 2b.I.4 census run, 126300 has 155 rows, 24 buckets, 14 scoring-eligible. Examples:
- `Roman|res|slate`: 29 rows (eligible)
- `No Numerals|res|green`: 13 rows (eligible)
- `Roman|nr|slate`: 3 rows (eligible, exactly at threshold)
- `Diamond|res|unknown`: 2 rows (below threshold; carries `signal="Low data"`)

The keyword-based classify_dj_config split (Black/Oyster, Blue/Jubilee, etc.) and the 4-axis CanonicalRow split produce different groupings. The 4-axis buckets will carry more granularity than the 9 keyword configs. Both representations will exist in v3 (DJ config section has bucket dict; each config's rows are the CanonicalRow subset where the title keyword matches).
