"""Orchestrate the full Grailzee analysis pipeline.

Net-new in v2. Composes Phases 6-14: ingest (pre-done) -> score ->
trends -> changes -> breakouts -> watchlist -> brands -> ledger ->
cycle rollup -> output builders -> cache write.

v3 (2b): Step 6 uses load_and_canonicalize + analyze_buckets.run instead of
analyze_references.run. build_shortlist reads references from the v3 cache.

Called by the report capability (Section 10.1):
    python3 scripts/run_analysis.py <csv> [<csv> ...] --output-dir DIR

Returns {"unnamed", "cycle_id"} on success.
Returns {"status": "error", "error": str} on failure.

Usage:
    run_analysis.py <csv_path> [<csv_path> ...] --output-dir DIR
        [--ledger PATH] [--cache PATH] [--backup PATH]
        [--name-cache PATH] [--cycle-focus PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from opentelemetry.trace import StatusCode

from scripts.grailzee_common import (
    CACHE_PATH,
    OUTPUT_PATH,
    analyzer_config_source,
    cycle_id_from_csv,
    get_tracer,
    load_analyzer_config,
    load_name_cache,
    load_sourcing_rules,
    prev_cycle,
    sourcing_rules_source,
)

from scripts import analyze_buckets
from scripts import analyze_trends
from scripts.ingest import load_and_canonicalize
from scripts import analyze_changes
from scripts import analyze_breakouts
from scripts import analyze_watchlist
from scripts import read_ledger
from scripts import roll_cycle
from scripts import build_shortlist
from scripts import write_cache

tracer = get_tracer(__name__)

# Signals that indicate a reference is worth a name-cache lookup.
# Pass = too risky to buy; Low data = too few sales to score.
# Neither warrants web resolution.
_SIGNALS_WORTH_RESOLVING: frozenset[str] = frozenset(
    {"Strong", "Normal", "Reserve", "Careful"}
)


def run_analysis(
    csv_paths: list[str],
    output_folder: str,
    ledger_path: str | None = None,
    cache_path: str | None = None,
    backup_path: str | None = None,
    name_cache_path: str | None = None,
    cycle_focus_path: str | None = None,
) -> dict:
    """Run the full analysis pipeline.

    csv_paths: normalized CSVs, newest first.
    Returns {"unnamed": [{"reference": str, "brand": str}], "cycle_id": str}
    """
    if not csv_paths:
        raise ValueError("No CSV paths provided; at least one report is required.")

    current_csv = csv_paths[0]
    source_report = Path(current_csv).name
    current_cycle_id = cycle_id_from_csv(current_csv)

    cfg = load_analyzer_config()
    pricing_window = cfg["windows"]["pricing_reports"]
    pricing_csv_paths = csv_paths[:pricing_window]

    # Step 6: Score references via v3 bucket construction (CanonicalRow pipeline)
    with tracer.start_as_current_span("analyze_buckets.run") as span:
        span.set_attribute("pricing_csv_count", len(pricing_csv_paths))
        span.set_attribute("windows.pricing_reports", pricing_window)
        try:
            pricing_paths = [Path(p) for p in pricing_csv_paths]
            rows, ingest_summary = load_and_canonicalize(pricing_paths)
            span.set_attribute("canonical_rows", ingest_summary.canonical_rows_emitted)
            all_results = analyze_buckets.run(rows, name_cache_path)
            span.set_attribute("refs_count", len(all_results.get("references", {})))
            # B.4: buckets where all sales land in a single condition category
            all_bucket_dicts = [
                bd
                for rd in (
                    list(all_results.get("references", {}).values())
                    + list(all_results.get("dj_configs", {}).values())
                )
                for bd in rd.get("buckets", {}).values()
            ]
            span.set_attribute(
                "condition_mix_single_bucket_count",
                sum(
                    1 for bd in all_bucket_dicts
                    if sum(
                        1 for v in (bd.get("condition_mix") or {}).values() if v > 0
                    ) == 1
                ),
            )
            # B.5: calibration canary; buckets where max_buy_nr clears at a loss.
            # Zero under the current formula; non-zero flags margin/fee drift.
            span.set_attribute(
                "negative_expected_net_nr_count",
                sum(
                    1 for bd in all_bucket_dicts
                    if (bd.get("expected_net_at_median_nr") or 0) < 0
                ),
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    # Step 7: Trends (full window, up to 6 per Section 6.2)
    with tracer.start_as_current_span("analyze_trends.run") as span:
        span.set_attribute("csv_count", len(csv_paths))
        try:
            trends = analyze_trends.run(csv_paths, name_cache_path)
            span.set_attribute("trend_count", len(trends.get("trends", {})))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    # Step 8: Two-period analyzers
    prev_csv = csv_paths[1] if len(csv_paths) >= 2 else None

    with tracer.start_as_current_span("analyze_changes.run") as span:
        span.set_attribute("has_prev", prev_csv is not None)
        try:
            changes = analyze_changes.run(current_csv, prev_csv, name_cache_path)
            span.set_attribute("emerged_count", len(changes.get("emerged", [])))
            span.set_attribute("faded_count", len(changes.get("faded", [])))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    with tracer.start_as_current_span("analyze_breakouts.run") as span:
        span.set_attribute("has_prev", prev_csv is not None)
        try:
            breakouts = analyze_breakouts.run(current_csv, prev_csv, name_cache_path)
            span.set_attribute("breakout_count", breakouts.get("count", 0))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    with tracer.start_as_current_span("analyze_watchlist.run") as span:
        span.set_attribute("has_prev", prev_csv is not None)
        try:
            watchlist_result = analyze_watchlist.run(current_csv, prev_csv, name_cache_path)
            span.set_attribute("watchlist_count", watchlist_result.get("count", 0))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    brands: dict = {"brands": {}, "count": 0}

    # Step 10: Ledger stats
    with tracer.start_as_current_span("read_ledger.run") as span:
        try:
            ledger_stats = read_ledger.run(ledger_path, cache_path)
            span.set_attribute("trade_count", len(ledger_stats.get("trades", [])))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    # Step 12: Cycle rollup (fatal).
    # load_cycle_focus() returns None for missing files; parse_ledger_csv()
    # returns [] for a missing or empty ledger — both handle first-run cleanly.
    # Any remaining exception (write error, malformed cache JSON, bad output
    # path) means the cycle outcome file was not written. Swallowing that
    # would leave the strategy skill with stale cycle data.
    previous_cycle_id = prev_cycle(current_cycle_id)
    with tracer.start_as_current_span("roll_cycle.run") as span:
        span.set_attribute("previous_cycle_id", previous_cycle_id)
        try:
            roll_cycle.run(
                previous_cycle_id=previous_cycle_id,
                ledger_path=ledger_path,
                cache_path=cache_path,
                cycle_focus_path=cycle_focus_path,
                output_path=(
                    str(Path(cache_path).parent
                        / f"cycle_outcome_{previous_cycle_id}.json")
                    if cache_path else None
                ),
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    # Step 13: Unnamed references with actionable signals.
    # Only include refs that are (a) absent from the name cache and
    # (b) have at least one bucket whose signal indicates trading value.
    # Pass and Low data refs are excluded — no value in resolving names
    # for references we would never buy.
    unnamed = [
        {"reference": ref, "brand": data.get("brand", "?")}
        for ref, data in all_results.get("references", {}).items()
        if not data.get("named", False)
        and any(
            bd.get("signal") in _SIGNALS_WORTH_RESOLVING
            for bd in data.get("buckets", {}).values()
        )
    ]

    # Step 15: Cache write
    market_window = {
        "pricing_reports": [Path(p).name for p in pricing_csv_paths],
        "trend_reports": [Path(p).name for p in csv_paths],
    }
    with tracer.start_as_current_span("write_cache.run") as span:
        span.set_attribute("cycle_id", current_cycle_id)
        span.set_attribute("cache_path", cache_path or "")
        try:
            write_cache.run(
                all_results, trends, changes, breakouts,
                watchlist_result, brands, ledger_stats, current_cycle_id,
                source_report=source_report, market_window=market_window,
                cache_path=cache_path, backup_path=backup_path,
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    # Step 16: Shortlist CSV (B.7; strategy reading-partner input).
    # Sibling artifact to the cache; writes to the cache's parent
    # directory when --cache overrides the default. Reads ``references``
    # from the just-written cache file, NOT from in-memory ``all_results``.
    resolved_cache_path = cache_path or CACHE_PATH
    shortlist_state_path = str(Path(resolved_cache_path).parent)
    with tracer.start_as_current_span("build_shortlist.run"):
        with open(resolved_cache_path, "r", encoding="utf-8") as f:
            cache_dict = json.load(f)
        build_shortlist.run(
            cache_dict.get("references", {}),
            cycle_id=current_cycle_id,
            state_path=shortlist_state_path,
        )

    return {
        "unnamed": sorted(unnamed, key=lambda x: x["reference"]),
        "cycle_id": current_cycle_id,
    }


# --- CLI entry ────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", help="Normalized CSVs, newest first")
    parser.add_argument("--output-dir", default=OUTPUT_PATH)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--backup", default=None)
    parser.add_argument("--name-cache", default=None)
    parser.add_argument("--cycle-focus", default=None)
    args = parser.parse_args()

    with tracer.start_as_current_span("run_analysis") as span:
        span.set_attribute("csv_count", len(args.csv_paths))

        cfg = load_analyzer_config()
        span.set_attribute("analyzer_config_source", analyzer_config_source())
        span.set_attribute("windows.pricing_reports", cfg["windows"]["pricing_reports"])
        span.set_attribute("windows.trend_reports", cfg["windows"]["trend_reports"])

        # Prime the sourcing_rules cache so the outer span can report
        # the source. First-call-wins: any in-process test code that
        # imports run_analysis must call _reset_sourcing_rules_cache()
        # before its own load_sourcing_rules(path=...) to avoid the
        # cached default leaking across test boundaries.
        load_sourcing_rules()
        span.set_attribute("sourcing_rules_source", sourcing_rules_source())

        try:
            result = run_analysis(
                args.csv_paths, args.output_dir,
                ledger_path=args.ledger,
                cache_path=args.cache,
                backup_path=args.backup,
                name_cache_path=args.name_cache,
                cycle_focus_path=args.cycle_focus,
            )
            span.set_attribute("cycle_id", result["cycle_id"])
            span.set_attribute("unnamed_count", len(result["unnamed"]))

            print(json.dumps(result, indent=2, default=str))
            return 0

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            error_result = {"status": "error", "error": str(exc)}
            print(json.dumps(error_result), file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
