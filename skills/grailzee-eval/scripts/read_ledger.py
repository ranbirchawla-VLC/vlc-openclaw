"""Read and analyze the Grailzee trade ledger.

Pure-read module. Parses the CSV, computes derived fields, and provides
aggregation functions consumed by ledger_manager.py CLI and the deal
capability.

No writes. No CLI. No side effects.
"""

from __future__ import annotations

import json
import statistics
from datetime import date
from typing import Any, Optional

from scripts.grailzee_common import (
    ACCOUNT_FEES,
    CACHE_PATH,
    LEDGER_PATH,
    LedgerRow,
    cycle_date_range,
    parse_ledger_csv,
)


# ─── Derived fields ──────────────────────────────────────────────────


def _load_cache(cache_path: Optional[str] = None) -> dict:
    """Load analysis_cache.json. Returns empty dict on missing/error."""
    import os
    path = cache_path or CACHE_PATH
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _find_cache_entry(cache: dict, brand: str, reference: str) -> Optional[dict]:
    """Find a reference in the cache by brand|model key or reference field."""
    for key, entry in cache.get("references", {}).items():
        if entry.get("reference") == reference:
            return entry
    return None


def _compute_derived_fields(
    row: LedgerRow,
    cache: Optional[dict] = None,
) -> dict:
    """Compute per-trade derived fields per plan Section 5.3.

    Returns a dict with: platform_fees, net_profit, roi_pct,
    median_at_trade, max_buy_at_trade, model_correct, premium_vs_median.
    Cache-dependent fields are None when cache is unavailable.
    """
    fees = ACCOUNT_FEES.get(row.account, 149)
    net = row.sell_price - row.buy_price - fees
    roi = (net / row.buy_price) * 100 if row.buy_price > 0 else 0

    result: dict[str, Any] = {
        "platform_fees": fees,
        "net_profit": net,
        "roi_pct": round(roi, 2),
        "median_at_trade": None,
        "max_buy_at_trade": None,
        "model_correct": None,
        "premium_vs_median": None,
    }

    if cache:
        entry = _find_cache_entry(cache, row.brand, row.reference)
        if entry:
            median = entry.get("median")
            mb_key = "max_buy_res" if row.account == "RES" else "max_buy_nr"
            max_buy = entry.get(mb_key)
            result["median_at_trade"] = median
            result["max_buy_at_trade"] = max_buy
            if max_buy is not None:
                result["model_correct"] = (
                    row.buy_price <= max_buy and net > 0
                )
            if median and median > 0:
                result["premium_vs_median"] = round(
                    ((row.sell_price - median) / median) * 100, 2
                )
    return result


# ─── Public API ───────────────────────────────────────────────────────


def run(
    ledger_path: Optional[str] = None,
    cache_path: Optional[str] = None,
    brand: Optional[str] = None,
    since: Optional[date] = None,
    reference: Optional[str] = None,
    cycle_id: Optional[str] = None,
) -> dict:
    """Load ledger, compute derived fields, aggregate, return summary.

    Filters: brand (case-insensitive), since (date), reference (exact),
    cycle_id (exact). All optional; defaults to full ledger.
    """
    rows = parse_ledger_csv(ledger_path)
    cache = _load_cache(cache_path)

    # Apply filters
    if brand:
        brand_lower = brand.lower()
        rows = [r for r in rows if r.brand.lower() == brand_lower]
    if since:
        rows = [r for r in rows if r.date_closed >= since]
    if reference:
        rows = [r for r in rows if r.reference == reference]
    if cycle_id:
        rows = [r for r in rows if r.cycle_id == cycle_id]

    # Compute derived fields
    enriched = []
    for row in rows:
        derived = _compute_derived_fields(row, cache)
        enriched.append({
            "date_closed": row.date_closed.isoformat(),
            "cycle_id": row.cycle_id,
            "brand": row.brand,
            "reference": row.reference,
            "account": row.account,
            "buy_price": row.buy_price,
            "sell_price": row.sell_price,
            **derived,
        })

    # Aggregates
    if enriched:
        nets = [t["net_profit"] for t in enriched]
        rois = [t["roi_pct"] for t in enriched]
        profitable = sum(1 for n in nets if n > 0)
        summary = {
            "total_trades": len(enriched),
            "profitable": profitable,
            "win_rate": round(profitable / len(enriched) * 100, 1),
            "total_net_profit": round(sum(nets), 2),
            "avg_roi_pct": round(statistics.mean(rois), 2),
            "total_deployed": round(sum(t["buy_price"] for t in enriched), 2),
        }
    else:
        summary = {
            "total_trades": 0,
            "profitable": 0,
            "win_rate": 0,
            "total_net_profit": 0,
            "avg_roi_pct": 0,
            "total_deployed": 0,
        }

    return {"trades": enriched, "summary": summary}


