"""Period comparison and momentum scoring across the rolling trend window.

Compares scored reference data between consecutive report periods and
computes per-reference momentum scores across the full trend window
(up to 6 reports, ~3 months per guide Section 6.2).

compare_periods extracted from v1 analyze_report.py:351-380.
momentum_score is new in v2 per guide Section 7.6.

Usage:
    analyze_trends.py <csv_path> [<csv_path> ...] [--name-cache PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import NAME_CACHE_PATH, get_tracer
from scripts.analyze_references import load_sales_csv, run as score_csvs

tracer = get_tracer(__name__)

MOMENTUM_LABELS = {
    -3: "Cooling Fast",
    -2: "Cooling",
    -1: "Softening",
     0: "Stable",
     1: "Warming",
     2: "Heating Up",
     3: "Hot",
}


# ─── Period comparison (extracted from v1 analyze_report.py:351-380) ──


def compare_periods(curr_refs: dict, prev_refs: dict) -> list[dict]:
    """Compare two scored-reference dicts and produce per-ref trend data.

    Expects the flat shape from score_all_references()["references"]:
    {ref: {brand, model, reference, median, st_pct, risk_nr, volume, floor, ...}}

    v1 used nested {key: {analysis: {...}}} shape; this version consumes
    the v2 flat shape. Logic otherwise preserved verbatim from v1.
    Risk-shift thresholds use v1's 20% boundary (trend detection, not
    reserve recommendation).
    """
    trends = []
    for ref, c in curr_refs.items():
        if ref not in prev_refs:
            continue
        p = prev_refs[ref]

        mc = c["median"] - p["median"]
        mp = (mc / p["median"] * 100) if p["median"] else 0

        stc = None
        if c.get("st_pct") is not None and p.get("st_pct") is not None:
            stc = (c["st_pct"] - p["st_pct"]) * 100

        signals = []
        if mp <= -5:
            signals.append("Cooling")
        elif mp >= 10:
            signals.append("Momentum")
        if stc is not None:
            if stc >= 10:
                signals.append("Demand Up")
            elif stc <= -10:
                signals.append("Demand Down")
        pr, cr = p.get("risk_nr"), c.get("risk_nr")
        if pr is not None and cr is not None:
            if pr <= 20 and cr > 20:
                signals.append("Now Reserve")
            elif pr > 20 and cr <= 20:
                signals.append("Now NR")

        trends.append({
            "reference": ref,
            "brand": c.get("brand", ""),
            "model": c.get("model", ""),
            "prev_median": p["median"],
            "curr_median": c["median"],
            "med_change": mc,
            "med_pct": round(mp, 2),
            "prev_st": p.get("st_pct"),
            "curr_st": c.get("st_pct"),
            "st_change": round(stc, 2) if stc is not None else None,
            "prev_vol": p.get("volume", 0),
            "curr_vol": c.get("volume", 0),
            "floor_change": c.get("floor", 0) - p.get("floor", 0),
            "signals": signals,
            "signal_str": " | ".join(signals) if signals else "Stable",
        })
    return trends


# ─── Momentum scoring (guide Section 7.6, new in v2) ─────────────────


def momentum_score(trend_data: list[dict]) -> dict:
    """Compute momentum score for one reference across multiple periods.

    trend_data: list of compare_periods entries for this reference,
    ordered oldest-to-newest. Each entry has med_pct and volume change.

    Returns {"score": int (-3 to 3), "label": str}.
    """
    if not trend_data:
        return {"score": 0, "label": "Stable"}

    score = 0

    # Median direction signals
    for t in trend_data:
        mp = t.get("med_pct", 0)
        if mp > 2:
            score += 1
        elif mp < -2:
            score -= 1

    # Volume trend (net direction across all periods)
    vol_changes = []
    for t in trend_data:
        vc = t.get("curr_vol", 0) - t.get("prev_vol", 0)
        vol_changes.append(vc)
    vol_trend = sum(1 if v > 0 else -1 if v < 0 else 0 for v in vol_changes)
    if vol_trend > 0:
        score += 1
    elif vol_trend < 0:
        score -= 1

    # Clamp to [-3, 3]
    score = max(-3, min(3, score))

    return {"score": score, "label": MOMENTUM_LABELS[score]}


# ─── Multi-period trend analysis ─────────────────────────────────────


def analyze_trends(scored_periods: list[dict]) -> dict:
    """Analyze trends across multiple scored periods.

    scored_periods: list of score_all_references() outputs, newest first.
    Max 6 per guide Section 6.2.

    Returns {
        "trends": [...],  (latest pair comparison)
        "momentum": {ref: {"score": int, "label": str}},
        "period_count": int,
        "note": str or None,
    }
    """
    if len(scored_periods) < 2:
        return {
            "trends": [],
            "momentum": {},
            "period_count": len(scored_periods),
            "note": "Single report, no trend history" if scored_periods else "No reports",
        }

    # Latest pair comparison
    curr = scored_periods[0].get("references", {})
    prev = scored_periods[1].get("references", {})
    latest_trends = compare_periods(curr, prev)

    # All pairwise comparisons for momentum (newest-to-oldest pairs)
    all_pairs: list[list[dict]] = []
    for i in range(len(scored_periods) - 1):
        newer = scored_periods[i].get("references", {})
        older = scored_periods[i + 1].get("references", {})
        pair_trends = compare_periods(newer, older)
        all_pairs.append(pair_trends)

    # Group trend entries by reference across all pairs
    ref_trends: dict[str, list[dict]] = defaultdict(list)
    for pair in reversed(all_pairs):  # oldest-to-newest for momentum
        for t in pair:
            ref_trends[t["reference"]].append(t)

    # Compute momentum per reference
    momentum = {}
    for ref, entries in ref_trends.items():
        momentum[ref] = momentum_score(entries)

    return {
        "trends": latest_trends,
        "momentum": momentum,
        "period_count": len(scored_periods),
        "note": None,
    }


# ─── CLI entry ────────────────────────────────────────────────────────


def run(
    csv_paths: list[str],
    name_cache_path: str | None = None,
) -> dict:
    """Load CSVs, score each as a period, analyze trends."""
    # Each CSV is one report period; score each independently
    scored_periods = []
    for path in csv_paths:
        result = score_csvs([path], name_cache_path)
        scored_periods.append(result)

    return analyze_trends(scored_periods)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", help="Normalized CSVs, newest first")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_trends.run") as span:
        span.set_attribute("csv_count", len(args.csv_paths))

        for path in args.csv_paths:
            if not os.path.exists(path):
                print(json.dumps({"status": "error", "error": f"CSV not found: {path}"}),
                      file=sys.stderr)
                return 1

        result = run(args.csv_paths, args.name_cache)
        span.set_attribute("period_count", result["period_count"])
        span.set_attribute("trend_count", len(result["trends"]))
        span.set_attribute("momentum_refs", len(result["momentum"]))

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
