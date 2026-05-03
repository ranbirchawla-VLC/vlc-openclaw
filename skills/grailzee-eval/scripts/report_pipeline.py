"""Ingest + glob + analyze wrapper for the report capability.

Phase 19.5: collapses the three-step `ingest_report -> glob -> run_analysis`
chain into one callable so `capabilities/report.md` can invoke a single
command. One new OTel span covers ingest + glob only; `run_analysis` has
its own per-stage spans.

Usage (plugin / JSON argv):
    python3 scripts/report_pipeline.py '{"input_report": "/path/to.xlsx"}'

Usage (argparse CLI):
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
from pydantic import BaseModel, ConfigDict, ValidationError

from scripts import ingest_report, run_analysis
from scripts.grailzee_common import (
    CSV_PATH,
    OUTPUT_PATH,
    REPORTS_PATH,
    get_tracer,
    load_analyzer_config,
)

tracer = get_tracer(__name__)

CSV_GLOB = "grailzee_*.csv"


# ─── Exception hierarchy ─────────────────────────────────────────────


class XlsxParseError(Exception):
    """Excel workbook cannot be read or parsed."""


class IngestError(Exception):
    """CSV output absent or unreadable after xlsx ingest."""


class AnalysisError(Exception):
    """Bucket aggregation or report computation failed."""


class SummaryWriteError(Exception):
    """Summary file could not be written."""


# ─── Plugin input contract ────────────────────────────────────────────


class _Input(BaseModel):
    """Plugin input model. No business fields; this is a no-input capability.

    extra='forbid' rejects unknown fields as bad_input, preventing silent
    drift between the registered JSON Schema and the Python contract.
    All run-time path overrides are extracted as test hooks before _Input
    validation and never reach this model.
    """

    model_config = ConfigDict(extra="forbid")


_TEST_HOOK_KEYS: frozenset[str] = frozenset({
    "input_report",
    "csv_dir",
    "output_folder",
    "ledger_path",
    "cache_path",
    "backup_path",
    "name_cache_path",
    "cycle_focus_path",
    "trend_window",
})

_ERROR_TYPE: dict[type, str] = {
    XlsxParseError: "xlsx_parse_error",
    IngestError: "ingest_error",
    AnalysisError: "analysis_error",
    SummaryWriteError: "summary_write_error",
}


def _error_envelope(error_type: str, message: str) -> dict:
    return {"status": "error", "error_type": error_type, "message": message}


def _configured_trend_window() -> int:
    """Live trend-window value from analyzer_config.json.

    Falls back to the factory default via load_analyzer_config()'s
    own fallback behavior when the config file is missing.
    """
    return load_analyzer_config()["windows"]["trend_reports"]


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
    trend_window: int | None = None,
) -> dict:
    """Ingest a Grailzee Pro workbook, gather the trend window, run analysis.

    Returns run_analysis's dict unchanged: {summary_path, unnamed, cycle_id}.
    Raises IngestError if the csv_dir contains no normalized CSVs after ingest.

    Newest-first ordering relies on ingest_report naming its output
    `grailzee_YYYY-MM-DD.csv`: the ISO date suffix makes lexical-descending
    sort equivalent to chronological-descending.
    """
    resolved_csv_dir = csv_dir or CSV_PATH
    resolved_trend_window = (
        trend_window if trend_window is not None else _configured_trend_window()
    )

    with tracer.start_as_current_span("report_pipeline.ingest_glob") as span:
        span.set_attribute("input_report", input_report)
        span.set_attribute("csv_dir", resolved_csv_dir)
        span.set_attribute("trend_window", resolved_trend_window)
        try:
            try:
                ingest_result = ingest_report.ingest(
                    input_report, output_dir=resolved_csv_dir,
                )
            except Exception as exc:
                raise XlsxParseError(str(exc)) from exc
            span.set_attribute("output_csv", ingest_result["output_csv"])
            span.set_attribute("rows_written", ingest_result["rows_written"])

            pattern = str(Path(resolved_csv_dir) / CSV_GLOB)
            matches = sorted(glob.glob(pattern), reverse=True)
            if not matches:
                raise IngestError(
                    f"No CSVs found in {resolved_csv_dir!r} "
                    f"matching {CSV_GLOB!r}"
                )
            csv_paths = matches[:resolved_trend_window]
            span.set_attribute("csv_count", len(csv_paths))
            span.set_attribute("csv_newest", Path(csv_paths[0]).name)
            span.set_attribute("csv_oldest", Path(csv_paths[-1]).name)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise

    try:
        return run_analysis.run_analysis(
            csv_paths,
            output_folder,
            ledger_path=ledger_path,
            cache_path=cache_path,
            backup_path=backup_path,
            name_cache_path=name_cache_path,
            cycle_focus_path=cycle_focus_path,
        )
    except OSError as exc:
        raise SummaryWriteError(str(exc)) from exc
    except Exception as exc:
        raise AnalysisError(str(exc)) from exc


# ─── Plugin dispatch ─────────────────────────────────────────────────


def _run_from_dict(data: dict) -> int:
    """JSON dispatch. Validates with _Input, auto-discovers xlsx, calls run_pipeline.

    Test hooks (all path overrides) are extracted before _Input validation so
    they never reach the strict model. All error paths emit _error_envelope()
    to stdout and return 0 per the §4.3 exit-0 contract.
    """
    hooks = {k: v for k, v in data.items() if k in _TEST_HOOK_KEYS}
    schema_data = {k: v for k, v in data.items() if k not in _TEST_HOOK_KEYS}

    try:
        _Input(**schema_data)
    except ValidationError as exc:
        errors = exc.errors()
        if any(e["type"] == "missing" for e in errors):
            missing = ", ".join(
                str(e["loc"][-1]) for e in errors if e["type"] == "missing"
            )
            print(json.dumps(_error_envelope("missing_arg", f"Missing required field: {missing}")))
        else:
            print(json.dumps(_error_envelope("bad_input", str(exc))))
        return 0

    input_report: str | None = hooks.get("input_report")
    if input_report is None:
        candidates = sorted(glob.glob(str(Path(REPORTS_PATH) / "*.xlsx")), reverse=True)
        if not candidates:
            print(json.dumps(_error_envelope("no_report", f"No .xlsx files found in {REPORTS_PATH!r}")))
            return 0
        input_report = candidates[0]

    output_folder: str = hooks.get("output_folder") or OUTPUT_PATH

    try:
        result = run_pipeline(
            input_report,
            output_folder,
            csv_dir=hooks.get("csv_dir"),
            ledger_path=hooks.get("ledger_path"),
            cache_path=hooks.get("cache_path"),
            backup_path=hooks.get("backup_path"),
            name_cache_path=hooks.get("name_cache_path"),
            cycle_focus_path=hooks.get("cycle_focus_path"),
            trend_window=hooks.get("trend_window"),
        )
    except (XlsxParseError, IngestError, AnalysisError, SummaryWriteError) as exc:
        print(json.dumps(_error_envelope(_ERROR_TYPE[type(exc)], str(exc))))
        return 0
    except Exception as exc:
        print(json.dumps(_error_envelope("internal_error", str(exc))))
        return 0

    print(json.dumps({"status": "ok", **result}, indent=2, default=str))
    return 0


def _run_from_argv() -> int:
    """Plugin spawnArgv entry point: reads sys.argv[1] as JSON string."""
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps(_error_envelope("bad_input", f"Invalid JSON in argv[1]: {exc}")))
        return 0
    if not isinstance(payload, dict):
        print(json.dumps(_error_envelope("bad_input", f"Expected JSON object, got {type(payload).__name__}")))
        return 0
    return _run_from_dict(payload)


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
    parser.add_argument(
        "--trend-window",
        type=int,
        default=None,
        help=(
            "Override the trend-window size. Default reads "
            "windows.trend_reports from analyzer_config.json "
            "(with factory-default fallback if the file is missing)."
        ),
    )
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
    # argv[1] starts with "{" → JSON payload from spawnArgv plugin dispatch.
    if len(sys.argv) > 1 and sys.argv[1].startswith("{"):
        sys.exit(_run_from_argv())
    # No extra argv → stdin path (legacy spawnStdin compat; also used in tests).
    if len(sys.argv) == 1:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(json.dumps(_error_envelope("bad_input", f"Invalid JSON on stdin: {exc}")))
            sys.exit(0)
        sys.exit(_run_from_dict(payload))
    # argv[1] present but not JSON → argparse path (direct CLI testing).
    sys.exit(main())
