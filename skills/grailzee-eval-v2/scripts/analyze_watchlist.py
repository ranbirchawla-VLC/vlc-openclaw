"""Detect watchlist references: 1-2 current sales with no prior activity.

New in v2 per guide Section 7.4. v1 labeled these "Low data" and excluded
them from the sourcing brief; v2 surfaces them as early signals worth
tracking.

A watchlist reference has 1-2 sales in the current period and either
does not appear in the prior period or had volume == 0.

Usage:
    analyze_watchlist.py <curr_csv> [<prev_csv>] [--name-cache PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import NAME_CACHE_PATH, get_tracer, normalize_ref
from scripts.analyze_references import (
    group_sales_by_reference,
    load_sales_csv,
    run as score_csvs,
)

tracer = get_tracer(__name__)

WATCHLIST_MIN_SALES = 1
WATCHLIST_MAX_SALES = 2  # inclusive; 3+ goes to scoring / emerged


def detect_watch_list(
    curr_grouped: dict[str, list[dict]],
    prev_refs: dict,
) -> list[dict]:
    """Detect references with 1-2 current sales and no prior activity.

    curr_grouped: {ref: [sale_dicts]} from group_sales_by_reference.
    prev_refs: scored references dict from score_all_references["references"].

    Returns [{"reference": str, "current_sales": int, "avg_price": float}, ...]
    sorted by reference for deterministic output.
    """
    watch: list[dict] = []
    for ref in sorted(curr_grouped):
        sales = curr_grouped[ref]
        count = len(sales)
        if count < WATCHLIST_MIN_SALES or count > WATCHLIST_MAX_SALES:
            continue
        prev = prev_refs.get(ref)
        if prev and prev.get("volume", 0) > 0:
            continue
        watch.append({
            "reference": ref,
            "current_sales": count,
            "avg_price": statistics.mean([s["price"] for s in sales]),
        })
    return watch


# --- CLI entry ────────────────────────────────────────────────────────


def run(
    curr_csv: str,
    prev_csv: str | None = None,
    name_cache_path: str | None = None,
) -> dict:
    """Load CSVs, detect watchlist references."""
    curr_sales = load_sales_csv(curr_csv)
    curr_grouped = group_sales_by_reference(curr_sales)

    prev_refs: dict = {}
    if prev_csv:
        prev_result = score_csvs([prev_csv], name_cache_path)
        prev_refs = prev_result.get("references", {})

    watchlist = detect_watch_list(curr_grouped, prev_refs)
    return {"watchlist": watchlist, "count": len(watchlist)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("curr_csv", help="Current period CSV")
    parser.add_argument("prev_csv", nargs="?", default=None,
                        help="Previous period CSV (omit for first report)")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_watchlist.run") as span:
        span.set_attribute("curr_csv", args.curr_csv)
        span.set_attribute("has_prev", args.prev_csv is not None)

        if not os.path.exists(args.curr_csv):
            print(json.dumps({"status": "error", "error": f"CSV not found: {args.curr_csv}"}),
                  file=sys.stderr)
            return 1
        if args.prev_csv and not os.path.exists(args.prev_csv):
            print(json.dumps({"status": "error", "error": f"CSV not found: {args.prev_csv}"}),
                  file=sys.stderr)
            return 1

        result = run(args.curr_csv, args.prev_csv, args.name_cache)
        span.set_attribute("watchlist_count", result["count"])

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
