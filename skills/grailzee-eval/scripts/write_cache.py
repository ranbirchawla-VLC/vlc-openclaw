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
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from opentelemetry.trace import get_current_span

from scripts.grailzee_common import (
    BACKUP_PATH,
    CACHE_PATH,
    CACHE_SCHEMA_VERSION,
    RUN_HISTORY_PATH,
    calculate_presentation_premium,
    canonical_reference,
    get_tracer,
    resolve_to_cache_ref,
)

tracer = get_tracer(__name__)

DJ_PARENT_REFERENCE = "126300"

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


def _trade_matches_cache_ref(trade: dict, reference: str) -> bool:
    """Does ``trade`` join to cache entry ``reference``?

    Uses ``resolved_cache_ref`` as the authoritative answer when
    ``read_ledger._compute_derived_fields`` successfully stamped one
    (requires the cache to have been loaded at read time). Falls back
    to a single-key ``resolve_to_cache_ref`` when the field is absent
    or null — the common case on the run_analysis first-pass, since
    the cache file is written AFTER read_ledger has already run, so
    read_ledger's call sees an empty cache and stamps ``None``.
    """
    resolved = trade.get("resolved_cache_ref")
    if resolved is not None:
        return resolved == reference
    return resolve_to_cache_ref({reference}, trade.get("reference", "")) == reference


