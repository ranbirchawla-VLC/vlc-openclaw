"""Write analysis_cache.json (v3 schema) per schema v3 Decision Lock 2026-04-24.

Upgraded from v2 (schema_version 2) to v3 (schema_version 3). Market fields
move per-bucket; the only reference-level derived field is `confidence`
(own-ledger trade rollup, not a per-bucket synthesis). Bucket construction
and scoring consumed from analyze_buckets.py.

Per G4 (patched 2026-04-24) + 2b fixup 2026-04-24: market fields are
per-bucket; `confidence` is reference-level (own-ledger summary); trend
and momentum are reference-level (cross-report data from analyze_trends.py).
Ledger-vs-market comparison (premium_vs_market, realized_premium) is NOT
produced here; it moves to strategy-session time in 2c where the ledger
entry's own bucket keying supplies the matching-bucket median.

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
from datetime import date, datetime
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
    or null; the common case on the run_analysis first-pass, since
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
    """Write analysis_cache.json (v3 schema). Returns output path.

    ``today`` reserved for future ledger-window work; currently unused
    by v3 write_cache after the 2b fixup removed the realized-premium
    window from the cache shape. Kept in the signature so callers
    (run_analysis, tests) do not need to change.

    v3 shape: market fields live in per-bucket dicts inside each reference
    entry's ``buckets`` key. `confidence` (own-ledger trade rollup) and
    trend/momentum remain at reference level. Ledger-vs-market comparison
    is NOT in the cache; strategy session computes it at read time with
    bucket-aware median lookup.
    """
    out = cache_path or CACHE_PATH
    bak = backup_path or BACKUP_PATH
    _ = today  # reserved; see docstring

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

    # Per-reference cache entries (v3: market fields live in buckets dict)
    cache_refs: dict[str, dict] = {}
    for ref, rd in refs.items():
        t_entry = trend_by_ref.get(ref)
        entry = {
            "brand": rd.get("brand", ""),
            "model": rd.get("model", ""),
            "reference": ref,
            "named": rd.get("named", False),
            "trend_signal": t_entry.get("signal_str") if t_entry else None,
            "trend_median_change": t_entry.get("med_change") if t_entry else None,
            "trend_median_pct": t_entry.get("med_pct") if t_entry else None,
            "momentum": momentum_map.get(ref),
            "confidence": _confidence_from_trades(
                ledger_trades, rd.get("brand", ""), ref,
            ),
            "buckets": rd.get("buckets", {}),
        }
        cache_refs[ref] = entry

    # DJ configs: confidence is always None (no per-config ledger join).
    # Trend/momentum are reference-level per Patch 2; DJ configs have no
    # independent trend series, so they receive nulls (not synthesized
    # defaults).
    for cfg_entry in dj_configs.values():
        cfg_entry["confidence"] = None
        cfg_entry["trend_signal"] = None
        cfg_entry["trend_median_change"] = None
        cfg_entry["trend_median_pct"] = None
        cfg_entry["momentum"] = None

    # Hot references: set union of emerged refs and breakout refs
    emerged_set = set(changes.get("emerged", []))
    breakout_set = set(b["reference"] for b in breakouts.get("breakouts", []))
    hot_count = len(emerged_set | breakout_set)

    # Bucket-level signal counts: a factual rollup of buckets by signal.
    # Reference buckets only; DJ config buckets excluded to match the
    # `total_references` precedent (DJ configs are sub-entries of 126300,
    # not distinct references; counting their buckets would present a
    # second view on the same underlying sales).
    ref_entries = list(cache_refs.values())
    all_ref_buckets = [
        bd
        for rd in ref_entries
        for bd in rd.get("buckets", {}).values()
    ]
    total_bucket_count = len(all_ref_buckets)
    strong_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Strong")
    normal_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Normal")
    reserve_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Reserve")
    caution_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Careful")
    pass_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Pass")
    low_data_bucket_count = sum(1 for bd in all_ref_buckets if bd.get("signal") == "Low data")

    summary = {
        "total_references": len(ref_entries),
        "total_bucket_count": total_bucket_count,
        "strong_bucket_count": strong_bucket_count,
        "normal_bucket_count": normal_bucket_count,
        "reserve_bucket_count": reserve_bucket_count,
        "caution_bucket_count": caution_bucket_count,
        "pass_bucket_count": pass_bucket_count,
        "low_data_bucket_count": low_data_bucket_count,
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
