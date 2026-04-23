# Grailzee Schema Design v2.0; analysis_cache.json (schema_version 3)

Supersedes `grailzee_schema_design_v1.md` and `grailzee_schema_design_v1_1.md`.
Live as of Phase 2b + fixup, branch `feature/grailzee-eval-v2`, 2026-04-24.

---

## What changed from v1/v1_1 (schema_version 2)

v1/v1_1 described a flat per-reference shape where market fields (median,
signal, volume, etc.) sat directly on each reference entry. Phase 2b moves
market fields into a per-bucket dict keyed by four-axis bucket_key.

Only `confidence` (own-ledger trade rollup) and trend/momentum remain at
reference level. Ledger-vs-market comparison (premium_vs_market,
realized_premium) is NOT in the cache; strategy session computes it at read
time against the matching bucket's median. Per-reference "dominant" values
and cross-bucket signal aggregates are NOT synthesized here; that is
judgment, and judgment lives in strategy.

The ingest pipeline (Phase 2a) introduced `CanonicalRow` as the typed row
representation. Phase 2b builds directly on `CanonicalRow` instances rather
than raw sale dicts.

---

## Keying

Four-axis bucket key per Decision Lock 2026-04-24:

    (reference, dial_numerals, auction_type, dial_color)

Serialized as all-lowercase, pipe-joined:
`f"{dial_numerals.lower()}|{auction_type.lower()}|{dial_color.lower()}"`.

- `dial_numerals` in bucket body: one of `Arabic`, `Roman`, `Diamond`, `No Numerals`; in the key: lowercased (`arabic`, `roman`, `diamond`, `no numerals`)
- `auction_type` in body: `nr` or `res`; in key: same
- `dial_color` in body: canonical string from `parse_dial_color` (already lowercase; includes `"unknown"`); in key: same

Example: `"arabic|nr|black"`.

`color=unknown` is a valid keying value (not dropped). Below-threshold buckets
(volume < `min_sales_for_scoring`) carry `signal="Low data"` and are retained.

---

## Top-level cache shape

```json
{
  "schema_version": 3,
  "generated_at": "<ISO timestamp>",
  "source_report": "<filename>",
  "cycle_id": "<cycle_id>",
  "market_window": {"pricing_reports": [...], "trend_reports": [...]},
  "premium_status": { ... },
  "references": { "<ref>": <reference_entry>, ... },
  "dj_configs": { "<cfg_name>": <reference_entry>, ... },
  "changes": { "emerged": [...], "shifted": {...}, "faded": [...] },
  "breakouts": [...],
  "watchlist": [...],
  "brands": { ... },
  "unnamed": [...],
  "summary": { ... }
}
```

---

## Reference entry shape

```json
{
  "brand": "Tudor",
  "model": "BB GMT",
  "reference": "79830RB",
  "named": true,
  "trend_signal": "Momentum",
  "trend_median_change": 200,
  "trend_median_pct": 6.67,
  "momentum": {"score": 2, "label": "Heating Up"},
  "confidence": { "trades": 3, "profitable": 3, "win_rate": 100.0, "avg_roi": 12.5, "avg_premium": null, "last_trade": "2026-04-01" },
  "buckets": {
    "arabic|nr|black": <bucket_entry>,
    "arabic|res|black": <bucket_entry>
  }
}
```

Reference-level fields (not in `buckets`):
- `brand`, `model`, `reference`, `named`; identity
- `trend_signal`, `trend_median_change`, `trend_median_pct`; cross-report trend signal, typed as `str | null`, `int | null`, `float | null`. Null when no prior cache exists for this reference (no string sentinels).
- `momentum`: `dict | null`; from `analyze_trends.py`, null when absent.
- `confidence`: `dict | null`; own-ledger trade rollup (trades, profitable, win_rate, avg_roi, avg_premium, last_trade); null when no trades match.

Not reference-level in v3 post-fixup (2b fixup 2026-04-24):
- `premium_vs_market_*` and `realized_premium_*` were removed. The ledger-vs-market comparison is a judgment synthesis (it implicitly picks a "reference median" out of multiple buckets). Strategy session computes the comparison at read time against the bucket that actually matches the ledger row's keying axes.
- "Dominant median" / "best signal across buckets" is not a cache concept. If a consumer needs a reference-level market view, it reads the bucket layer directly.

