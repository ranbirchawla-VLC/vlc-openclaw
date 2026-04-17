"""Detect emerged, shifted, faded, and unnamed references between two periods.

New in v2 per guide Section 7.2. No v1 equivalent (v1 had "discoveries"
against a hardcoded CORE_REFERENCES list; v2 compares any two scored
periods).

Usage:
    analyze_changes.py <curr_csv> [<prev_csv>] [--name-cache PATH]
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

from scripts.grailzee_common import NAME_CACHE_PATH, get_tracer, load_name_cache
from scripts.analyze_references import run as score_csvs

tracer = get_tracer(__name__)

SHIFTED_THRESHOLD_PCT = 5.0  # >5% median move = shifted


def detect_changes(
    curr_refs: dict,
    prev_refs: dict,
    name_cache: dict,
) -> dict:
    """Categorize references into emerged, shifted, faded, unnamed.

    curr_refs, prev_refs: score_all_references()["references"] dicts.
    name_cache: loaded name_cache.json dict.

    Returns {
        "emerged": [ref, ...],
        "shifted": {ref: {"direction": "up"|"down", "pct": float}},
        "faded": [ref, ...],
        "unnamed": [ref, ...],
    }
    """
    curr_keys = set(curr_refs.keys())
    prev_keys = set(prev_refs.keys())

    # Emerged: in current, not in previous
    emerged = sorted(curr_keys - prev_keys)

    # Faded: in previous, not in current
    faded = sorted(prev_keys - curr_keys)

    # Shifted: in both, median moved >5%
    shifted = {}
    for ref in sorted(curr_keys & prev_keys):
        curr_median = curr_refs[ref].get("median", 0)
        prev_median = prev_refs[ref].get("median", 0)
        if prev_median == 0:
            continue
        pct = ((curr_median - prev_median) / prev_median) * 100
        if abs(pct) > SHIFTED_THRESHOLD_PCT:
            shifted[ref] = {
                "direction": "up" if pct > 0 else "down",
                "pct": round(pct, 1),
            }

    # Unnamed: scored in current but not in name cache
    unnamed = sorted(ref for ref in curr_keys if ref not in name_cache)

    return {
        "emerged": emerged,
        "shifted": shifted,
        "faded": faded,
        "unnamed": unnamed,
    }


# ─── CLI entry ────────────────────────────────────────────────────────


def run(
    curr_csv: str,
    prev_csv: str | None = None,
    name_cache_path: str | None = None,
) -> dict:
    """Score current (and optionally previous) CSV, detect changes."""
    name_cache = load_name_cache(name_cache_path)
    curr_result = score_csvs([curr_csv], name_cache_path)
    curr_refs = curr_result.get("references", {})

    prev_refs: dict = {}
    if prev_csv:
        prev_result = score_csvs([prev_csv], name_cache_path)
        prev_refs = prev_result.get("references", {})

    return detect_changes(curr_refs, prev_refs, name_cache)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("curr_csv", help="Current period CSV")
    parser.add_argument("prev_csv", nargs="?", default=None,
                        help="Previous period CSV (omit for first report)")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args()

    with tracer.start_as_current_span("analyze_changes.run") as span:
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
        span.set_attribute("emerged_count", len(result["emerged"]))
        span.set_attribute("shifted_count", len(result["shifted"]))
        span.set_attribute("faded_count", len(result["faded"]))
        span.set_attribute("unnamed_count", len(result["unnamed"]))

        print(json.dumps(result, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
