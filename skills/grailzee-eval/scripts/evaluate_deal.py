"""Single deal evaluation for Grailzee v2.

Takes brand + reference + purchase price, reads the analysis cache,
enriches with ledger confidence and cycle alignment, and returns a
structured recommendation as JSON.

Extracted and refactored from v1 evaluate_deal.py. Decision logic
preserved; v2 adds confidence enrichment, cycle focus annotation,
and premium status surfacing.

Usage:
    python3 evaluate_deal.py <brand> <reference> <purchase_price>
        [--cache PATH] [--ledger PATH] [--cycle-focus PATH]
        [--reports-csv-dir PATH]

Output: JSON to stdout
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    CACHE_PATH,
    CACHE_SCHEMA_VERSION,
    CSV_PATH,
    CYCLE_FOCUS_PATH,
    LEDGER_PATH,
    NR_FIXED,
    RES_FIXED,
    get_ad_budget,
    get_tracer,
    load_analyzer_config,
    load_cycle_focus,
    normalize_ref,
    match_reference,
    strip_ref,
)

from scripts import analyze_references
from scripts import read_ledger

tracer = get_tracer(__name__)


# ─── CLI argument parsing ────────────────────────────────────────────


def _parse_price_arg(s: str) -> float:
    """Parse CLI price argument. Strips $ and commas. Raises ValueError."""
    return float(s.replace("$", "").replace(",", ""))


# ─── Cache loading ───────────────────────────────────────────────────


def _load_cache(cache_path: str) -> tuple[dict | None, dict | None]:
    """Load and validate analysis_cache.json.

    Returns (cache_dict, None) on success.
    Returns (None, error_response_dict) on missing file or stale schema.
    """
    if not os.path.exists(cache_path):
        return None, {
            "status": "error",
            "error": "no_cache",
            "message": (
                f"No analysis cache found at {cache_path}. "
                "Run the full Grailzee analyzer first to generate the cache."
            ),
        }

    with open(cache_path, "r") as f:
        cache = json.load(f)

    schema_version = cache.get("schema_version", 0)
    if schema_version < CACHE_SCHEMA_VERSION:
        return None, {
            "status": "error",
            "error": "stale_schema",
            "message": (
                f"Cache schema version {schema_version} is below required "
                f"version {CACHE_SCHEMA_VERSION}. Re-run the full analyzer."
            ),
        }

    return cache, None


# ─── Reference lookup in cache ───────────────────────────────────────


def _find_reference(
    cache: dict, brand: str, reference: str,
) -> tuple[str | None, dict | None]:
    """Multi-pass cache lookup for a reference.

    Uses normalize_ref and strip_ref from grailzee_common for
    normalization. match_reference handles substring comparisons
    in passes 3-4.

    The cache-iteration loop lives here because match_reference
    operates on individual string pairs, not cache dicts.

    Pass 1: exact normalized reference match on cache keys
    Pass 2: stripped reference match on cache keys
    Pass 3: brand-filtered + match_reference substring matching
    Pass 4: dj_configs section via match_reference

    Returns (cache_key, entry) or (None, None).
    """
    refs = cache.get("references", {})
    norm_ref = normalize_ref(reference)
    stripped = strip_ref(reference)
    brand_upper = brand.strip().upper()

    # Pass 1: exact normalized match on keys
    for key, entry in refs.items():
        if normalize_ref(key) == norm_ref:
            return key, entry

    # Pass 2: stripped match on keys
    for key, entry in refs.items():
        if strip_ref(key) == stripped:
            return key, entry

    # Pass 3: brand-filtered + match_reference for substring matching
    for key, entry in refs.items():
        if entry.get("brand", "").upper() != brand_upper:
            continue
        if match_reference(reference, key):
            return key, entry

    # Pass 4: dj_configs section
    for key, entry in cache.get("dj_configs", {}).items():
        if match_reference(reference, entry.get("reference", "")):
            return key, entry

    return None, None


# ─── On-demand analysis from CSV ─────────────────────────────────────


def _find_latest_csv(reports_csv_dir: str) -> str | None:
    """Find most recent grailzee_YYYY-MM-DD.csv by filename sort."""
    pattern = os.path.join(reports_csv_dir, "grailzee_*.csv")
    files = glob.glob(pattern)
    if not files:
        return None
    # Filename date sorting gives chronological order
    return sorted(files)[-1]


def _on_demand_analysis(
    brand: str, reference: str, reports_csv_dir: str,
) -> dict | None:
    """Score one reference from the latest CSV.

    Uses analyze_references.load_sales_csv for loading and
    analyze_references.analyze_reference for scoring. No scoring
    logic duplicated here.

    Returns a cache-shaped entry dict with _source="on_demand",
    or None if fewer than 2 matching sales found.
    """
    csv_path = _find_latest_csv(reports_csv_dir)
    if csv_path is None:
        return None

    all_sales = analyze_references.load_sales_csv(csv_path)
    matching = [
        s for s in all_sales
        if match_reference(s.get("reference", ""), reference)
    ]

    if len(matching) < 2:
        return None

    scored = analyze_references.analyze_reference(matching)
    if scored is None:
        return None

    return {
        "brand": brand,
        "model": "",
        "reference": reference,
        "section": "on_demand",
        "named": False,
        "median": scored["median"],
        "max_buy_nr": scored["max_buy_nr"],
        "max_buy_res": scored["max_buy_res"],
        "risk_nr": scored["risk_nr"],
        "signal": scored["signal"],
        "volume": scored["volume"],
        "st_pct": scored["st_pct"],
        "momentum": None,
        "confidence": None,
        "trend_signal": "No history",
        "trend_median_change": 0,
        "trend_median_pct": 0,
        "floor": scored.get("floor"),
        "recommend_reserve": scored.get("recommend_reserve", False),
        "_source": "on_demand",
        "_report": os.path.basename(csv_path),
        "_sale_count": scored["volume"],
    }


# ─── Confidence enrichment ───────────────────────────────────────────


def _enrich_confidence(
    brand: str, reference: str,
    ledger_path: str | None, cache_path: str | None,
) -> dict | None:
    """Read trade ledger for reference confidence scoring.

    Delegates to read_ledger.reference_confidence(). No caching;
    the ledger CSV is structurally small (sub-millisecond reads).
    """
    return read_ledger.reference_confidence(
        ledger_path=ledger_path,
        cache_path=cache_path,
        brand=brand,
        reference=reference,
    )


# ─── Cycle focus alignment ──────────────────────────────────────────


def _check_cycle_alignment(
    reference: str,
    cycle_focus_path: str | None,
    cache_cycle_id: str | None,
) -> dict:
    """Check cycle_focus.json for cycle alignment.

    Returns a dict with: state, cycle_id_current, cycle_id_focus,
    in_targets, note.

    States: "in_cycle", "off_cycle", "no_focus", "stale_focus", "error".
    """
    path = cycle_focus_path or CYCLE_FOCUS_PATH
    if not os.path.exists(path):
        return {
            "state": "no_focus",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "in_targets": False,
            "note": None,
        }

    try:
        with open(path, "r") as f:
            focus = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "state": "error",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "in_targets": False,
            "note": f"cycle_focus.json parse error: {exc}",
        }

    focus_cycle_id = focus.get("cycle_id")
    if focus_cycle_id is None:
        return {
            "state": "error",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "in_targets": False,
            "note": "cycle_focus.json missing cycle_id key",
        }

    # Check staleness
    if focus_cycle_id != cache_cycle_id:
        return {
            "state": "stale_focus",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": focus_cycle_id,
            "in_targets": False,
            "note": (
                f"Cycle focus is for {focus_cycle_id}, "
                f"current cycle is {cache_cycle_id}"
            ),
        }

    # Current focus; check if reference is in targets
    targets = focus.get("targets", [])
    target_refs = []
    for t in targets:
        if isinstance(t, dict):
            target_refs.append(t.get("reference", ""))
        else:
            target_refs.append(str(t))

    in_targets = any(
        match_reference(reference, tr) for tr in target_refs
    )

    if in_targets:
        return {
            "state": "in_cycle",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": focus_cycle_id,
            "in_targets": True,
            "note": None,
        }

    return {
        "state": "off_cycle",
        "cycle_id_current": cache_cycle_id,
        "cycle_id_focus": focus_cycle_id,
        "in_targets": False,
        "note": "Reference not in current hunting list",
    }


# ─── Decision logic ─────────────────────────────────────────────────


def _score_decision(entry: dict, purchase_price: float) -> dict:
    """Core YES/NO/MAYBE decision logic. Pure function.

    All v1 decision branches preserved:
    - Signal=Pass -> NO
    - Price > max_buy -> NO
    - Near-ceiling MAYBE (> 0.98 * max_buy, signal not Strong)
    - Careful/Reserve route-to-Reserve MAYBE
    - Well-below-max strong YES (<= 0.90 * max_buy)
    - Within-max YES

    Returns dict with: grailzee, format, max_buy, fixed_cost,
    margin_dollars, margin_pct, vs_max_buy, vs_median_pct,
    reason, reserve_price.
    """
    median = entry["median"]
    max_buy_nr = entry["max_buy_nr"]
    max_buy_res = entry["max_buy_res"]
    risk_nr = entry.get("risk_nr")
    signal = entry["signal"]

    # recommend_reserve is computed at evaluation time from risk_nr and
    # the current risk_reserve_threshold_fraction (analyzer_config.json
    # scoring section). The cache does not store this field; it is
    # derived here so the threshold can evolve without cache regeneration.
    # Strategy edits to the threshold change format recommendations for
    # all future evaluations, even against existing cache data.
    risk_reserve_threshold = load_analyzer_config()["scoring"][
        "risk_reserve_threshold_fraction"
    ]
    recommend_reserve = (
        risk_nr is not None and risk_nr > risk_reserve_threshold * 100
    )

    # Determine initial format and effective MAX BUY
    if recommend_reserve:
        fmt = "Reserve"
        max_buy = max_buy_res
        fixed_cost = RES_FIXED
    else:
        fmt = "NR"
        max_buy = max_buy_nr
        fixed_cost = NR_FIXED

    # Price evaluation
    margin_dollars = median - purchase_price - fixed_cost
    margin_pct = (
        (margin_dollars / purchase_price * 100) if purchase_price > 0 else 0
    )
    vs_max_buy = purchase_price - max_buy
    vs_median_pct = (
        ((median - purchase_price) / median * 100) if median > 0 else 0
    )

    brand = entry.get("brand", "")
    model = entry.get("model", entry.get("reference", ""))
    reserve_price = None

    # ── Decision branches ──

    if signal == "Pass":
        grailzee = "NO"
        reason = (
            f"Risk is too high on {brand} {model}. "
            f"Signal is {signal} with {risk_nr:.0f}% of VG+ sales "
            f"below breakeven."
        )

    elif purchase_price > max_buy:
        over_by = purchase_price - max_buy
        grailzee = "NO"
        reason = (
            f"Price is ${over_by:,.0f} over MAX BUY (${max_buy:,.0f}). "
            f"At ${purchase_price:,.0f} the margin is {margin_pct:.1f}%, "
            f"below the 5% target."
        )

    elif purchase_price > max_buy * 0.98 and signal != "Strong":
        grailzee = "MAYBE"
        reason = (
            f"Price is near the MAX BUY ceiling (${max_buy:,.0f}) and "
            f"signal is {signal}. Margin at median is {margin_pct:.1f}%. "
            f"Tight; only worth it on a clean piece with papers."
        )

    elif signal in ("Careful", "Reserve") and not recommend_reserve:
        # MAYBE: signal indicates elevated risk (20-50%) but below the
        # Reserve threshold (risk_reserve_threshold_fraction * 100 = 40%).
        # The 20-40% risk band means the reference has too much VG+ downside
        # for confident NR listing but not enough to auto-route to Reserve.
        # Recommendation: list on Reserve account instead. This covers
        # both "Reserve" signal (risk 20-30%) and lower-band "Careful"
        # signal (risk 30-40%).
        grailzee = "MAYBE"
        fmt = "Reserve"
        max_buy = max_buy_res
        fixed_cost = RES_FIXED
        margin_dollars = median - purchase_price - fixed_cost
        margin_pct = (
            (margin_dollars / purchase_price * 100)
            if purchase_price > 0 else 0
        )
        reason = (
            f"Signal is {signal} ({risk_nr:.0f}% VG+ risk). "
            f"Price works at ${purchase_price:,.0f} but route to "
            f"Reserve account, not branded NR."
        )

    else:
        grailzee = "YES"
        if purchase_price <= max_buy * 0.90:
            reason = (
                f"Strong buy. ${purchase_price:,.0f} is well below "
                f"MAX BUY (${max_buy:,.0f}), giving {margin_pct:.1f}% "
                f"margin at median. Signal is {signal}."
            )
        else:
            reason = (
                f"Buy works. ${purchase_price:,.0f} is within MAX BUY "
                f"(${max_buy:,.0f}), {margin_pct:.1f}% margin at median. "
                f"Signal is {signal}."
            )

    # Reserve price suggestion
    if fmt == "Reserve":
        reserve_price = round(
            purchase_price + fixed_cost + (purchase_price * 0.02), -1
        )

    return {
        "grailzee": grailzee,
        "format": fmt,
        "max_buy": max_buy,
        "fixed_cost": fixed_cost,
        "margin_dollars": margin_dollars,
        "margin_pct": margin_pct,
        "vs_max_buy": vs_max_buy,
        "vs_median_pct": vs_median_pct,
        "reason": reason,
        "reserve_price": reserve_price,
    }


# ─── Response builder ───────────────────────────────────────────────


def _build_response(
    entry: dict,
    decision: dict,
    purchase_price: float,
    confidence: dict | None,
    cycle_alignment: dict,
    premium_status: dict | None,
    cache_meta: dict,
    data_source: str,
) -> dict:
    """Assemble the full response dict.

    v2 response is a superset of v1. Existing v1 keys preserved
    with same semantics. New keys: confidence, cycle_focus,
    premium_status, metrics.momentum.
    """
    median = entry["median"]
    signal = entry["signal"]
    risk_nr = entry.get("risk_nr")
    st_pct = entry.get("st_pct")
    volume = entry.get("volume", 0)
    trend = entry.get("trend_signal", "Stable")

    # Build rationale with context
    reason = decision["reason"]
    context_parts = []
    if st_pct is not None:
        context_parts.append(f"Sell-through {st_pct:.0%}")
    if volume:
        context_parts.append(f"{volume} sales in period")
    if trend and trend != "Stable":
        context_parts.append(f"Trending: {trend}")
    context = ". ".join(context_parts) + "." if context_parts else ""
    rationale = f"{reason} {context}".strip()

    # On-demand data quality note
    if data_source == "on_demand":
        rationale += (
            f" NOTE: This reference is not in the core program. "
            f"Analysis based on {volume} raw sales from the report. "
            f"No sell-through or trend data available."
        )

    return {
        "status": "ok",
        "brand": entry.get("brand", ""),
        "model": entry.get("model", ""),
        "reference": entry.get("reference", ""),
        "section": entry.get("section", "references"),
        "purchase_price": purchase_price,
        "data_source": data_source,

        "grailzee": decision["grailzee"],
        "format": decision["format"],
        "reserve_price": decision["reserve_price"],
        "ad_budget": get_ad_budget(median),
        "rationale": rationale,

        "metrics": {
            "median": median,
            "max_buy": decision["max_buy"],
            "floor": entry.get("floor"),
            "margin_dollars": round(decision["margin_dollars"]),
            "margin_pct": round(decision["margin_pct"], 1),
            "risk_vg_pct": round(risk_nr, 1) if risk_nr is not None else None,
            "signal": signal,
            "sell_through": (
                f"{st_pct:.0%}" if st_pct is not None else None
            ),
            "volume": volume,
            "trend": trend,
            "vs_max_buy": round(decision["vs_max_buy"]),
            "momentum": entry.get("momentum"),
        },

        "confidence": confidence,
        "cycle_focus": cycle_alignment,
        "premium_status": premium_status,

        "cache_date": cache_meta.get("generated_at", "unknown"),
        "cache_report": cache_meta.get("source_report", "unknown"),
    }


# ─── Public entry point ─────────────────────────────────────────────


def evaluate(
    brand: str,
    reference: str,
    purchase_price: float,
    cache_path: str | None = None,
    ledger_path: str | None = None,
    cycle_focus_path: str | None = None,
    reports_csv_dir: str | None = None,
) -> dict:
    """Evaluate a single deal. Returns structured recommendation.

    All paths default to grailzee_common constants.
    Test injection via kwargs.
    """
    cache_path = cache_path or CACHE_PATH
    ledger_path = ledger_path or LEDGER_PATH
    reports_csv_dir = reports_csv_dir or CSV_PATH

    with tracer.start_as_current_span("evaluate_deal") as span:
        span.set_attribute("brand", brand)
        span.set_attribute("reference", reference)
        span.set_attribute("purchase_price", purchase_price)

        # Step 1: Load cache
        cache, error = _load_cache(cache_path)
        if error is not None:
            span.set_attribute("status", "error")
            return error

        cache_meta = {
            "generated_at": cache.get("generated_at", "unknown"),
            "source_report": cache.get("source_report", "unknown"),
        }
        cache_cycle_id = cache.get("cycle_id")
        premium_status = cache.get("premium_status")

        # Step 2: Find reference in cache
        cache_key, entry = _find_reference(cache, brand, reference)

        if entry is not None:
            data_source = "cache"
        else:
            # Step 3: On-demand analysis from CSV
            entry = _on_demand_analysis(brand, reference, reports_csv_dir)
            if entry is not None:
                data_source = "on_demand"
            else:
                # Not found anywhere. Return not_found with comp_search_hint.
                # Confidence skipped on not_found: the brand+reference came
                # from raw user text, not a verified source. Running a ledger
                # lookup against unverified input risks false matches.
                cycle_alignment = _check_cycle_alignment(
                    reference, cycle_focus_path, cache_cycle_id,
                )
                span.set_attribute("status", "not_found")
                return {
                    "status": "not_found",
                    "brand": brand,
                    "reference": reference,
                    "purchase_price": purchase_price,
                    "grailzee": "NEEDS_RESEARCH",
                    "rationale": (
                        f"No Grailzee sales data for {brand} {reference}. "
                        f"Not in the analysis cache and not found in the "
                        f"raw report. Research Chrono24 and eBay sold comps "
                        f"to establish a median, then apply the standard "
                        f"formula."
                    ),
                    "comp_search_hint": {
                        "brand": brand,
                        "reference": reference,
                        "purchase_price": purchase_price,
                        "search_queries": [
                            f"{brand} {reference} site:chrono24.com",
                            f"{brand} {reference} sold site:ebay.com",
                            f"{brand} {reference} watchrecon",
                        ],
                        "instructions": (
                            "Find 5+ recent sold prices for this reference "
                            "in VG+ condition with papers. Take the median. "
                            "Apply: MAX BUY NR = (Median - $149) / 1.05. "
                            "If purchase price is below MAX BUY, it's a buy. "
                            "If fewer than 5 comps exist, flag as "
                            "insufficient data."
                        ),
                        "formula_reminder": (
                            "MAX BUY NR = (Median - $149) / 1.05"
                        ),
                    },
                    "confidence": None,
                    "cycle_focus": cycle_alignment,
                    "premium_status": premium_status,
                    "cache_date": cache_meta["generated_at"],
                    "cache_report": cache_meta["source_report"],
                }

        # Step 4: Confidence enrichment (only on verified matches)
        confidence = _enrich_confidence(
            entry.get("brand", brand),
            entry.get("reference", reference),
            ledger_path,
            cache_path,
        )

        # Step 5: Cycle alignment
        cycle_alignment = _check_cycle_alignment(
            entry.get("reference", reference),
            cycle_focus_path,
            cache_cycle_id,
        )

        # Step 6: Decision logic
        decision = _score_decision(entry, purchase_price)

        # Step 7: Build response
        result = _build_response(
            entry, decision, purchase_price,
            confidence, cycle_alignment, premium_status,
            cache_meta, data_source,
        )

        span.set_attribute("status", "ok")
        span.set_attribute("grailzee", decision["grailzee"])
        span.set_attribute("data_source", data_source)
        return result


# ─── CLI ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate a single deal against Grailzee data"
    )
    parser.add_argument("brand", help="Watch brand (e.g. Tudor)")
    parser.add_argument("reference", help="Reference number (e.g. 79830RB)")
    parser.add_argument("purchase_price", help="Purchase price (e.g. 2750)")
    parser.add_argument("--cache", default=None, help="Path to analysis_cache.json")
    parser.add_argument("--ledger", default=None, help="Path to trade_ledger.csv")
    parser.add_argument("--cycle-focus", default=None, help="Path to cycle_focus.json")
    parser.add_argument("--reports-csv-dir", default=None, help="Path to reports_csv/")
    args = parser.parse_args()

    try:
        price = _parse_price_arg(args.purchase_price)
    except ValueError:
        print(json.dumps({
            "status": "error",
            "error": "bad_price",
            "message": f"Cannot parse price: {args.purchase_price}",
        }))
        sys.exit(1)

    result = evaluate(
        args.brand, args.reference, price,
        cache_path=args.cache,
        ledger_path=args.ledger,
        cycle_focus_path=args.cycle_focus,
        reports_csv_dir=args.reports_csv_dir,
    )
    print(json.dumps(result, indent=2, default=str))
