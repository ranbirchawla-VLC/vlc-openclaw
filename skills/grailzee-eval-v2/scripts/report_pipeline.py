"""Ingest + glob + analyze wrapper for the report capability.

Phase 19.5: collapses the three-step `ingest_report -> glob -> run_analysis`
chain into one callable so `capabilities/report.md` can invoke a single
command. One new OTel span covers ingest + glob only; `run_analysis` has
its own per-stage spans.

Usage:
    python3 scripts/report_pipeline.py <input.xlsx> --output-folder DIR
        [--csv-dir DIR] [--ledger PATH] [--cache PATH] [--backup PATH]
        [--name-cache PATH] [--cycle-focus PATH] [--trend-window N]

Returns the same dict as run_analysis: {summary_path, unnamed, cycle_id}.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from opentelemetry.trace import StatusCode

from scripts import ingest_report, run_analysis
from scripts.grailzee_common import CSV_PATH, OUTPUT_PATH, get_tracer

tracer = get_tracer(__name__)

DEFAULT_TREND_WINDOW = 6
CSV_GLOB = "grailzee_*.csv"


def run_pipeline(
    input_report: str,
    output_folder: str,
    *,
    csv_dir: str | None = None,
    ledger_path: str | None = None,
    cache_path: str | None = None,
    backup_path: str | None = None,
    name_cache_path: str | None = None,
    cycle_focus_path: str | None = None,
    trend_window: int = DEFAULT_TREND_WINDOW,
) -> dict:
    """Ingest a Grailzee Pro workbook, gather the trend window, run analysis.

    Returns run_analysis's dict unchanged: {summary_path, unnamed, cycle_id}.
    Raises ValueError if the csv_dir contains no normalized CSVs after ingest.

    Newest-first ordering relies on ingest_report naming its output
    `grailzee_YYYY-MM-DD.csv`: the ISO date suffix makes lexical-descending
    sort equivalent to chronological-descending.
    """
    resolved_csv_dir = csv_dir or CSV_PATH

    with tracer.start_as_current_span("report_pipeline.ingest_glob") as span:
        span.set_attribute("input_report", input_report)
        span.set_attribute("csv_dir", resolved_csv_dir)
        span.set_attribute("trend_window", trend_window)
        try:
            ingest_result = ingest_report.ingest(
                input_report, output_dir=resolved_csv_dir,
            )
            span.set_attribute("output_csv", ingest_result["output_csv"])
            span.set_attribute("rows_written", ingest_result["rows_written"])

            pattern = str(Path(resolved_csv_dir) / CSV_GLOB)
            matches = sorted(glob.glob(pattern), reverse=True)
            if not matches:
                raise ValueError(
                    f"No CSVs found in {resolved_csv_dir!r} "
                    f"matching {CSV_GLOB!r}"
                )
            csv_paths = matches[:trend_window]
            span.set_attribute("csv_count", len(csv_paths))
            span.set_attribute("csv_newest", Path(csv_paths[0]).name)
            span.set_attribute("csv_oldest", Path(csv_paths[-1]).name)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    return run_analysis.run_analysis(
        csv_paths,
        output_folder,
        ledger_path=ledger_path,
        cache_path=cache_path,
        backup_path=backup_path,
        name_cache_path=name_cache_path,
        cycle_focus_path=cycle_focus_path,
    )


# --- CLI entry ────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_report", help="Path to Grailzee Pro .xlsx workbook")
    parser.add_argument("--output-folder", default=OUTPUT_PATH)
    parser.add_argument("--csv-dir", default=None)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--backup", default=None)
    parser.add_argument("--name-cache", default=None)
    parser.add_argument("--cycle-focus", default=None)
    parser.add_argument("--trend-window", type=int, default=DEFAULT_TREND_WINDOW)
    args = parser.parse_args()

    with tracer.start_as_current_span("report_pipeline.run") as span:
        span.set_attribute("input_report", args.input_report)
        try:
            result = run_pipeline(
                args.input_report,
                args.output_folder,
                csv_dir=args.csv_dir,
                ledger_path=args.ledger,
                cache_path=args.cache,
                backup_path=args.backup,
                name_cache_path=args.name_cache,
                cycle_focus_path=args.cycle_focus,
                trend_window=args.trend_window,
            )
            span.set_attribute("cycle_id", result["cycle_id"])
            span.set_attribute("unnamed_count", len(result["unnamed"]))
            print(json.dumps(result, indent=2, default=str))
            return 0
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
