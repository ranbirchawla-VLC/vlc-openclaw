"""Score all references from normalized sales CSVs.

Reads CSVs produced by ingest_report.py, groups sales by reference,
scores each reference with 3+ sales, joins name_cache for display names,
and handles DJ 126300 config breakout.

Extracted from v1 analyze_report.py (lines 254-348). Core scoring logic
(calc_risk, analyze_reference) preserved verbatim. Grouping redesigned:
v1 matched against CORE_REFERENCES; v2 scores every reference with 3+
sales per guide principle #2.

Usage:
    analyze_references.py <csv_path> [<csv_path> ...] [--name-cache PATH] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    NR_FIXED,
    RES_FIXED,
    analyzer_config_source,
    classify_dj_config,
    get_tracer,
    is_quality_sale,
    load_analyzer_config,
    load_name_cache,
    max_buy_nr as calc_max_buy_nr,
    max_buy_reserve as calc_max_buy_reserve,
    normalize_ref,
    NAME_CACHE_PATH,
    OUTPUT_PATH,
)

tracer = get_tracer(__name__)


# ─── Condition-mix bucketing (B.4) ────────────────────────────────────


_CONDITION_PRIORITY: list[tuple[str, str]] = [
    ("like new", "like_new"),
    ("very good", "very_good"),
    ("excellent", "excellent"),
    ("new", "new"),
]


def _condition_bucket(condition: str) -> str:
    """Classify a raw condition string into one of the 5 schema buckets.

    Priority-ordered substring match, case-insensitive: ``like new`` is
    checked before ``new`` so ``"Like New"`` lands in ``like_new`` and
    does not fall through. Anything that doesn't match a quality label
    (including blank/unknown) lands in ``below_quality`` — schema v1
    §3.1's 5th bucket catches the non-quality tail.
    """
    cond = (condition or "").lower().strip()
    for needle, bucket in _CONDITION_PRIORITY:
        if needle in cond:
            return bucket
    return "below_quality"


def _condition_mix(sales: list[dict]) -> dict:
    """Distribution of condition grades across ``sales``.

    Always returns the schema-fixed 5-key dict (``excellent``,
    ``very_good``, ``like_new``, ``new``, ``below_quality``), each an
    integer count. Per schema v1 §3.1, every key is present even when
    the count is zero.
    """
    mix = {
        "excellent": 0,
        "very_good": 0,
        "like_new": 0,
        "new": 0,
        "below_quality": 0,
    }
    for s in sales:
        mix[_condition_bucket(s.get("condition", ""))] += 1
    return mix


# ─── Per-reference scoring (extracted from v1 analyze_report.py) ──────


def calc_risk(quality_prices: list[float], breakeven: float) -> float | None:
    """Percentage of quality sales below breakeven.

    Extracted from v1 analyze_report.py:260-263. Returns 0-100 scale.
    Returns None if no quality prices available.
    """
    if not quality_prices:
        return None
    below = sum(1 for p in quality_prices if p < breakeven)
    return (below / len(quality_prices)) * 100


def analyze_reference(
    sales: list[dict], st_pct: float | None = None
) -> dict | None:
    """Score a single reference from its sales.

    Extracted from v1 analyze_report.py:265-299. Behavior preserved:
    same formula, same signal thresholds. recommend_reserve and the
    four signal thresholds are sourced from analyzer_config.json
    (Phase A.2); defaults match the prior hardcoded values.

    Expects sales dicts with keys: price (float), condition (str),
    papers (str). Matches v1's dict shape from parse_report().
    """
    if not sales:
        return None
    cfg = load_analyzer_config()
    scoring = cfg["scoring"]
    signal_thresholds = scoring["signal_thresholds"]
    risk_reserve_threshold = scoring["risk_reserve_threshold_fraction"]
    min_sales = scoring["min_sales_for_scoring"]

    prices = [s["price"] for s in sales]
    quality_prices = [s["price"] for s in sales if is_quality_sale(s)]
    median = statistics.median(prices)

    mb_nr = calc_max_buy_nr(median)
    be_nr = mb_nr + NR_FIXED
    risk_nr = calc_risk(quality_prices, be_nr)

    mb_res = calc_max_buy_reserve(median)
    be_res = mb_res + RES_FIXED
    risk_res = calc_risk(quality_prices, be_res)

    recommend_reserve = (
        risk_nr is not None and risk_nr > risk_reserve_threshold * 100
    )
    qc = len(quality_prices)

    if risk_nr is None or qc < min_sales:
        signal = "Low data"
    elif risk_nr <= signal_thresholds["strong_max_risk_pct"]:
        signal = "Strong"
    elif risk_nr <= signal_thresholds["normal_max_risk_pct"]:
        signal = "Normal"
    elif risk_nr <= signal_thresholds["reserve_max_risk_pct"]:
        signal = "Reserve"
    elif risk_nr <= signal_thresholds["careful_max_risk_pct"]:
        signal = "Careful"
    else:
        signal = "Pass"

    return {
        "median": median,
        "mean": statistics.mean(prices),
        "floor": min(prices),
        "ceiling": max(prices),
        "volume": len(prices),
        "st_pct": st_pct,
        "quality_count": qc,
        "max_buy_nr": mb_nr,
        "max_buy_res": mb_res,
        "breakeven_nr": be_nr,
        "breakeven_res": be_res,
        "risk_nr": risk_nr,
        "risk_res": risk_res,
        "profit_nr": median - mb_nr - NR_FIXED,
        "profit_res": median - mb_res - RES_FIXED,
        "recommend_reserve": recommend_reserve,
        "signal": signal,
        "condition_mix": _condition_mix(sales),
    }


# ─── Grouping ────────────────────────────────────────────────────────


def group_sales_by_reference(sales: list[dict]) -> dict[str, list[dict]]:
    """Group sales by normalized reference. No CORE_REFERENCES filter."""
    by_ref: dict[str, list[dict]] = defaultdict(list)
    for s in sales:
        ref = normalize_ref(s.get("reference", ""))
        if ref:
            by_ref[ref].append(s)
    return dict(by_ref)


# ─── DJ config breakout ──────────────────────────────────────────────


def score_dj_configs(dj_sales: list[dict]) -> dict[str, dict]:
    """Score DJ 126300 sales broken out by dial/bracelet config.

    Extracted from v1 analyze_report.py:325-336. Classifies each sale
    by title, scores config buckets with 3+ sales.
    """
    configs: dict[str, list[dict]] = defaultdict(list)
    for s in dj_sales:
        cfg = classify_dj_config(s.get("title", ""))
        if cfg is not None:
            configs[cfg].append(s)

    min_sales = load_analyzer_config()["scoring"]["min_sales_for_scoring"]

    result = {}
    for cfg_name, cfg_sales in configs.items():
        if len(cfg_sales) < min_sales:
            continue
        a = analyze_reference(cfg_sales)
        if a:
            result[cfg_name] = {
                "brand": "Rolex",
                "model": f"DJ 41 {cfg_name}",
                "reference": "126300",
                "section": "dj_config",
                **a,
            }
    return result


# ─── Full-dataset scoring (guide Section 7.1) ────────────────────────


def score_all_references(
    sales: list[dict],
    name_cache: dict,
    sell_through: dict[str, float] | None = None,
) -> dict:
    """Score every reference with min_sales_for_scoring+ sales.

    Returns {
        "references": {ref: {brand, model, reference, named, ...metrics}},
        "dj_configs": {config_name: {brand, model, ...metrics}},
        "unnamed": [ref, ...],
    }
    """
    sell_through = sell_through or {}
    grouped = group_sales_by_reference(sales)

    min_sales = load_analyzer_config()["scoring"]["min_sales_for_scoring"]

    references = {}
    unnamed = []
    dj_sales: list[dict] = []

    for ref, ref_sales in grouped.items():
        if len(ref_sales) < min_sales:
            continue

        st = sell_through.get(ref)
        a = analyze_reference(ref_sales, st)
        if a is None:
            continue

        # Name cache lookup
        cache_entry = name_cache.get(ref, {})
        brand = cache_entry.get("brand", ref_sales[0].get("make", "?"))
        model = cache_entry.get("model", ref)
        named = ref in name_cache

        if not named:
            unnamed.append(ref)

        references[ref] = {
            "brand": brand,
            "model": model,
            "reference": ref,
            "named": named,
            **a,
        }

        # Collect DJ 126300 sales for config breakout
        if ref == "126300" or normalize_ref(ref) == "126300":
            dj_sales = ref_sales

    # DJ config breakout
    dj_configs = {}
    if dj_sales:
        config_breakout = name_cache.get("126300", {}).get("config_breakout", False)
        if config_breakout:
            dj_configs = score_dj_configs(dj_sales)

    return {
        "references": references,
        "dj_configs": dj_configs,
        "unnamed": sorted(unnamed),
    }


# ─── CSV loading ─────────────────────────────────────────────────────


def load_sales_csv(csv_path: str) -> list[dict]:
    """Load a normalized CSV (Phase 5 output) into sale dicts.

    Maps CSV columns to the dict shape analyze_reference expects:
    {price, condition, papers, reference, make, title, sell_through_pct}
    """
    sales = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                price = float(row.get("sold_price", 0))
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue
            st_raw = row.get("sell_through_pct", "")
            st = float(st_raw) if st_raw else None
            sales.append({
                "price": price,
                "condition": row.get("condition", ""),
                "papers": row.get("papers", ""),
                "reference": row.get("reference", ""),
                "make": row.get("make", ""),
                "title": row.get("title", ""),
                "sell_through_pct": st,
            })
    return sales


def _build_sell_through_map(sales: list[dict]) -> dict[str, float]:
    """Aggregate sell-through per reference from sales rows."""
    st_map: dict[str, list[float]] = defaultdict(list)
    for s in sales:
        ref = normalize_ref(s.get("reference", ""))
        st = s.get("sell_through_pct")
        if ref and st is not None:
            st_map[ref].append(st)
    return {ref: statistics.mean(vals) for ref, vals in st_map.items() if vals}


# ─── CLI entry ────────────────────────────────────────────────────────


def run(
    csv_paths: list[str],
    name_cache_path: str | None = None,
) -> dict:
    """Load CSVs, score all references, return structured result."""
    all_sales: list[dict] = []
    for path in csv_paths:
        all_sales.extend(load_sales_csv(path))

    name_cache = load_name_cache(name_cache_path)
    sell_through = _build_sell_through_map(all_sales)

    result = score_all_references(all_sales, name_cache, sell_through)
    result["total_sales_loaded"] = len(all_sales)
    result["csv_files"] = csv_paths
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", help="Normalized CSV files")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH,
                        help="Path to name_cache.json")
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_references.run") as span:
        span.set_attribute("csv_count", len(args.csv_paths))

        for path in args.csv_paths:
            if not os.path.exists(path):
                print(json.dumps({
                    "status": "error",
                    "error": f"CSV not found: {path}",
                }), file=sys.stderr)
                return 1

        # Surface the scoring knobs that actually changed behavior during
        # this run. analyzer_config_source tells the reader whether the
        # run saw the committed file or fell back to factory defaults.
        cfg = load_analyzer_config()
        scoring = cfg["scoring"]
        span.set_attribute("analyzer_config_source", analyzer_config_source())
        span.set_attribute("min_sales_for_scoring", scoring["min_sales_for_scoring"])
        span.set_attribute(
            "risk_reserve_threshold_fraction",
            scoring["risk_reserve_threshold_fraction"],
        )
        for key, value in scoring["signal_thresholds"].items():
            span.set_attribute(f"signal_thresholds.{key}", value)

        result = run(args.csv_paths, args.name_cache)
        span.set_attribute("references_scored", len(result["references"]))
        span.set_attribute("unnamed_count", len(result["unnamed"]))
        span.set_attribute("total_sales", result["total_sales_loaded"])

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