def reference_confidence(
    ledger_path: Optional[str] = None,
    cache_path: Optional[str] = None,
    brand: str = "",
    reference: str = "",
) -> Optional[dict]:
    """Per-reference confidence scoring per plan Section 5.6.

    Returns None if no trades found for the brand+reference pair.
    """
    rows = parse_ledger_csv(ledger_path)
    cache = _load_cache(cache_path)

    brand_lower = brand.lower()
    trades = [r for r in rows
              if r.brand.lower() == brand_lower and r.reference == reference]
    if not trades:
        return None

    derived_list = [_compute_derived_fields(t, cache) for t in trades]

    profitable = sum(1 for d in derived_list if d["net_profit"] > 0)
    rois = [d["roi_pct"] for d in derived_list]
    premiums = [d["premium_vs_median"] for d in derived_list
                if d["premium_vs_median"] is not None]

    return {
        "trades": len(trades),
        "profitable": profitable,
        "win_rate": round(profitable / len(trades) * 100, 1),
        "avg_roi": round(statistics.mean(rois), 1),
        "avg_premium": round(statistics.mean(premiums), 1) if premiums else None,
        "last_trade": max(t.date_closed for t in trades).isoformat(),
    }


def cycle_rollup(
    cycle_id: str,
    ledger_path: Optional[str] = None,
    cache_path: Optional[str] = None,
    cycle_focus: Optional[dict] = None,
) -> dict:
    """Produce cycle_outcome structure per plan Section 5.7."""
    rows = parse_ledger_csv(ledger_path)
    cache = _load_cache(cache_path)

    cycle_rows = [r for r in rows if r.cycle_id == cycle_id]

    start, end = cycle_date_range(cycle_id)
    focus_refs = set()
    if cycle_focus and cycle_focus.get("cycle_id") == cycle_id:
        for t in cycle_focus.get("targets", []):
            ref = t.get("reference") if isinstance(t, dict) else t
            if ref:
                focus_refs.add(ref)

    trade_entries = []
    nets = []
    rois = []
    deployed = []
    in_focus_count = 0
    off_cycle_count = 0

    for row in cycle_rows:
        derived = _compute_derived_fields(row, cache)
        in_focus = row.reference in focus_refs if focus_refs else False
        if in_focus:
            in_focus_count += 1
        else:
            off_cycle_count += 1
        nets.append(derived["net_profit"])
        rois.append(derived["roi_pct"])
        deployed.append(row.buy_price)
        trade_entries.append({
            "date": row.date_closed.isoformat(),
            "brand": row.brand,
            "reference": row.reference,
            "account": row.account,
            "buy": row.buy_price,
            "sell": row.sell_price,
            "net": derived["net_profit"],
            "roi": derived["roi_pct"],
            "in_focus": in_focus,
        })

    profitable = sum(1 for n in nets if n > 0) if nets else 0
    total_deployed = sum(deployed) if deployed else 0
    total_net = sum(nets) if nets else 0

    # Cycle focus hit/miss analysis
    focus_section: dict[str, Any] = {}
    if focus_refs:
        traded_refs = {row.reference for row in cycle_rows}
        hits = sorted(focus_refs & traded_refs)
        misses = sorted(focus_refs - traded_refs)
        off_cycle = sorted(traded_refs - focus_refs)
        focus_section = {
            "targeted_references": sorted(focus_refs),
            "hits": hits,
            "misses": misses,
            "off_cycle_trades": off_cycle,
        }

    return {
        "cycle_id": cycle_id,
        "date_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "trades": trade_entries,
        "summary": {
            "total_trades": len(trade_entries),
            "profitable": profitable,
            "in_focus_count": in_focus_count,
            "off_cycle_count": off_cycle_count,
            "avg_roi": round(statistics.mean(rois), 1) if rois else 0,
            "total_net": round(total_net, 2),
            "capital_deployed": round(total_deployed, 2),
            "capital_returned": round(total_deployed + total_net, 2),
        },
        "cycle_focus": focus_section,
    }
