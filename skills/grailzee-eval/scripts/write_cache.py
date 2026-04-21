"""Write analysis_cache.json (v2 schema) per guide Section 13.

Extracted from v1 write_cache.py (232 lines). Schema upgraded from v1
(schema_version 1) to v2. Backup rotation and run history preserved.
Per-reference shape simplified (v2 references are already flat; no
flatten_entry needed).

Usage:
    Called by orchestrator: write_cache.run(all_results, trends, changes,
        breakouts, watchlist, brands, ledger_stats, current_cycle_id)
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    BACKUP_PATH,
    CACHE_PATH,
    CACHE_SCHEMA_VERSION,
    RUN_HISTORY_PATH,
    calculate_presentation_premium,
    get_tracer,
)

tracer = get_tracer(__name__)

MAX_BACKUPS = 10
MAX_HISTORY = 50


def _backup_existing(cache_path: str, backup_dir: str) -> None:
    """Copy existing cache to backup with timestamp. Keep last MAX_BACKUPS."""
    if not os.path.exists(cache_path):
        return
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"analysis_cache_{ts}.json"
    shutil.copy2(cache_path, os.path.join(backup_dir, backup_name))

    backups = sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith("analysis_cache_") and f.endswith(".json")
    )
    for old in backups[:-MAX_BACKUPS]:
        os.remove(os.path.join(backup_dir, old))


def _confidence_from_trades(
    trades: list[dict], brand: str, reference: str,
) -> dict | None:
    """Compute per-reference confidence from enriched ledger trades."""
    matching = [
        t for t in trades
        if t.get("brand", "").lower() == brand.lower()
        and t.get("reference") == reference
    ]
    if not matching:
        return None
    profitable = sum(1 for t in matching if t.get("net_profit", 0) > 0)
    rois = [t["roi_pct"] for t in matching]
    premiums = [t["premium_vs_median"] for t in matching
                if t.get("premium_vs_median") is not None]
    return {
        "trades": len(matching),
        "profitable": profitable,
        "win_rate": round(profitable / len(matching) * 100, 1),
        "avg_roi": round(statistics.mean(rois), 1),
        "avg_premium": round(statistics.mean(premiums), 1) if premiums else None,
        "last_trade": max(t["sell_date"] for t in matching),
    }


def _build_premium_status(trades: list[dict]) -> dict:
    """Compute premium_status block from enriched ledger trades."""
    ps = calculate_presentation_premium(trades)
    ps["trades_to_threshold"] = max(0, 10 - ps["trade_count"])
    return ps


def _premium_status_string(ps: dict) -> str:
    """Format premium_status for the summary block."""
    return (
        f"{ps['trade_count']} trades, "
        f"+{ps['avg_premium']}%, "
        f"{ps['trades_to_threshold']} to threshold"
    )


def write_cache(
    all_results: dict,
    trends: dict,
    changes: dict,
    breakouts: dict,
    watchlist: dict,
    brands: dict,
    ledger_stats: dict,
    current_cycle_id: str,
    source_report: str = "",
    market_window: dict | None = None,
    cache_path: str | None = None,
    backup_path: str | None = None,
) -> str:
    """Write analysis_cache.json (v2 schema). Returns output path."""
    out = cache_path or CACHE_PATH
    bak = backup_path or BACKUP_PATH

    # Backup previous cache
    _backup_existing(out, bak)

    refs = all_results.get("references", {})
    dj_configs = all_results.get("dj_configs", {})
    trend_list = trends.get("trends", [])
    momentum_map = trends.get("momentum", {})
    ledger_trades = ledger_stats.get("trades", [])

    # Build trend lookup by reference
    trend_by_ref: dict[str, dict] = {}
    for t in trend_list:
        trend_by_ref[t["reference"]] = t

    # Premium status
    premium_status = _build_premium_status(ledger_trades)

    # Per-reference cache entries
    cache_refs: dict[str, dict] = {}
    for ref, rd in refs.items():
        t_entry = trend_by_ref.get(ref, {})
        entry = {
            "brand": rd.get("brand", ""),
            "model": rd.get("model", ""),
            "reference": ref,
            "named": rd.get("named", False),
            "median": rd.get("median"),
            "max_buy_nr": rd.get("max_buy_nr"),
            "max_buy_res": rd.get("max_buy_res"),
            "risk_nr": rd.get("risk_nr"),
            "signal": rd.get("signal", "Low data"),
            "volume": rd.get("volume", 0),
            "st_pct": rd.get("st_pct"),
            "momentum": momentum_map.get(ref),
            "confidence": _confidence_from_trades(
                ledger_trades, rd.get("brand", ""), ref,
            ),
            "trend_signal": t_entry.get("signal_str", "No prior data"),
            "trend_median_change": t_entry.get("med_change", 0),
            "trend_median_pct": t_entry.get("med_pct", 0),
        }
        cache_refs[ref] = entry

    # Hot references: set union of emerged refs and breakout refs
    emerged_set = set(changes.get("emerged", []))
    breakout_set = set(b["reference"] for b in breakouts.get("breakouts", []))
    hot_count = len(emerged_set | breakout_set)

    # Summary
    ref_entries = list(cache_refs.values())
    summary = {
        "total_references": len(ref_entries),
        "strong_count": sum(1 for e in ref_entries if e["signal"] == "Strong"),
        "normal_count": sum(1 for e in ref_entries if e["signal"] == "Normal"),
        "reserve_count": sum(1 for e in ref_entries if e["signal"] == "Reserve"),
        "caution_count": sum(1 for e in ref_entries if e["signal"] == "Careful"),
        "emerged_count": len(changes.get("emerged", [])),
        "breakout_count": len(breakouts.get("breakouts", [])),
        "watchlist_count": len(watchlist.get("watchlist", [])),
        "unnamed_count": len(changes.get("unnamed", [])),
        "hot_references": hot_count,
        "premium_status": _premium_status_string(premium_status),
    }

    cache = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_report": source_report,
        "cycle_id": current_cycle_id,
        "market_window": market_window or {"pricing_reports": [], "trend_reports": []},
        "premium_status": premium_status,
        "references": cache_refs,
        "dj_configs": dj_configs,
        "changes": {
            "emerged": changes.get("emerged", []),
            "shifted": changes.get("shifted", {}),
            "faded": changes.get("faded", []),
        },
        "breakouts": breakouts.get("breakouts", []),
        "watchlist": watchlist.get("watchlist", []),
        "brands": brands.get("brands", {}),
        "unnamed": changes.get("unnamed", []),
        "summary": summary,
    }

    # Write
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, default=str)
        f.write("\n")

    # Update run history
    history_path = os.path.join(os.path.dirname(out), "run_history.json")
    history: list[dict] = []
    if os.path.exists(history_path):
        with open(history_path, "r") as f:
            history = json.load(f)
    history.append({
        "timestamp": datetime.now().isoformat(),
        "source_report": source_report,
        "total_references": summary["total_references"],
        "cycle_id": current_cycle_id,
    })
    history = history[-MAX_HISTORY:]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    return out


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
    source_report: str = "",
    market_window: dict | None = None,
    cache_path: str | None = None,
    backup_path: str | None = None,
) -> str:
    """CLI-friendly wrapper."""
    return write_cache(
        all_results, trends, changes, breakouts,
        watchlist, brands, ledger_stats, current_cycle_id,
        source_report, market_window, cache_path, backup_path,
    )


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache_path", help="Path to write analysis_cache.json")
    args = parser.parse_args()

    with tracer.start_as_current_span("write_cache.run") as span:
        path = run({}, {}, {}, {}, {}, {}, {}, "cycle_0000-00",
                   cache_path=args.cache_path,
                   backup_path=os.path.join(os.path.dirname(args.cache_path), "backup"))
        span.set_attribute("cache_path", path)
        print(path)
        return 0


if __name__ == "__main__":
    sys.exit(main())
