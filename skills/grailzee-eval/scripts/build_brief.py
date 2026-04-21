"""Sourcing brief: dual output (JSON + markdown) per guide Section 12.2.

Partial extraction from v1 analyze_report.py:718-980. Adapted for v2's
flat reference dict. JSON goes to STATE_PATH/sourcing_brief.json (consumed
by query_targets.py). Markdown goes to output folder.

Priority scoring preserved from v1:
  +3 Strong, +2 Normal, +1 Reserve/Careful
  +2 trend >= 5%, +1 trend >= 0%
  +1 volume >= 15, +1 sell-through >= 60%
  >=6 HIGH, >=4 MEDIUM, else LOW

Usage:
    build_brief.py <output_folder>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    BRIEF_PATH,
    OUTPUT_PATH,
    get_tracer,
    load_sourcing_rules,
    sourcing_rules_source,
)

tracer = get_tracer(__name__)

# Phase A.4: SOURCING_RULES is now assembled at build time by
# _resolved_sourcing_rules(). The fields below are build_brief-internal
# and remain hardcoded per schema v1 S2 and §2.3's scoping decisions:
#   - platform_priority: sourcing behavior, not math tunable (S2).
#   - us_inventory_only, never_exceed_max_buy: policy flags, not in §2.3.
# The strategy-tunable fields (condition_minimum, papers_required,
# keyword_filters) are sourced from state/sourcing_rules.json via the
# memoized loader, with factory-default fallback when the file is
# missing.
_SOURCING_RULES_BUILD_BRIEF_INTERNAL = {
    "us_inventory_only": True,
    "never_exceed_max_buy": True,
    "platform_priority": [
        {"platform": "facebook_groups", "type": "private dealer groups", "check_frequency": "daily"},
        {"platform": "whatsapp", "type": "dealer group chats", "check_frequency": "real_time"},
        {"platform": "ebay", "type": "BIN listings", "check_frequency": "twice_daily"},
        {"platform": "chrono24", "type": "US dealer listings", "check_frequency": "daily"},
        {"platform": "reddit", "type": "r/watchexchange", "check_frequency": "daily"},
    ],
}


def _resolved_sourcing_rules() -> dict:
    """Build the composite sourcing_rules dict for brief emission.

    Merges build_brief's hardcoded internal fields (platform_priority,
    us_inventory_only, never_exceed_max_buy) with the strategy-tunable
    fields sourced from state/sourcing_rules.json (condition_minimum,
    papers_required, keyword_filters). The result matches the shape of
    the pre-A.4 ``SOURCING_RULES`` module constant, so the JSON brief
    output and the markdown keyword/platform sections see no structural
    change.

    ``load_sourcing_rules()`` is memoized at module level, so repeated
    calls within a single brief build cost one dict lookup.

    Returned dict shares ``keyword_filters`` by reference with the
    memoized loader cache; all current downstream consumers are
    read-only (JSON-serialize, ``", ".join(...)`` in markdown). Do not
    mutate nested collections in callers or the memoized cache will
    leak state into subsequent loads within the same process.
    """
    file_rules = load_sourcing_rules()
    resolved = {
        "us_inventory_only": _SOURCING_RULES_BUILD_BRIEF_INTERNAL["us_inventory_only"],
        "papers_required": file_rules["papers_required"],
        "condition_minimum": file_rules["condition_minimum"],
        "never_exceed_max_buy": _SOURCING_RULES_BUILD_BRIEF_INTERNAL["never_exceed_max_buy"],
        "platform_priority": _SOURCING_RULES_BUILD_BRIEF_INTERNAL["platform_priority"],
        "keyword_filters": file_rules["keyword_filters"],
    }
    return resolved


def _priority_score(ref_data: dict, trend_pct: float) -> int:
    """Compute priority score. Extracted from v1 analyze_report.py:752-766."""
    score = 0
    sig = ref_data.get("signal", "")
    if sig == "Strong":
        score += 3
    elif sig == "Normal":
        score += 2
    elif sig in ("Reserve", "Careful"):
        score += 1
    if trend_pct >= 5:
        score += 2
    elif trend_pct >= 0:
        score += 1
    if ref_data.get("volume", 0) >= 15:
        score += 1
    st = ref_data.get("st_pct")
    if st is not None and st >= 0.60:
        score += 1
    return score


def _priority_label(score: int) -> str:
    if score >= 6:
        return "HIGH"
    if score >= 4:
        return "MEDIUM"
    return "LOW"


def _search_terms(brand: str, model: str, ref: str) -> list[str]:
    """Generate search term variants. Extracted from v1."""
    terms = [f"{brand} {ref}", f"{brand} {model}"]
    if brand == "Tudor":
        if not ref.startswith("M"):
            terms.append(f"Tudor M{ref}")
        else:
            terms.append(f"Tudor {ref[1:]}")
    elif brand == "Omega" and "." in ref:
        terms.append(f"Omega {ref.replace('.', '')}")
    return terms


def _build_notes(ref_data: dict, trend_pct: float) -> str:
    """Contextual sourcing notes. Extracted from v1."""
    notes: list[str] = []
    if ref_data.get("recommend_reserve"):
        risk = ref_data.get("risk_nr")
        notes.append(f"Route to Reserve account. Risk at {risk:.0f}%." if risk is not None else "Route to Reserve account.")
    if trend_pct <= -5:
        notes.append("Softening. Buy at sweet spot or below, not at MAX.")
    if ref_data.get("volume", 0) < 8:
        notes.append("Low volume. Fewer opportunities but less competition.")
    st = ref_data.get("st_pct")
    if st is not None and st >= 0.75:
        notes.append(f"High sell-through ({st:.0%}). Moves fast on Grailzee.")
    return " ".join(notes)


def build_brief(
    all_results: dict,
    trends: dict,
    changes: dict,
    breakouts: dict,
    brands: dict,
    output_folder: str,
) -> dict:
    """Produce sourcing_brief.json + markdown. Returns {"json_path", "md_path"}."""
    refs = all_results.get("references", {})
    momentum_map = trends.get("momentum", {})
    trend_entries = trends.get("trends", [])
    now = datetime.now()
    sourcing_rules = _resolved_sourcing_rules()

    # Build trend lookup by reference
    trend_by_ref: dict[str, dict] = {}
    for t in trend_entries:
        trend_by_ref[t["reference"]] = t

    # Build targets
    targets: list[dict] = []
    for ref, rd in refs.items():
        sig = rd.get("signal", "")
        if sig in ("Pass", "Low data"):
            continue

        is_res = rd.get("recommend_reserve", False)
        mb = rd.get("max_buy_res") if is_res else rd.get("max_buy_nr")
        if mb is None:
            continue
        sweet_spot = round(mb * 0.90, -1)

        t_entry = trend_by_ref.get(ref, {})
        trend_str = t_entry.get("signal_str", "Stable")
        trend_pct = t_entry.get("med_pct", 0)

        ps = _priority_score(rd, trend_pct)
        mom = momentum_map.get(ref)
        st_pct = rd.get("st_pct")

        targets.append({
            "brand": rd.get("brand", ""),
            "model": rd.get("model", ""),
            "reference": ref,
            "priority": _priority_label(ps),
            "priority_score": ps,
            "max_buy": mb,
            "sweet_spot": sweet_spot,
            "median": rd.get("median"),
            "floor": rd.get("floor"),
            "format": "Reserve" if is_res else "NR",
            "signal": sig,
            "risk_vg_pct": round(rd["risk_nr"], 1) if rd.get("risk_nr") is not None else None,
            "volume": rd.get("volume", 0),
            "sell_through": f"{st_pct:.0%}" if st_pct is not None else None,
            "trend": trend_str,
            "trend_pct": round(trend_pct, 1),
            "momentum": mom,
            "search_terms": _search_terms(rd.get("brand", ""), rd.get("model", ""), ref),
            "condition_filter": ["Excellent", "Like New", "Very Good", "BNIB"],
            "papers_required": True,
            "action": "auto_evaluate" if ps >= 4 else "flag_for_review",
            "notes": _build_notes(rd, trend_pct),
        })

    targets.sort(key=lambda t: -t["priority_score"])

    # JSON brief
    brief = {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "valid_until": "Next Grailzee Pro report (~2 weeks)",
        "sourcing_rules": sourcing_rules,
        "targets": targets,
        "summary": {
            "total_targets": len(targets),
            "high_priority": sum(1 for t in targets if t["priority"] == "HIGH"),
            "medium_priority": sum(1 for t in targets if t["priority"] == "MEDIUM"),
            "low_priority": sum(1 for t in targets if t["priority"] == "LOW"),
            "lowest_entry_point": min(t["sweet_spot"] for t in targets) if targets else 0,
            "highest_entry_point": max(t["max_buy"] for t in targets) if targets else 0,
        },
    }

    json_path = BRIEF_PATH
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2, default=str)
        f.write("\n")

    # Markdown brief
    md: list[str] = []
    md.append(f"# Vardalux Sourcing Brief; {now.strftime('%B %d, %Y')}")
    md.append("Valid until next Grailzee Pro report (~2 weeks)\n")
    md.append(f"## Active Targets: {len(targets)} references\n")

    for priority_label in ("HIGH", "MEDIUM", "LOW"):
        group = [t for t in targets if t["priority"] == priority_label]
        if not group:
            continue
        label_map = {"HIGH": "hunt actively", "MEDIUM": "buy on sight if price works", "LOW": "opportunistic only"}
        md.append(f"\n### Priority: {priority_label} ({label_map[priority_label]})\n")
        md.append("| Reference | Model | MAX BUY | Sweet Spot | Signal | Trend |")
        md.append("|-----------|-------|---------|------------|--------|-------|")
        for t in group:
            md.append(
                f"| {t['reference']} | {t['brand']} {t['model']} | "
                f"**${t['max_buy']:,.0f}** | ${t['sweet_spot']:,.0f} | "
                f"{t['signal']} | {t['trend']} |"
            )
            if t["notes"]:
                md.append(f"  *{t['notes']}*")

    md.append("\n## Search Keywords\n")
    md.append("### Include (any match)")
    md.append(", ".join(sourcing_rules["keyword_filters"]["include"]) + "\n")
    md.append("### Exclude (skip listing)")
    md.append(", ".join(sourcing_rules["keyword_filters"]["exclude"]) + "\n")
    md.append("## Platform Scan Order\n")
    for i, p in enumerate(sourcing_rules["platform_priority"], 1):
        md.append(f"{i}. {p['platform'].replace('_', ' ').title()} ({p['check_frequency']})")
    md.append("\nUS inventory only. Never exceed MAX BUY. Papers required on every deal.\n")
    md.append(f"---\n*Generated {now.strftime('%B %d, %Y')}*")

    os.makedirs(output_folder, exist_ok=True)
    md_filename = f"Vardalux_Sourcing_Brief_{now.strftime('%B%Y')}.md"
    md_path = os.path.join(output_folder, md_filename)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    return {"json_path": json_path, "md_path": md_path}


# --- CLI entry ────────────────────────────────────────────────────────


def run(
    all_results: dict,
    trends: dict,
    changes: dict,
    breakouts: dict,
    brands: dict,
    output_folder: str,
) -> dict:
    """CLI-friendly wrapper."""
    return build_brief(all_results, trends, changes, breakouts, brands, output_folder)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_folder", help="Directory to write brief files")
    args = parser.parse_args()

    with tracer.start_as_current_span("build_brief.run") as span:
        result = run({}, {}, {}, {}, {}, args.output_folder)
        span.set_attribute("json_path", result["json_path"])
        span.set_attribute("sourcing_rules_source", sourcing_rules_source())
        print(json.dumps(result, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
