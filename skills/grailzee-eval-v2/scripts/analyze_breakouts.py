"""Detect breakout references between two scored periods.

New in v2 per guide Section 7.3. A breakout is a reference present in
both periods that triggers one or more notable-move signals: large
median shift, volume surge, or sell-through spike.

Usage:
    analyze_breakouts.py <curr_csv> [<prev_csv>] [--name-cache PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import NAME_CACHE_PATH, get_tracer
from scripts.analyze_references import run as score_csvs

tracer = get_tracer(__name__)

MEDIAN_BREAKOUT_PCT = 8.0   # >8% median move
VOLUME_SURGE_FACTOR = 2     # current > prev * 2
VOLUME_MIN_PREV = 3         # prev must have >= 3 sales for volume signal
ST_BREAKOUT_PP = 15.0       # >15 percentage points sell-through increase


def detect_breakouts(curr_refs: dict, prev_refs: dict) -> list[dict]:
    """Detect breakout references across two scored periods.

    Only considers references present in BOTH periods (emerged refs
    are handled by analyze_changes, not breakouts).

    A reference qualifies as a breakout if it triggers one or more
    signals. One signal suffices.

    Returns list of {"reference": str, "signals": [str, ...]}.
    """
    breakouts = []
    for ref in sorted(set(curr_refs) & set(prev_refs)):
        current = curr_refs[ref]
        prev = prev_refs[ref]
        signals = []

        # Median move >8%
        prev_median = prev.get("median", 0)
        if prev_median:
            median_delta = ((current["median"] - prev_median) / prev_median) * 100
            if abs(median_delta) > MEDIAN_BREAKOUT_PCT:
                sign = "+" if median_delta > 0 else ""
                signals.append(f"Median {sign}{median_delta:.1f}%")

        # Volume surge: >2x with prior >= 3
        prev_vol = prev.get("volume", 0)
        curr_vol = current.get("volume", 0)
        if curr_vol > prev_vol * VOLUME_SURGE_FACTOR and prev_vol >= VOLUME_MIN_PREV:
            signals.append(f"Volume surge ({prev_vol} \u2192 {curr_vol})")

        # Sell-through spike: >15pp
        curr_st = current.get("st_pct")
        prev_st = prev.get("st_pct")
        if curr_st is not None and prev_st is not None:
            st_delta = round((curr_st - prev_st) * 100, 4)
            if st_delta > ST_BREAKOUT_PP:
                signals.append(f"Sell-through +{st_delta:.0f}pp")

        if signals:
            breakouts.append({"reference": ref, "signals": signals})

    return breakouts


# ─── CLI entry ────────────────────────────────────────────────────────


def run(
    curr_csv: str,
    prev_csv: str | None = None,
    name_cache_path: str | None = None,
) -> dict:
    """Score current and previous CSVs, detect breakouts."""
    curr_result = score_csvs([curr_csv], name_cache_path)
    curr_refs = curr_result.get("references", {})

    prev_refs: dict = {}
    if prev_csv:
        prev_result = score_csvs([prev_csv], name_cache_path)
        prev_refs = prev_result.get("references", {})

    breakouts = detect_breakouts(curr_refs, prev_refs)
    return {"breakouts": breakouts, "count": len(breakouts)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("curr_csv", help="Current period CSV")
    parser.add_argument("prev_csv", nargs="?", default=None,
                        help="Previous period CSV (omit for first report)")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_breakouts.run") as span:
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
        span.set_attribute("breakout_count", result["count"])

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
