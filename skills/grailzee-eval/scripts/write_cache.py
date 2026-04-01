#!/usr/bin/env python3
"""
Grailzee Analysis Cache Writer

Called after a full analysis run to write a flat, lookup-optimized
JSON cache that the deal evaluator (and any other downstream tool)
can read without re-parsing Excel reports.

Also handles backup rotation: before writing a new cache, the previous
one is timestamped and moved to the backup folder.
"""

import os, json, shutil
from datetime import datetime

GRAILZEE_ROOT = "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData"
DEFAULT_STATE_DIR = os.path.join(GRAILZEE_ROOT, "state")
DEFAULT_BACKUP_DIR = os.path.join(GRAILZEE_ROOT, "backup")

SCHEMA_VERSION = 1


def ensure_dirs(state_dir=None, backup_dir=None):
    """Create the folder structure if it doesn't exist."""
    state_dir = state_dir or DEFAULT_STATE_DIR
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    base = os.path.dirname(state_dir)

    for d in [base, state_dir, backup_dir,
              os.path.join(base, "reports"),
              os.path.join(base, "output")]:
        os.makedirs(d, exist_ok=True)

    # Write meta file if first run
    meta_path = os.path.join(base, ".grailzee-meta.json")
    if not os.path.exists(meta_path):
        with open(meta_path, 'w') as f:
            json.dump({
                "schema_version": SCHEMA_VERSION,
                "created_at": datetime.now().isoformat(),
                "description": "Vardalux Grailzee analyzer persistent data. Do not delete.",
            }, f, indent=2)


def backup_existing(cache_path, backup_dir=None):
    """Move existing cache to backup with timestamp."""
    if not os.path.exists(cache_path):
        return
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"analysis_cache_{ts}.json"
    shutil.copy2(cache_path, os.path.join(backup_dir, backup_name))

    # Keep only last 10 backups
    backups = sorted([
        f for f in os.listdir(backup_dir)
        if f.startswith("analysis_cache_") and f.endswith(".json")
    ])
    for old in backups[:-10]:
        os.remove(os.path.join(backup_dir, old))


def flatten_entry(data):
    """
    Flatten a results dict entry into the cache format.
    
    Input: {'brand': ..., 'model': ..., 'reference': ..., 'section': ...,
            'analysis': {median, max_buy_nr, risk_nr, signal, ...},
            'sales': [...]}
    
    Output: flat dict with analysis fields promoted to top level,
            sales stripped (cache doesn't store raw sales).
    """
    a = data.get("analysis", {})
    entry = {
        "brand": data.get("brand", ""),
        "model": data.get("model", ""),
        "reference": data.get("reference", ""),
        "section": data.get("section", ""),
        "alternate_refs": [],

        # Core metrics (promoted from analysis)
        "median": a.get("median"),
        "mean": a.get("mean"),
        "floor": a.get("floor"),
        "ceiling": a.get("ceiling"),
        "volume": a.get("volume", 0),
        "quality_count": a.get("quality_count", 0),
        "st_pct": a.get("st_pct"),

        # Buy targets
        "max_buy_nr": a.get("max_buy_nr"),
        "max_buy_res": a.get("max_buy_res"),
        "breakeven_nr": a.get("breakeven_nr"),
        "breakeven_res": a.get("breakeven_res"),

        # Risk
        "risk_nr": a.get("risk_nr"),
        "risk_res": a.get("risk_res"),
        "recommend_reserve": a.get("recommend_reserve", False),
        "signal": a.get("signal", "Low data"),

        # Profit at median
        "profit_nr": a.get("profit_nr"),
        "profit_res": a.get("profit_res"),
    }
    return entry


def write_cache(results, trends, discoveries, source_report,
                state_dir=None, backup_dir=None):
    """
    Write the analysis cache from a completed analyzer run.
    
    Args:
        results: dict from match_core_sales() — keyed by "Brand|Model"
        trends: list from compare_periods()
        discoveries: list of discovered references
        source_report: filename of the report that was analyzed
        state_dir: override for state directory
        backup_dir: override for backup directory
    
    Returns:
        path to the written cache file
    """
    state_dir = state_dir or DEFAULT_STATE_DIR
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    ensure_dirs(state_dir, backup_dir)

    cache_path = os.path.join(state_dir, "analysis_cache.json")

    # Backup previous cache
    backup_existing(cache_path, backup_dir)

    # ── Build the cache ──
    cache = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_report": source_report,
        "references": {},
        "dj_configs": {},
        "discoveries": {},
    }

    # Core + opportunistic references
    for key, data in results.items():
        if key.startswith('_'):
            continue
        entry = flatten_entry(data)

        # Build alternate refs list from the CORE_REFERENCES patterns
        # (the key is "Brand|Model", reference is patterns[0])
        entry["alternate_refs"] = []

        # Add trend data if available
        trend_match = next((t for t in trends if
                           t.get("brand") == data.get("brand") and
                           t.get("model") == data.get("model")), None)
        if trend_match:
            entry["trend_signal"] = trend_match.get("signal_str", "Stable")
            entry["trend_median_change"] = trend_match.get("med_change", 0)
            entry["trend_median_pct"] = trend_match.get("med_pct", 0)
        else:
            entry["trend_signal"] = "No prior data"
            entry["trend_median_change"] = 0
            entry["trend_median_pct"] = 0

        cache["references"][key] = entry

    # DJ configs (separate section for clean lookup)
    dj_cfgs = results.get("_dj_configs", {})
    if isinstance(dj_cfgs, dict):
        for cfg_name, data in dj_cfgs.items():
            entry = flatten_entry(data)
            entry["config"] = cfg_name
            cache["dj_configs"][cfg_name] = entry

    # Discovered references
    for disc in discoveries:
        entry = flatten_entry({
            "brand": disc.get("brand", "?"),
            "model": disc.get("model", ""),
            "reference": disc.get("reference", ""),
            "section": "discovered",
            "analysis": disc.get("analysis", {}),
        })
        entry["sale_count"] = disc.get("count", 0)
        cache["discoveries"][disc.get("reference", "?")] = entry

    # ── Summary stats (for quick status checks) ──
    ref_entries = list(cache["references"].values())
    cache["summary"] = {
        "total_references": len(ref_entries),
        "strong_count": sum(1 for e in ref_entries if e["signal"] == "Strong"),
        "normal_count": sum(1 for e in ref_entries if e["signal"] == "Normal"),
        "reserve_count": sum(1 for e in ref_entries if e["signal"] in ("Reserve", "Careful")),
        "pass_count": sum(1 for e in ref_entries if e["signal"] == "Pass"),
        "discoveries_count": len(discoveries),
        "dj_configs_count": len(cache["dj_configs"]),
    }

    # ── Write ──
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, default=str)

    print(f"  Cache written: {cache_path}")
    print(f"  References: {cache['summary']['total_references']}, "
          f"DJ configs: {cache['summary']['dj_configs_count']}, "
          f"Discoveries: {cache['summary']['discoveries_count']}")

    # ── Update run history ──
    history_path = os.path.join(state_dir, "run_history.json")
    history = []
    if os.path.exists(history_path):
        with open(history_path, 'r') as f:
            history = json.load(f)

    history.append({
        "timestamp": datetime.now().isoformat(),
        "source_report": source_report,
        "references_count": cache["summary"]["total_references"],
        "discoveries_count": cache["summary"]["discoveries_count"],
    })
    # Keep last 50 runs
    history = history[-50:]

    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)

    return cache_path
