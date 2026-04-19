"""Brand-level momentum rollups per guide Section 7.5.

New in v2; no v1 equivalent. Aggregates per-reference momentum scores
into brand-level signals: warming count, cooling count, average momentum,
and a brand signal label.

Requires 2+ scored references per brand to produce a rollup. Momentum
scores come from analyze_trends.py (Phase 7); references with no
momentum entry default to score 0 (neutral).

Usage:
    analyze_brands.py <csv_path> [<csv_path> ...] [--name-cache PATH]
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
from scripts.analyze_references import run as score_csvs
from scripts.analyze_trends import run as run_trends

tracer = get_tracer(__name__)

MIN_REFS_FOR_ROLLUP = 2


def brand_momentum(
    refs: dict[str, dict],
    momentum: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Aggregate per-reference momentum into brand-level signals.

    refs: scored references dict (all_results["references"]).
    momentum: {ref: {"score": int, "label": str}} from analyze_trends.

    Returns {brand: {"reference_count", "avg_momentum", "warming",
                     "cooling", "signal"}}
    """
    momentum = momentum or {}
    by_brand: dict[str, list[int]] = defaultdict(list)
    for ref, ref_data in refs.items():
        score = momentum.get(ref, {}).get("score", 0)
        by_brand[ref_data["brand"]].append(score)

    rollups: dict[str, dict] = {}
    for brand in sorted(by_brand):
        scores = by_brand[brand]
        if len(scores) < MIN_REFS_FOR_ROLLUP:
            continue
        warming = sum(1 for s in scores if s > 0)
        cooling = sum(1 for s in scores if s < 0)
        rollups[brand] = {
            "reference_count": len(scores),
            "avg_momentum": round(statistics.mean(scores), 1),
            "warming": warming,
            "cooling": cooling,
            "signal": (
                "Brand heating" if warming > cooling * 2 else
                "Brand cooling" if cooling > warming * 2 else
                "Mixed"
            ),
        }
    return rollups


# --- CLI entry ────────────────────────────────────────────────────────


def run(
    all_results: dict,
    trends: dict | None = None,
) -> dict:
    """Extract references and momentum, produce brand rollups."""
    refs = all_results.get("references", {})
    momentum = (trends or {}).get("momentum", {})
    rollups = brand_momentum(refs, momentum)
    return {"brands": rollups, "count": len(rollups)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", help="Normalized CSVs, newest first")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_brands.run") as span:
        span.set_attribute("csv_count", len(args.csv_paths))

        for path in args.csv_paths:
            if not os.path.exists(path):
                print(json.dumps({"status": "error", "error": f"CSV not found: {path}"}),
                      file=sys.stderr)
                return 1

        all_results = score_csvs(args.csv_paths, args.name_cache)
        trends = run_trends(args.csv_paths, args.name_cache)
        result = run(all_results, trends)
        span.set_attribute("brand_count", result["count"])

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