---

## Bucket entry shape

```json
{
  "dial_numerals": "Arabic",
  "auction_type": "nr",
  "dial_color": "black",
  "named_special": "panda",
  "volume": 14,
  "st_pct": 0.62,
  "condition_mix": {"near_mint": 0.21, "excellent": 0.57, "very_good": 0.14, "good": 0.07, "below_quality": 0.0},
  "signal": "Strong",
  "median": 3200.0,
  "max_buy_nr": 2910.0,
  "max_buy_res": 2770.0,
  "risk_nr": 8.0,
  "capital_required_nr": 2910.0,
  "capital_required_res": 2770.0,
  "expected_net_at_median_nr": 141.0,
  "expected_net_at_median_res": 231.0
}
```

The bucket body preserves canonical case on `dial_numerals` (e.g.
`"Arabic"`). The bucket's dict key is the all-lowercase serialized form
(`"arabic|nr|black"`).

Below-threshold bucket (volume < `min_sales_for_scoring`):
- `signal`: `"Low data"`
- `median`, `max_buy_nr`, `max_buy_res`, `risk_nr`, `capital_required_*`, `expected_net_at_median_*`: all `null`
- `volume`, `st_pct`, `condition_mix`: always populated

`named_special` is bucket metadata (not a keying axis). Longest-slug-wins
tiebreak across rows in the bucket; alphabetical tiebreak for determinism.

---

## DJ config entries

DJ config entries (`dj_configs`) follow the same reference entry shape.
Reference-level fields are:
- `brand`, `model` (`"DJ 41 {cfg_name}"`), `reference` (`"126300"`), `named`
- `confidence`: always `null` (no per-config ledger join)
- `trend_signal`, `trend_median_change`, `trend_median_pct`, `momentum`: always `null` (DJ configs have no independent trend series)

Buckets are the four-axis subsets of the DJ-filtered `CanonicalRow` set.

---

## Summary block

```json
{
  "total_references": 482,
  "emerged_count": 12,
  "breakout_count": 8,
  "watchlist_count": 24,
  "unnamed_count": 3230,
  "hot_references": 18,
  "premium_status": "3 trades, +12.5%, 7 to threshold"
}
```

Per-signal reference counts (strong/normal/reserve/caution) are not emitted
in v3 post-fixup: signal is per-bucket, and any reference-level signal
aggregate is a synthesis (a reference with a Strong `Arabic|nr|black` bucket
and a Careful `Arabic|res|black` bucket has no single signal). Consumers
that need signal counts compute them from the bucket layer.

---

## Producing modules

| Field group | Module |
|-------------|--------|
| Market fields (buckets) | `analyze_buckets.py` |
| Trend / momentum (reference-level) | `analyze_trends.py` via `write_cache.py` |
| Ledger-derived `confidence` (reference-level) | `write_cache.py` |
| Schema write | `write_cache.py` |

---

## Consumers requiring 2c restoration

- `evaluate_deal.py`; deal evaluator; bucket-aware lookup needed
- `build_shortlist.py`; strategy reading-partner; `_flatten_row` needs bucket path
- `analyze_brands.py`, `build_spreadsheet.py`, `build_summary.py`, `build_brief.py`; summary outputs; need per-bucket signal aggregation

All skipped in 2b with `@pytest.mark.skip(reason="2c-restore: ...")`.
Grep: `rg "2c-restore"` for the full list.

---

## Ledger-vs-market: strategy-session scope

Post-fixup (2026-04-24), ledger-vs-market comparison does not land in the
cache. The analyzer does not synthesize a "reference-level median" for
premium math because that would silently pick one bucket's median to
compare every ledger row against, regardless of whether the row actually
matches that bucket's axes.

Strategy session does the comparison at read time. It has the ledger row
(with its own keying axes via read_ledger enrichment) and the v3 cache
(with per-bucket medians). The comparison is: look up the matching bucket's
median, compute the delta. If no bucket matches the row's keying, strategy
notes it and moves on.

`evaluate_deal.py` returns a clean `pending_2c_restore` error on v3 caches
until 2c restores the bucket-aware lookup.
