"""Phase 2b v3 bucket construction and scoring over CanonicalRow instances.

Replaces analyze_references.py as the scoring entry point for schema v3.
Consumes list[CanonicalRow] from ingest.py; groups by four-axis bucket key
per the locked schema v3 decisions; scores each bucket via the existing
analyze_reference primitives.

analyze_references.py is kept in-tree for:
  - evaluate_deal._on_demand_analysis (fallback path, not cache-backed)
  - 2c cleanup per the non-goals locked in the 2b prompt

Schema v3 keying tuple per Decision Lock 2026-04-24:
(reference, dial_numerals, auction_type, dial_color)

bucket_key serialization: all three axes lowercased, pipe-joined:
f"{dial_numerals.lower()}|{auction_type.lower()}|{dial_color.lower()}".
Example: "arabic|nr|black". The keying axes stay case-preserved inside
the bucket body (dial_numerals="Arabic"); only the dict key is lowercase
so consumers have a case-uniform index.

Named-special (Decision 3) is metadata on the bucket, not a keying axis.

Per G4 (patched 2026-04-24 plan-review):
  - Market fields: per-bucket
  - Ledger-derived fields: reference-level (set by write_cache)
  - Trend and momentum: reference-level (set by write_cache; cross-report)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    classify_dj_config,
    get_tracer,
    load_analyzer_config,
    load_name_cache,
    NAME_CACHE_PATH,
)
from scripts.analyze_references import (
    analyze_reference,
    _condition_mix,
)
from scripts.ingest import CanonicalRow

tracer = get_tracer(__name__)

DJ_PARENT_REFERENCE = "126300"


# ─── Bucket key ───────────────────────────────────────────────────────


def bucket_key(row: CanonicalRow) -> str:
    """Serialize the four-axis bucket key, all axes lowercased.

    Format: "{dial_numerals}|{auction_type}|{dial_color}" with every axis
    lowercased so consumers get a case-uniform key (e.g. "arabic|nr|black").
    The bucket body preserves canonical case on its dial_numerals etc.
    fields; only the dict key is normalized here.
    """
    return (
        f"{row.dial_numerals.lower()}"
        f"|{row.auction_type.lower()}"
        f"|{row.dial_color.lower()}"
    )


# ─── Bucket construction ──────────────────────────────────────────────


def build_buckets(rows: list[CanonicalRow]) -> dict[str, list[CanonicalRow]]:
    """Group rows by four-axis bucket key.

    Returns dict of bucket_key -> non-empty row list. Bucket construction
    is driven by present rows; no empty buckets are created.
    """
    buckets: dict[str, list[CanonicalRow]] = defaultdict(list)
    for row in rows:
        buckets[bucket_key(row)].append(row)
    return dict(buckets)


# ─── named_special resolution ─────────────────────────────────────────


def _named_special_for_bucket(rows: list[CanonicalRow]) -> str | None:
    """G6: resolve named_special for a bucket using longest-match-wins.

    If rows within a bucket carry different named_special slugs, takes the
    longest slug (proxy for longest source pattern match per ingest.py
    longest-match-wins rule). Alphabetical tiebreak for determinism.
    Returns None if no row carries a named_special.
    """
    present = {r.named_special for r in rows if r.named_special is not None}
    if not present:
        return None
    return max(present, key=lambda s: (len(s), s))


# ─── Row adapter ──────────────────────────────────────────────────────


def _row_to_sale(row: CanonicalRow) -> dict:
    """Adapt a CanonicalRow to the sale dict shape analyze_reference expects.

    Keys: price, condition, papers, reference, make, title, sell_through_pct.
    """
    return {
        "price": row.sold_for,
        "condition": row.condition,
        "papers": row.papers,
        "reference": row.reference,
        "make": row.brand,
        "title": row.auction_descriptor,
        "sell_through_pct": row.sell_through_pct,
    }


def _st_pct_for_rows(rows: list[CanonicalRow]) -> float | None:
    """Mean sell_through_pct across rows; None if no populated values."""
    vals = [r.sell_through_pct for r in rows if r.sell_through_pct is not None]
    return statistics.mean(vals) if vals else None


# ─── Per-bucket scoring ────────────────────────────────────────────────


def score_bucket(rows: list[CanonicalRow]) -> dict:
    """Score one bucket from its CanonicalRow instances.

    Delegates all market computation to analyze_references.analyze_reference.
    Below-threshold buckets (volume < min_sales_for_scoring) carry
    signal="Low data" with null on market fields; volume, st_pct, and
    condition_mix are always populated.
    """
    cfg = load_analyzer_config()
    min_sales: int = cfg["scoring"]["min_sales_for_scoring"]

    sales = [_row_to_sale(r) for r in rows]
    st_pct = _st_pct_for_rows(rows)
    named = _named_special_for_bucket(rows)

    base: dict[str, Any] = {
        "dial_numerals": rows[0].dial_numerals,
        "auction_type": rows[0].auction_type.lower(),
        "dial_color": rows[0].dial_color,
        "named_special": named,
        "volume": len(rows),
        "st_pct": st_pct,
        "condition_mix": _condition_mix(sales),
    }

    if len(rows) < min_sales:
        base.update({
            "signal": "Low data",
            "median": None,
            "max_buy_nr": None,
            "max_buy_res": None,
            "risk_nr": None,
            "capital_required_nr": None,
            "capital_required_res": None,
            "expected_net_at_median_nr": None,
            "expected_net_at_median_res": None,
        })
        return base

    scored = analyze_reference(sales, st_pct)
    if scored is None:
        # analyze_reference returns None only on empty sales; unreachable
        # when len(rows) >= min_sales >= 3, but guarded for safety.
        base.update({
            "signal": "Low data",
            "median": None,
            "max_buy_nr": None,
            "max_buy_res": None,
            "risk_nr": None,
            "capital_required_nr": None,
            "capital_required_res": None,
            "expected_net_at_median_nr": None,
            "expected_net_at_median_res": None,
        })
        return base

    base.update({
        "signal": scored["signal"],
        "median": scored["median"],
        "max_buy_nr": scored["max_buy_nr"],
        "max_buy_res": scored["max_buy_res"],
        "risk_nr": scored["risk_nr"],
        "capital_required_nr": scored["capital_required_nr"],
        "capital_required_res": scored["capital_required_res"],
        "expected_net_at_median_nr": scored["expected_net_at_median_nr"],
        "expected_net_at_median_res": scored["expected_net_at_median_res"],
    })
    return base


def _score_reference_buckets(rows: list[CanonicalRow]) -> dict[str, dict]:
    """Build and score all buckets for a set of rows.

    Returns {bucket_key: scored_bucket_dict}.
    """
    raw = build_buckets(rows)
    return {bk: score_bucket(brows) for bk, brows in raw.items()}


# ─── DJ config breakout ────────────────────────────────────────────────


def _score_dj_configs(
    rows_126300: list[CanonicalRow],
    name_cache: dict,
) -> dict[str, dict]:
    """Build and score DJ 126300 config breakouts per G5.

    Classifies each 126300 row via classify_dj_config(auction_descriptor),
    builds four-axis buckets per config, scores per T3. Returns {} when
    config_breakout is not set in name_cache["126300"] or when no 126300
    rows are present.

    Reference-level ledger field inheritance from parent 126300 happens
    in write_cache (same as v2 pattern). Only market fields (buckets) are
    produced here.
    """
    if not rows_126300:
        return {}
    if not name_cache.get(DJ_PARENT_REFERENCE, {}).get("config_breakout", False):
        return {}

    parent_named = DJ_PARENT_REFERENCE in name_cache

    classified: dict[str, list[CanonicalRow]] = defaultdict(list)
    for row in rows_126300:
        cfg = classify_dj_config(row.auction_descriptor)
        if cfg is not None:
            classified[cfg].append(row)

    result = {}
    for cfg_name, cfg_rows in classified.items():
        result[cfg_name] = {
            "brand": "Rolex",
            "model": f"DJ 41 {cfg_name}",
            "reference": DJ_PARENT_REFERENCE,
            "named": parent_named,
            "buckets": _score_reference_buckets(cfg_rows),
        }
    return result


# ─── Full-dataset scoring ──────────────────────────────────────────────


def score_all_references(
    rows: list[CanonicalRow],
    name_cache: dict,
) -> dict:
    """Build four-axis buckets and score all references.

    Consumes list[CanonicalRow] from ingest.load_and_canonicalize.
    Returns the v3 intermediate all_results dict:
        {
            "references": {ref: reference_record},
            "dj_configs": {cfg_name: reference_record},
            "unnamed": [ref, ...],
        }
    where each reference_record contains:
        brand, model, reference, named, buckets.
    Ledger-derived and trend-derived fields are added by write_cache.
    """
    with tracer.start_as_current_span("analyze_buckets.score_all_references") as span:
        by_ref: dict[str, list[CanonicalRow]] = defaultdict(list)
        for row in rows:
            by_ref[row.reference].append(row)

        # Expand alt_refs so lookups against Pro-report ref variants
        # (e.g. "M79830RB") hit the curated entry keyed as "79830RB".
        # Primary keys win; alt_refs only fill gaps. named=True covers
        # both primary-key hits and alt_ref hits — both are curated names.
        lookup_cache: dict[str, dict] = dict(name_cache)
        for entry in name_cache.values():
            for alt in entry.get("alt_refs", []):
                if alt not in lookup_cache:
                    lookup_cache[alt] = entry

        cfg = load_analyzer_config()
        min_sales: int = cfg["scoring"]["min_sales_for_scoring"]

        references: dict[str, dict] = {}
        unnamed: list[str] = []
        rows_126300: list[CanonicalRow] = []

        total_bucket_count = 0
        scored_bucket_count = 0
        below_threshold_count = 0

        for ref, ref_rows in by_ref.items():
            cache_entry = lookup_cache.get(ref, {})
            brand: str = cache_entry.get("brand") or (ref_rows[0].brand if ref_rows else "?")
            model: str = cache_entry.get("model") or ref
            named: bool = ref in lookup_cache

            if not named:
                unnamed.append(ref)

            buckets = _score_reference_buckets(ref_rows)

            for bd in buckets.values():
                total_bucket_count += 1
                if bd["volume"] >= min_sales:
                    scored_bucket_count += 1
                else:
                    below_threshold_count += 1

            references[ref] = {
                "brand": brand,
                "model": model,
                "reference": ref,
                "named": named,
                "buckets": buckets,
            }

            if ref == DJ_PARENT_REFERENCE:
                rows_126300 = ref_rows

        dj_configs = _score_dj_configs(rows_126300, lookup_cache)

        span.set_attribute("reference_count", len(references))
        span.set_attribute("total_bucket_count", total_bucket_count)
        span.set_attribute("scored_bucket_count", scored_bucket_count)
        span.set_attribute("below_threshold_bucket_count", below_threshold_count)
        span.set_attribute("dj_config_count", len(dj_configs))
        span.set_attribute("outcome", "ok")

        return {
            "references": references,
            "dj_configs": dj_configs,
            "unnamed": sorted(unnamed),
        }


# ─── Public entry point ────────────────────────────────────────────────


def run(
    rows: list[CanonicalRow],
    name_cache_path: str | None = None,
) -> dict:
    """Load name cache and score all references. Returns all_results dict."""
    name_cache = load_name_cache(name_cache_path)
    return score_all_references(rows, name_cache)


# ─── CLI ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI for spot-check use. Reads one or more CSVs via ingest, scores.

    Usage:
        python3 scripts/analyze_buckets.py <csv> [<csv> ...] [--name-cache PATH]
    Prints JSON summary to stdout.
    """
    from scripts.ingest import load_and_canonicalize

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", help="Canonical CSV files")
    parser.add_argument("--name-cache", default=NAME_CACHE_PATH)
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.csv_paths]
    rows, summary = load_and_canonicalize(paths)
    result = run(rows, args.name_cache)

    out = {
        "ingest_summary": {
            "source_rows_total": summary.source_rows_total,
            "canonical_rows_emitted": summary.canonical_rows_emitted,
        },
        "reference_count": len(result["references"]),
        "dj_config_count": len(result["dj_configs"]),
        "unnamed_count": len(result["unnamed"]),
        "total_bucket_count": sum(
            len(rd["buckets"]) for rd in result["references"].values()
        ),
        "scored_bucket_count": sum(
            1 for rd in result["references"].values()
            for bd in rd["buckets"].values()
            if bd.get("signal") != "Low data" and bd.get("volume", 0) >= 3
        ),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
