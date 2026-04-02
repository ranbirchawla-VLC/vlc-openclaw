#!/usr/bin/env python3
"""
Vardalux Grailzee Target Query

Reads the sourcing brief JSON and returns current buy targets
with optional filtering by priority, brand, budget, and format.

This is the "what should I be buying?" endpoint. The deal evaluator
answers "should I buy THIS at THIS price?" — this answers "what should
I be hunting for right now?"

Usage:
    python3 query_targets.py                          # All HIGH priority targets
    python3 query_targets.py --priority ALL            # Everything
    python3 query_targets.py --priority HIGH           # Only HIGH
    python3 query_targets.py --brand Tudor              # Only Tudor
    python3 query_targets.py --budget 3000              # MAX BUY under $3,000
    python3 query_targets.py --format NR                # Only NR-eligible
    python3 query_targets.py --include-discoveries      # Also show discovered refs
    python3 query_targets.py --brand Tudor --budget 3000  # Combine filters

Output: JSON to stdout
"""

import sys, os, json
from datetime import datetime

# ═══ DEFAULTS ═══
GRAILZEE_ROOT = "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData"
DEFAULT_BRIEF_PATH = os.path.join(GRAILZEE_ROOT, "state", "sourcing_brief.json")

# Freshness threshold (days). Beyond this, warn that data is stale.
STALE_DAYS = 21


def load_brief(brief_path=None):
    """Load the sourcing brief. Returns (brief_dict, error_dict_or_None)."""
    brief_path = brief_path or DEFAULT_BRIEF_PATH

    if not os.path.exists(brief_path):
        return None, {
            "status": "error",
            "error": "no_brief",
            "message": (
                f"No sourcing brief found at {brief_path}. "
                "Run the full Grailzee analyzer first to generate it."
            ),
        }

    with open(brief_path, 'r') as f:
        brief = json.load(f)

    # Check freshness
    generated = brief.get("generated_at", "")
    stale_warning = None
    if generated:
        try:
            gen_dt = datetime.fromisoformat(generated)
            age_days = (datetime.now() - gen_dt).days
            if age_days > STALE_DAYS:
                stale_warning = (
                    f"Sourcing brief is {age_days} days old "
                    f"(generated {gen_dt.strftime('%B %d, %Y')}). "
                    "A new Grailzee Pro report may be available. "
                    "Run the full analyzer to refresh."
                )
        except (ValueError, TypeError):
            pass

    brief["_stale_warning"] = stale_warning
    return brief, None


