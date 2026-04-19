"""OUTBOUND bundle builder.

Packages the current GrailzeeData state into a single ``.zip`` for upload to
a Chat strategy session. The bundle is written to
``<grailzee_root>/bundles/grailzee_outbound_<cycle_id>_<YYYYMMDD_HHMMSS_ffffff>.zip``.

Microsecond precision in the timestamp matches the write_cache backup
rotation convention (two bundles generated in the same second get distinct
filenames).

Roles included
--------------
================  ========  ========================================
role              required  source
================  ========  ========================================
analysis_cache    yes       state/analysis_cache.json
cycle_focus_      yes       state/cycle_focus.json
  current
monthly_goals     yes       state/monthly_goals.json
quarterly_        yes       state/quarterly_allocation.json
  allocation
trade_ledger_     yes       state/trade_ledger.csv, filtered to rows
  snippet                   whose ``cycle_id`` equals the current
                            cycle_id
sourcing_brief    yes       output/briefs/sourcing_brief_<cycle>.json
latest_report_    yes       reports_csv/grailzee_YYYY-MM-DD.csv,
  csv                       most recent by lexical-desc sort
================  ========  ========================================

Boundary detection
------------------
``scope.month_boundary`` / ``scope.quarter_boundary`` indicate whether this
bundle represents the first run of a new month / quarter. The comparison
anchor is the most recent entry in ``state/run_history.json`` whose
``cycle_id`` DIFFERS from the cache's current cycle_id (not simply the last
entry — the agent may already have appended an entry for the current cycle
before this script runs; comparing against itself would mask the boundary).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
SOURCE_TAG = "grailzee-cowork/build_bundle"
BUNDLE_KIND = "outbound"
REPORT_CSV_PATTERN = re.compile(r"^grailzee_\d{4}-\d{2}-\d{2}\.csv$")
CYCLE_ID_PATTERN = re.compile(r"^cycle_(\d{4})-(\d{2})$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _filename_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _parse_cycle_id(cycle_id: str) -> tuple[int, int]:
    """Return ``(year, month)`` for a ``cycle_YYYY-MM`` id.

    Raises ValueError on malformed input.
    """
    m = CYCLE_ID_PATTERN.match(cycle_id)
    if not m:
        raise ValueError(f"Malformed cycle_id {cycle_id!r}; expected cycle_YYYY-MM")
    return int(m.group(1)), int(m.group(2))


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _detect_boundaries(current_cycle_id: str, run_history_path: Path) -> dict[str, bool]:
    """Return ``{'month_boundary': bool, 'quarter_boundary': bool}``.

    Anchors on the most recent run_history entry whose cycle_id DIFFERS
    from ``current_cycle_id``. If history is absent, empty, or contains
    only the current cycle, both flags are False.
    """
    if not run_history_path.exists():
        return {"month_boundary": False, "quarter_boundary": False}
    try:
        history = json.loads(run_history_path.read_text())
    except json.JSONDecodeError as exc:
        # Don't block the bundle on a corrupt history file, but surface the
        # problem so the operator can notice and repair it.
        print(
            f"WARNING: run_history at {run_history_path} unparseable ({exc}); "
            f"boundary flags default to False.",
            file=sys.stderr,
        )
        return {"month_boundary": False, "quarter_boundary": False}
    runs = history.get("runs", []) if isinstance(history, dict) else []
    prior_cycle_id: str | None = None
    for entry in reversed(runs):
        if not isinstance(entry, dict):
            continue
        cid = entry.get("cycle_id")
        if cid and cid != current_cycle_id:
            prior_cycle_id = cid
            break
    if prior_cycle_id is None:
        return {"month_boundary": False, "quarter_boundary": False}
    try:
        curr_y, curr_m = _parse_cycle_id(current_cycle_id)
        prev_y, prev_m = _parse_cycle_id(prior_cycle_id)
    except ValueError:
        return {"month_boundary": False, "quarter_boundary": False}
    month_boundary = (curr_y, curr_m) != (prev_y, prev_m)
    quarter_boundary = (curr_y, _quarter_of(curr_m)) != (prev_y, _quarter_of(prev_m))
    return {"month_boundary": month_boundary, "quarter_boundary": quarter_boundary}


def _slice_ledger(ledger_path: Path, cycle_id: str) -> bytes:
    """Return CSV bytes: header + rows whose ``cycle_id`` column matches.

    If the ledger file is missing or has no rows, returns the header line
    from an empty in-memory scaffold so the bundle role is still populated.
    """
    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing trade ledger: {ledger_path}")
    text = ledger_path.read_text()
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError(f"Empty trade ledger at {ledger_path} (no header row)")
    header = rows[0]
    if "cycle_id" not in header:
        raise ValueError(
            f"Trade ledger at {ledger_path} missing required 'cycle_id' column"
        )
    cycle_idx = header.index("cycle_id")
    matching = [r for r in rows[1:] if len(r) > cycle_idx and r[cycle_idx] == cycle_id]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(matching)
    return buf.getvalue().encode("utf-8")


def _find_latest_report(reports_csv_dir: Path) -> Path:
    """Return newest ``grailzee_YYYY-MM-DD.csv``; ISO date in filename makes
    lexical-desc sort equal to chronological-desc."""
    if not reports_csv_dir.exists():
        raise FileNotFoundError(f"Missing reports_csv dir: {reports_csv_dir}")
    candidates = sorted(
        (p for p in reports_csv_dir.iterdir() if REPORT_CSV_PATTERN.match(p.name)),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No report CSVs matching grailzee_YYYY-MM-DD.csv in {reports_csv_dir}"
        )
    return candidates[0]


def _load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        raise FileNotFoundError(f"Missing analysis cache: {cache_path}")
    cache = json.loads(cache_path.read_text())
    if not isinstance(cache, dict) or not cache.get("cycle_id"):
        raise ValueError(f"Cache at {cache_path} missing required 'cycle_id' field")
    return cache


def _read_required(path: Path, label: str) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path.read_bytes()


def build_outbound_bundle(
    grailzee_root: Path,
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Build an OUTBOUND bundle. Return path to the created ``.zip``.

    Parameters
    ----------
    grailzee_root:
        Path to the GrailzeeData tree (parent of ``state/``, ``output/``,
        ``reports_csv/``, and ``bundles/``).
    output_dir:
        Override for the bundle output directory. Defaults to
        ``grailzee_root / "bundles"`` and is created if absent.
    now:
        Override for the bundle timestamp. Defaults to
        ``datetime.now(timezone.utc)``.
    """
    grailzee_root = Path(grailzee_root)
    state = grailzee_root / "state"
    briefs = grailzee_root / "output" / "briefs"
    reports_csv = grailzee_root / "reports_csv"
    bundles_dir = output_dir or (grailzee_root / "bundles")

    cache = _load_cache(state / "analysis_cache.json")
    cycle_id = cache["cycle_id"]

    payloads: list[tuple[str, str, bytes]] = []  # (role, arcname, data)

    payloads.append(
        (
            "analysis_cache",
            "analysis_cache.json",
            (state / "analysis_cache.json").read_bytes(),
        )
    )
    payloads.append(
        (
            "cycle_focus_current",
            "cycle_focus_current.json",
            _read_required(state / "cycle_focus.json", "cycle_focus"),
        )
    )
    payloads.append(
        (
            "monthly_goals",
            "monthly_goals.json",
            _read_required(state / "monthly_goals.json", "monthly_goals"),
        )
    )
    payloads.append(
        (
            "quarterly_allocation",
            "quarterly_allocation.json",
            _read_required(
                state / "quarterly_allocation.json", "quarterly_allocation"
            ),
        )
    )
    payloads.append(
        (
            "trade_ledger_snippet",
            "trade_ledger_snippet.csv",
            _slice_ledger(state / "trade_ledger.csv", cycle_id),
        )
    )
    brief_path = briefs / f"sourcing_brief_{cycle_id}.json"
    payloads.append(
        (
            "sourcing_brief",
            "sourcing_brief.json",
            _read_required(brief_path, f"sourcing_brief for {cycle_id}"),
        )
    )
    latest_report = _find_latest_report(reports_csv)
    payloads.append(
        (
            "latest_report_csv",
            f"latest_report/{latest_report.name}",
            latest_report.read_bytes(),
        )
    )

    scope = _detect_boundaries(cycle_id, state / "run_history.json")
    now_dt = now or datetime.now(timezone.utc)

    files_meta = [
        {
            "path": arcname,
            "role": role,
            "sha256": _sha256(data),
            "size_bytes": len(data),
        }
        for role, arcname, data in payloads
    ]

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "bundle_kind": BUNDLE_KIND,
        "generated_at": _iso_utc(now_dt),
        "cycle_id": cycle_id,
        "source": SOURCE_TAG,
        "scope": scope,
        "files": files_meta,
    }

    bundles_dir.mkdir(parents=True, exist_ok=True)
    bundle_name = (
        f"grailzee_outbound_{cycle_id}_{_filename_timestamp(now_dt)}.zip"
    )
    bundle_path = bundles_dir / bundle_name

    tmp_path = bundle_path.parent / (bundle_path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for _role, arcname, data in payloads:
                zf.writestr(arcname, data)
        tmp_path.replace(bundle_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return bundle_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an OUTBOUND Grailzee strategy-session bundle."
    )
    parser.add_argument(
        "--grailzee-root",
        required=True,
        help="Path to the GrailzeeData tree (parent of state/, output/, reports_csv/).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override the bundle output directory (default: <root>/bundles).",
    )
    args = parser.parse_args(argv)
    try:
        path = build_outbound_bundle(
            Path(args.grailzee_root),
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Bundle build failed: {exc}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