def _confidence_from_trades(
    trades: list[dict], brand: str, reference: str,
) -> dict | None:
    """Compute per-reference confidence from enriched ledger trades.

    Matches via ``_trade_matches_cache_ref`` so ledger rows logged with
    per-piece inventory IDs (``M28500-0005``) join to the canonical
    cache entry (``28500``).
    """
    matching = [
        t for t in trades
        if t.get("brand", "").lower() == brand.lower()
        and _trade_matches_cache_ref(t, reference)
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


def _premium_vs_market_from_trades(
    trades: list[dict],
    brand: str,
    reference: str,
    current_median: float | None,
) -> tuple[float, int]:
    """Compute (premium_vs_market_pct, premium_vs_market_sale_count) per B.2.

    Most-recent Vardalux sale on the reference vs current market median.
    Zero-floored: no matching trades, indeterminate median, or a most-
    recent sale at-or-below the current median all collapse to 0.0.
    The count reports total matching trades regardless of premium sign,
    mirroring realized_premium_trade_count's precedent for B.3.

    Tiebreak: two sales on the same ``sell_date`` resolve by highest
    ``sell_price``. New convention with B.2; no prior codebase precedent
    for most-recent-row tiebreak exists.

    Brand+reference match mirrors ``_confidence_from_trades`` and
    uses ``_trade_matches_cache_ref`` so per-piece inventory IDs join
    to the canonical cache entry.
    """
    matching = [
        t for t in trades
        if t.get("brand", "").lower() == brand.lower()
        and _trade_matches_cache_ref(t, reference)
    ]
    sale_count = len(matching)
    if not matching or current_median is None or current_median <= 0:
        return 0.0, sale_count
    most_recent = max(
        matching,
        key=lambda t: (t["sell_date"], t["sell_price"]),
    )
    sale_price = most_recent["sell_price"]
    if sale_price <= current_median:
        return 0.0, sale_count
    pct = round((sale_price - current_median) / current_median * 100, 1)
    return pct, sale_count


def _realized_premium_from_trades(
    trades: list[dict],
    brand: str,
    reference: str,
    current_median: float | None,
    today: date,
    window_days: int = 30,
) -> tuple[float | None, int]:
    """Compute (realized_premium_pct, realized_premium_trade_count) per B.3.

    Recency-bounded version of B.2's signal: most-recent Vardalux sale
    on the reference **within the last ``window_days``** vs current
    market median. Window is inclusive on both ends — a sell exactly
    ``window_days`` before ``today`` is in window.

    Returns:
      * ``(None, 0)`` — no matching in-window trade (B.3's distinct
        "no recent data" signal, contrasted with B.2's zero-floor
        "no data ever" signal)
      * ``(None, count)`` — in-window trades exist but current_median
        is indeterminate (can't compute pct)
      * ``(pct, count)`` — normal case; pct is NOT zero-floored, so a
        below-median recent clearing produces a negative number and
        strategy reads raw

    Tiebreak: two sells on the same ``sell_date`` resolve by highest
    ``sell_price`` (same convention as B.2).

    Brand+reference match goes through ``_trade_matches_cache_ref`` so
    per-piece inventory IDs join to the canonical cache entry.
    """
    window_start = today - timedelta(days=window_days)
    matching = [
        t for t in trades
        if t.get("brand", "").lower() == brand.lower()
        and _trade_matches_cache_ref(t, reference)
    ]
    in_window: list[tuple[date, dict]] = []
    for t in matching:
        sd_str = t.get("sell_date", "")
        if not sd_str:
            continue
        try:
            sd = date.fromisoformat(sd_str)
        except (TypeError, ValueError):
            continue
        if sd >= window_start and sd <= today:
            in_window.append((sd, t))
    count = len(in_window)
    if not in_window:
        return None, 0
    if current_median is None or current_median <= 0:
        return None, count
    most_recent_sd, most_recent_trade = max(
        in_window, key=lambda p: (p[0], p[1]["sell_price"]),
    )
    sale_price = most_recent_trade["sell_price"]
    pct = round((sale_price - current_median) / current_median * 100, 1)
    return pct, count


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
    today: date | None = None,
) -> str:
    """Write analysis_cache.json (v2 schema). Returns output path.

    ``today`` anchors the B.3 realized-premium 30-day window. Defaults
    to ``date.today()`` in live runs; tests pass a fixed date so the
    assertions stay stable across pytest-run dates.
    """
    out = cache_path or CACHE_PATH
    bak = backup_path or BACKUP_PATH
    today = today or date.today()

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
        pvm_pct, pvm_count = _premium_vs_market_from_trades(
            ledger_trades, rd.get("brand", ""), ref, rd.get("median"),
        )
        rp_pct, rp_count = _realized_premium_from_trades(
            ledger_trades, rd.get("brand", ""), ref,
            rd.get("median"), today,
        )
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
            "premium_vs_market_pct": pvm_pct,
            "premium_vs_market_sale_count": pvm_count,
            "realized_premium_pct": rp_pct,
            "realized_premium_trade_count": rp_count,
            "trend_signal": t_entry.get("signal_str", "No prior data"),
            "trend_median_change": t_entry.get("med_change", 0),
            "trend_median_pct": t_entry.get("med_pct", 0),
        }
        cache_refs[ref] = entry

    # DJ configs inherit premium_vs_market_* and realized_premium_* from
    # parent reference 126300 per B.2/B.3 addendum: Grailzee Pro data
    # lacks dial-color granularity so per-config computation isn't
    # supportable from the source. If the parent isn't present in
    # cache_refs (e.g. didn't meet min_sales this run), configs fall
    # back to B.2 (0.0, 0) / B.3 (None, 0).
    parent = cache_refs.get(DJ_PARENT_REFERENCE, {})
    parent_pvm_pct = parent.get("premium_vs_market_pct", 0.0)
    parent_pvm_count = parent.get("premium_vs_market_sale_count", 0)
    parent_rp_pct = parent.get("realized_premium_pct", None)
    parent_rp_count = parent.get("realized_premium_trade_count", 0)
    for cfg_entry in dj_configs.values():
        cfg_entry["premium_vs_market_pct"] = parent_pvm_pct
        cfg_entry["premium_vs_market_sale_count"] = parent_pvm_count
        cfg_entry["realized_premium_pct"] = parent_rp_pct
        cfg_entry["realized_premium_trade_count"] = parent_rp_count

    # Coverage signals on the active span (the caller's write_cache.run
    # span in run_analysis.py, or write_cache.main()'s span). Silent
    # no-op outside any span context.
    span = get_current_span()
    all_entries = list(cache_refs.values()) + list(dj_configs.values())
    span.set_attribute(
        "premium_vs_market_pct_nonzero_count",
        sum(1 for e in all_entries if (e.get("premium_vs_market_pct") or 0) > 0),
    )
    span.set_attribute(
        "realized_premium_pct_populated_count",
        sum(1 for e in all_entries if e.get("realized_premium_pct") is not None),
    )

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
    today: date | None = None,
) -> str:
    """CLI-friendly wrapper."""
    return write_cache(
        all_results, trends, changes, breakouts,
        watchlist, brands, ledger_stats, current_cycle_id,
        source_report, market_window, cache_path, backup_path,
        today=today,
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