def filter_targets(brief, priority=None, brand=None, budget=None,
                   fmt=None, include_discoveries=False):
    """
    Filter the target list from the sourcing brief.

    Args:
        brief: loaded sourcing_brief.json dict
        priority: "HIGH", "MEDIUM", "LOW", or "ALL" (default: HIGH)
        brand: brand name filter (case-insensitive)
        budget: max purchase price ceiling (only targets with max_buy <= budget)
        fmt: "NR" or "Reserve" filter
        include_discoveries: if True, append discovered references

    Returns: dict with filtered targets and metadata
    """
    targets = brief.get("targets", [])
    discoveries = brief.get("discoveries", [])

    # Default to HIGH if no priority specified
    if priority is None:
        priority = "HIGH"
    priority = priority.upper()

    filtered = []
    for t in targets:
        # Priority filter
        if priority != "ALL" and t.get("priority", "") != priority:
            continue
        # Brand filter
        if brand and t.get("brand", "").upper() != brand.upper():
            continue
        # Budget filter
        if budget is not None and t.get("max_buy", float('inf')) > budget:
            continue
        # Format filter
        if fmt and t.get("format", "").upper() != fmt.upper():
            continue
        filtered.append(t)

    # Sort by priority score descending, then by max_buy ascending (cheapest first)
    filtered.sort(key=lambda t: (-t.get("priority_score", 0), t.get("max_buy", 0)))

    # Discovery section (optional)
    disc_filtered = []
    if include_discoveries:
        for d in discoveries:
            if brand and d.get("brand", "").upper() != brand.upper():
                continue
            if budget is not None and d.get("max_buy", float('inf')) > budget:
                continue
            disc_filtered.append(d)

    # Build response
    stale = brief.get("_stale_warning")
    result = {
        "status": "ok",
        "generated_at": brief.get("generated_at", "unknown"),
        "source_report": brief.get("source_report", "unknown"),
        "filters_applied": {
            "priority": priority,
            "brand": brand,
            "budget": budget,
            "format": fmt,
            "include_discoveries": include_discoveries,
        },
        "target_count": len(filtered),
        "targets": [],
    }

    if stale:
        result["stale_warning"] = stale

    # Flatten each target to what the agent needs for a clean message
    for t in filtered:
        entry = {
            "brand": t.get("brand", ""),
            "model": t.get("model", ""),
            "reference": t.get("reference", ""),
            "priority": t.get("priority", ""),
            "max_buy": t.get("max_buy", 0),
            "sweet_spot": t.get("sweet_spot", 0),
            "median": t.get("median", 0),
            "format": t.get("format", "NR"),
            "signal": t.get("signal", ""),
            "trend": t.get("trend", "Stable"),
            "volume": t.get("volume", 0),
            "sell_through": t.get("sell_through"),
            "notes": t.get("notes", ""),
            "search_terms": t.get("search_terms", []),
            "platform_first": _best_platform(t),
        }
        result["targets"].append(entry)

    if disc_filtered:
        result["discoveries_count"] = len(disc_filtered)
        result["discoveries"] = [
            {
                "brand": d.get("brand", ""),
                "reference": d.get("reference", ""),
                "median": d.get("median", 0),
                "max_buy": d.get("max_buy", 0),
                "signal": d.get("signal", ""),
                "volume": d.get("volume", 0),
                "notes": d.get("notes", ""),
            }
            for d in disc_filtered
        ]

    # Add summary line for the agent to use as a Telegram header
    if filtered:
        brands_seen = sorted(set(t.get("brand", "") for t in filtered))
        price_range = (
            f"${min(t.get('sweet_spot', 0) for t in filtered):,.0f}"
            f"–${max(t.get('max_buy', 0) for t in filtered):,.0f}"
        )
        result["summary_line"] = (
            f"{len(filtered)} active target{'s' if len(filtered) != 1 else ''} "
            f"({', '.join(brands_seen)}) | Entry range: {price_range}"
        )
    else:
        result["summary_line"] = "No targets match the current filters."

    return result


def _best_platform(target):
    """Suggest the single best platform to check first for this target."""
    brand = target.get("brand", "").upper()
    median = target.get("median", 0)

    # Rolex/higher price points: Facebook groups and dealer chats first
    if brand == "ROLEX" or median > 5000:
        return "Facebook groups / dealer chats"
    # Mid-range: eBay BIN is fastest
    if median > 2500:
        return "eBay BIN listings"
    # Lower price: Reddit and eBay both good
    return "eBay / Reddit r/watchexchange"


# ═══ CLI ═══
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Query Vardalux Grailzee buy targets")
    parser.add_argument('--priority', type=str, default=None,
                        help='Filter by priority: HIGH, MEDIUM, LOW, ALL (default: HIGH)')
    parser.add_argument('--brand', type=str, default=None,
                        help='Filter by brand name (case-insensitive)')
    parser.add_argument('--budget', type=float, default=None,
                        help='Only show targets with MAX BUY at or below this amount')
    parser.add_argument('--format', type=str, default=None, dest='fmt',
                        help='Filter by auction format: NR or Reserve')
    parser.add_argument('--include-discoveries', action='store_true', default=False,
                        help='Include discovered references (not in core program)')
    parser.add_argument('--brief', type=str, default=None,
                        help='Override path to sourcing_brief.json')

    args = parser.parse_args()

    brief, error = load_brief(args.brief)
    if error:
        print(json.dumps(error, indent=2))
        sys.exit(1)

    result = filter_targets(
        brief,
        priority=args.priority,
        brand=args.brand,
        budget=args.budget,
        fmt=args.fmt,
        include_discoveries=args.include_discoveries,
    )
    print(json.dumps(result, indent=2))
