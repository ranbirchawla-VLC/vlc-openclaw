"""Markdown analysis summary per guide Section 12.2.

Partial extraction from v1 analyze_report.py:601-714. Adapted for v2's
flat reference dict and expanded to cover all v2 analysis dimensions:
breakouts, watchlist, brands, momentum, cycle context.

Usage:
    build_summary.py <output_folder> [--cycle-id CYCLE_ID]
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

from scripts.grailzee_common import OUTPUT_PATH, get_tracer

tracer = get_tracer(__name__)


def build_summary(
    all_results: dict,
    trends: dict,
    changes: dict,
    breakouts: dict,
    watchlist: dict,
    brands: dict,
    ledger_stats: dict,
    current_cycle_id: str,
    output_folder: str,
) -> str:
    """Produce markdown analysis summary. Returns output path."""
    refs = all_results.get("references", {})
    dj_configs = all_results.get("dj_configs", {})
    now = datetime.now().strftime("%B %d, %Y")
    lines: list[str] = []

    lines.append(f"# Vardalux Grailzee Analysis; {current_cycle_id}")
    lines.append(f"Generated: {now}\n")

    # -- Market Snapshot --
    strong = [r for r in refs.values() if r.get("signal") == "Strong"]
    normal = [r for r in refs.values() if r.get("signal") == "Normal"]
    reserve_refs = [r for r in refs.values() if r.get("recommend_reserve")]
    nr_safe = [r for r in refs.values()
               if not r.get("recommend_reserve") and r.get("signal") in ("Strong", "Normal")]

    lines.append("## Market Snapshot\n")
    lines.append(
        f"{len(refs)} references scored. "
        f"{len(strong)} Strong, {len(normal)} Normal, "
        f"{len(nr_safe)} NR-safe, {len(reserve_refs)} routing to Reserve."
    )

    # Trend headlines
    trend_entries = trends.get("trends", [])
    if trend_entries:
        rising = [t for t in trend_entries if t.get("med_pct", 0) >= 5]
        falling = [t for t in trend_entries if t.get("med_pct", 0) <= -5]
        if rising:
            names = ", ".join(t.get("model", t.get("reference", "?")) for t in rising[:4])
            lines.append(f"Rising: {names}.")
        if falling:
            names = ", ".join(t.get("model", t.get("reference", "?")) for t in falling[:4])
            lines.append(f"Softening: {names}.")
        if not rising and not falling:
            lines.append("Market is broadly stable period over period.")
    else:
        lines.append("No prior report for trend comparison.")

    # Ledger stats
    ls = ledger_stats.get("summary", {})
    if ls.get("total_trades", 0) > 0:
        lines.append(
            f"\nLedger: {ls['total_trades']} trades, "
            f"{ls.get('win_rate', 0)}% win rate, "
            f"{ls.get('avg_roi_pct', 0)}% avg ROI."
        )

    # -- Buy Targets: NR Safe --
    if nr_safe:
        lines.append("\n## NR Buy Targets\n")
        lines.append("| Reference | Model | MAX BUY | Signal | ST% | Vol |")
        lines.append("|-----------|-------|---------|--------|-----|-----|")
        for r in sorted(nr_safe, key=lambda x: x.get("brand", "")):
            st = f"{r['st_pct']:.0%}" if r.get("st_pct") is not None else "\u2014"
            mb = r.get("max_buy_nr", 0)
            lines.append(
                f"| {r['reference']} | {r.get('brand', '')} {r.get('model', '')} | "
                f"**${mb:,.0f}** | {r.get('signal', '')} | {st} | {r.get('volume', 0)} |"
            )

    # -- Reserve Candidates --
    if reserve_refs:
        lines.append("\n## Reserve Candidates\n")
        lines.append("| Reference | Model | MAX BUY (Res) | Risk VG+ | Vol |")
        lines.append("|-----------|-------|---------------|----------|-----|")
        for r in sorted(reserve_refs, key=lambda x: x.get("brand", "")):
            risk = f"{r['risk_nr']:.0f}%" if r.get("risk_nr") is not None else "\u2014"
            mb = r.get("max_buy_res", 0)
            lines.append(
                f"| {r['reference']} | {r.get('brand', '')} {r.get('model', '')} | "
                f"**${mb:,.0f}** | {risk} | {r.get('volume', 0)} |"
            )

    # -- DJ Configs --
    if dj_configs:
        lines.append("\n## Datejust 126300 by Configuration\n")
        lines.append("| Config | MAX BUY | Signal | Risk VG+ | Vol |")
        lines.append("|--------|---------|--------|----------|-----|")
        for cn in sorted(dj_configs):
            d = dj_configs[cn]
            is_res = d.get("recommend_reserve", False)
            mb = d.get("max_buy_res") if is_res else d.get("max_buy_nr", 0)
            risk = f"{d['risk_nr']:.0f}%" if d.get("risk_nr") is not None else "\u2014"
            fmt_note = " (Res)" if is_res else ""
            lines.append(f"| {cn} | **${mb:,.0f}**{fmt_note} | {d.get('signal', '')} | {risk} | {d.get('volume', 0)} |")

    # -- Trend Movers --
    if trend_entries:
        notable = [t for t in trend_entries if t.get("signals")]
        if notable:
            lines.append("\n## Trend Movers\n")
            for t in notable:
                direction = "up" if t.get("med_change", 0) > 0 else "down"
                lines.append(
                    f"**{t.get('brand', '')} {t.get('model', '')}**: "
                    f"Median {direction} ${abs(t.get('med_change', 0)):,.0f} "
                    f"({t.get('med_pct', 0):+.1f}%). {t.get('signal_str', '')}."
                )

    # -- Emerged References (v2; replaces v1 "Discovered") --
    emerged = changes.get("emerged", [])
    if emerged:
        lines.append(f"\n## Emerged References ({len(emerged)} new)\n")
        for ref in emerged[:10]:
            lines.append(f"- {ref}")

    # -- Breakouts (new in v2) --
    breakout_list = breakouts.get("breakouts", [])
    if breakout_list:
        lines.append(f"\n## Breakouts ({len(breakout_list)})\n")
        for b in breakout_list:
            signals = ", ".join(b.get("signals", []))
            lines.append(f"- **{b['reference']}**: {signals}")

    # -- Watchlist (new in v2) --
    wl = watchlist.get("watchlist", [])
    if wl:
        lines.append(f"\n## Watchlist ({len(wl)} early signals)\n")
        lines.append("| Reference | Sales | Avg Price |")
        lines.append("|-----------|-------|-----------|")
        for w in wl:
            lines.append(f"| {w['reference']} | {w['current_sales']} | ${w['avg_price']:,.0f} |")

    # -- Brand Signals (new in v2) --
    brand_data = brands.get("brands", {})
    if brand_data:
        lines.append("\n## Brand Signals\n")
        for bn in sorted(brand_data):
            bd = brand_data[bn]
            lines.append(
                f"- **{bn}**: {bd['signal']} "
                f"(avg momentum {bd['avg_momentum']}, "
                f"{bd['warming']}W/{bd['cooling']}C, "
                f"{bd['reference_count']} refs)"
            )

    lines.append(f"\n---\n*Generated {now}*")

    # Write
    os.makedirs(output_folder, exist_ok=True)
    filename = f"Vardalux_Grailzee_Analysis_{datetime.now().strftime('%B%Y')}.md"
    output_path = os.path.join(output_folder, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


# --- CLI entry ────────────────────────────────────────────────────────


def run(
    all_results: dict,
    trends: dict,
    changes: dict,
    breakouts: dict,
    watchlist: dict,
    brands: dict,
    ledger_stats: dict,
    current_cycle_id: str,
    output_folder: str,
) -> str:
    """CLI-friendly wrapper."""
    return build_summary(
        all_results, trends, changes, breakouts,
        watchlist, brands, ledger_stats, current_cycle_id, output_folder,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_folder", help="Directory to write markdown")
    parser.add_argument("--cycle-id", default="cycle_0000-00")
    args = parser.parse_args()

    with tracer.start_as_current_span("build_summary.run") as span:
        result_path = run({}, {}, {}, {}, {}, {}, {}, args.cycle_id, args.output_folder)
        span.set_attribute("output_path", result_path)
        print(result_path)
        return 0


if __name__ == "__main__":
    sys.exit(main())
