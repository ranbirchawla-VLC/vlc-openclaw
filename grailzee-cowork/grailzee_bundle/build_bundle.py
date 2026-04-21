"""OUTBOUND bundle builder.

Packages the current GrailzeeData state into a single ``.zip`` for upload to
a Chat strategy session. The bundle is written to
``<grailzee_root>/bundles/grailzee_outbound_<cycle_id>_<YYYYMMDD_HHMMSS_ffffff>.zip``.

Microsecond precision in the timestamp matches the write_cache backup
rotation convention (two bundles generated in the same second get distinct
filenames).

Roles included
--------------
=======================  ========  ==========  ==========================================
role                     required  source      notes
=======================  ========  ==========  ==========================================
analysis_cache           yes       Drive       state/analysis_cache.json
cycle_focus              yes       Drive       state/cycle_focus.json
monthly_goals            yes       Drive       state/monthly_goals.json
quarterly_allocation     yes       Drive       state/quarterly_allocation.json
trade_ledger             yes       Drive       state/trade_ledger.csv (FULL)
sourcing_brief           yes       Drive       output/briefs/sourcing_brief_<cycle>.json
latest_report_csv        yes       Drive       reports_csv/grailzee_YYYY-MM-DD.csv
analyzer_config          yes       workspace   state/analyzer_config.json (A.5)
brand_floors             yes       workspace   state/brand_floors.json (A.5)
sourcing_rules           yes       workspace   state/sourcing_rules.json (A.5)
previous_cycle_outcome   no        Drive       only when a prior cycle had trade data
previous_cycle_outcome_  yes       Drive       meta always bundled (A.7)
  meta
=======================  ========  ==========  ==========================================

Phase A.5 migration
-------------------
Role ``cycle_focus_current`` renamed to ``cycle_focus`` with archive name
``cycle_focus.json`` (previously ``cycle_focus_current.json``). The bundle
also writes a transitional alias archive entry at the legacy archive name
``cycle_focus_current.json`` carrying identical bytes; it is NOT a manifest
role. Strategy-side consumers reading the legacy name keep working for one
task cycle while strategy-skill docs migrate. Follow-up task removes the
alias.

Three workspace-state configs (analyzer_config, brand_floors, sourcing_rules)
join the bundle. They live under the repo-backed ``WORKSPACE_STATE_PATH``;
``workspace_state_dir`` defaults to auto-discovery via the cross-skill sys.path
pattern already used for grailzee-eval imports. Pass ``--workspace-state-dir``
to override.

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
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Cross-skill import (single source of truth for cycle math) ─────
# grailzee-eval owns prev_cycle and cycle_outcome_path. Duplicating them
# here would reintroduce the dual-source problem Phase A.5 just killed,
# so we add grailzee-eval/scripts to sys.path instead. Layout-fragile
# but explicit.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_GRAILZEE_EVAL = _WORKSPACE_ROOT / "skills" / "grailzee-eval"
if _GRAILZEE_EVAL.exists() and str(_GRAILZEE_EVAL) not in sys.path:
    sys.path.insert(0, str(_GRAILZEE_EVAL))
from scripts.grailzee_common import (  # noqa: E402
    prev_cycle,
)

MANIFEST_VERSION = 1
SOURCE_TAG = "grailzee-cowork/build_bundle"
BUNDLE_KIND = "outbound"
REPORT_CSV_PATTERN = re.compile(r"^grailzee_\d{4}-\d{2}-\d{2}\.csv$")
CYCLE_ID_PATTERN = re.compile(r"^cycle_(\d{4})-(\d{2})$")

# Phase A.7: how far back to look for a cycle outcome with real trades.
# 26 biweekly cycles ≈ 52 weeks. Bailout prevents infinite walk when the
# ledger is empty / brand-new deployments.
MAX_PREVIOUS_CYCLE_LOOKBACK = 26

PREVIOUS_OUTCOME_ARCNAME = "cycle_outcome_previous.json"
PREVIOUS_OUTCOME_META_ARCNAME = "cycle_outcome_previous.meta.json"

# Phase A.5 transitional alias: legacy archive name for cycle_focus.json.
# Same bytes as the canonical ``cycle_focus.json`` entry; not a manifest
# role. Strategy-side docs still reference ``cycle_focus_current.json``
# as of A.5; this alias keeps the legacy name resolvable for one cycle
# while the rename propagates. Follow-up task drops the alias.
CYCLE_FOCUS_LEGACY_ARCNAME = "cycle_focus_current.json"

# Phase A.5: workspace-state configs bundled alongside Drive-backed files.
# Sources live under the grailzee-eval repo's ``state/`` directory,
# discovered via the cross-skill sys.path pattern used for grailzee_common
# imports. Each tuple is (role_name, archive_name, source_filename).
WORKSPACE_CONFIG_FILES = (
    ("analyzer_config", "analyzer_config.json", "analyzer_config.json"),
    ("brand_floors", "brand_floors.json", "brand_floors.json"),
    ("sourcing_rules", "sourcing_rules.json", "sourcing_rules.json"),
)

# Default workspace_state_dir: ``<workspace_root>/state``, same root the
# grailzee-eval sys.path prefix above is anchored on.
DEFAULT_WORKSPACE_STATE_DIR = _WORKSPACE_ROOT / "state"


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


def _read_full_ledger(ledger_path: Path) -> bytes:
    """Return the full ledger CSV as bytes. No filtering, no trimming.

    Per Section 11 of the implementation plan, the strategist reads ALL
    state before opening a session. Cycle-scoped slicing (Phase 24a's
    initial behaviour) hid historical context; the strategist
    cross-references current-cycle signal against the full close
    history. Header-only ledgers (no trades yet) pass through verbatim.
    """
    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing trade ledger: {ledger_path}")
    return ledger_path.read_bytes()


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


def resolve_previous_cycle_outcome(
    state_dir: Path,
    target_cycle_id: str,
    max_lookback: int = MAX_PREVIOUS_CYCLE_LOOKBACK,
) -> tuple[Path | None, dict[str, Any]]:
    """Find the most recent cycle outcome file with real trade data.

    Walks ``prev_cycle()`` starting from ``target_cycle_id`` until it
    hits a ``state/cycle_outcome_<id>.json`` whose ``trades`` array is
    non-empty, or until ``max_lookback`` cycles have been examined.

    A cycle outcome file that exists but has an empty ``trades`` array
    counts as a "skipped" cycle; missing files are simply absent from
    the history. The distinction is what the strategist uses to say
    "your most recent completed cycle was empty — here's the last one
    with data."

    Returns ``(path_or_None, manifest_dict)`` where manifest_dict is the
    JSON payload for ``cycle_outcome_previous.meta.json``. On no-match
    bailout, path is None and manifest has ``source_cycle_id: None``.
    """
    skipped: list[str] = []
    candidate = prev_cycle(target_cycle_id)
    for _ in range(max_lookback):
        path = state_dir / f"cycle_outcome_{candidate}.json"
        if path.exists():
            trades: list[Any] = []
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                data = None
            if isinstance(data, dict):
                raw_trades = data.get("trades", [])
                if isinstance(raw_trades, list):
                    trades = raw_trades
            if trades:
                resolution_note = (
                    f"{candidate} is the most recent cycle with real "
                    f"trade data before {target_cycle_id}"
                )
                if skipped:
                    resolution_note += (
                        f"; skipped {len(skipped)} empty cycle"
                        f"{'s' if len(skipped) != 1 else ''} "
                        f"({', '.join(skipped)})"
                    )
                return path, {
                    "source_cycle_id": candidate,
                    "target_planning_cycle_id": target_cycle_id,
                    "skipped_cycles": skipped,
                    "resolution_note": resolution_note,
                }
            # File existed but had no trades — explicit skip
            skipped.append(candidate)
        candidate = prev_cycle(candidate)

    return None, {
        "source_cycle_id": None,
        "target_planning_cycle_id": target_cycle_id,
        "skipped_cycles": skipped,
        "resolution_note": (
            f"No cycle outcome with trade data found within "
            f"{max_lookback} cycles before {target_cycle_id}"
        ),
    }


def build_outbound_bundle(
    grailzee_root: Path,
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
    workspace_state_dir: Path | None = None,
) -> Path:
    """Build an OUTBOUND bundle. Return path to the created ``.zip``.

    Parameters
    ----------
    grailzee_root:
        Path to the GrailzeeData tree (parent of ``state/``, ``output/``,
        ``reports_csv/``, and ``bundles/``). Drive-backed in production.
    output_dir:
        Override for the bundle output directory. Defaults to
        ``grailzee_root / "bundles"`` and is created if absent.
    now:
        Override for the bundle timestamp. Defaults to
        ``datetime.now(timezone.utc)``.
    workspace_state_dir:
        Phase A.5: directory holding the repo-backed config files
        (analyzer_config.json, brand_floors.json, sourcing_rules.json).
        Defaults to ``DEFAULT_WORKSPACE_STATE_DIR``, auto-discovered via
        the same cross-skill root already in use for grailzee-eval
        imports. Tests pass a tmp path here.
    """
    grailzee_root = Path(grailzee_root)
    state = grailzee_root / "state"
    briefs = grailzee_root / "output" / "briefs"
    reports_csv = grailzee_root / "reports_csv"
    bundles_dir = output_dir or (grailzee_root / "bundles")
    workspace_state = (
        Path(workspace_state_dir)
        if workspace_state_dir is not None
        else DEFAULT_WORKSPACE_STATE_DIR
    )

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
    # Phase A.5: role renamed cycle_focus_current -> cycle_focus; archive
    # name follows. Legacy archive name `cycle_focus_current.json` is
    # still emitted below as a non-role alias for one cycle.
    cycle_focus_bytes = _read_required(state / "cycle_focus.json", "cycle_focus")
    payloads.append(("cycle_focus", "cycle_focus.json", cycle_focus_bytes))
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
    # Phase A.5: workspace-state configs. Fail loud with a descriptive
    # label if any is absent; strategy sessions assume all three are
    # present.
    for role, arcname, source_name in WORKSPACE_CONFIG_FILES:
        payloads.append(
            (
                role,
                arcname,
                _read_required(workspace_state / source_name, role),
            )
        )
    payloads.append(
        (
            "trade_ledger",
            "trade_ledger.csv",
            _read_full_ledger(state / "trade_ledger.csv"),
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

    # Phase A.7: previous cycle outcome. Resolve the most recent cycle
    # with real trade data; always bundle the meta (even when resolution
    # returns null) so the strategist has a single consistent signal.
    prev_outcome_path, prev_outcome_meta = resolve_previous_cycle_outcome(
        state, cycle_id
    )
    if prev_outcome_path is not None:
        payloads.append(
            (
                "previous_cycle_outcome",
                PREVIOUS_OUTCOME_ARCNAME,
                prev_outcome_path.read_bytes(),
            )
        )
    payloads.append(
        (
            "previous_cycle_outcome_meta",
            PREVIOUS_OUTCOME_META_ARCNAME,
            (json.dumps(prev_outcome_meta, indent=2) + "\n").encode("utf-8"),
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
            # Phase A.5 transitional alias: legacy `cycle_focus_current.json`
            # archive entry carries the same bytes as the canonical
            # `cycle_focus.json`. No manifest role; strategy-side consumers
            # reading the legacy archive name keep working during the
            # rename migration.
            zf.writestr(CYCLE_FOCUS_LEGACY_ARCNAME, cycle_focus_bytes)
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
    parser.add_argument(
        "--workspace-state-dir",
        default=None,
        help=(
            "Phase A.5: override the workspace state directory holding "
            "analyzer_config.json, brand_floors.json, sourcing_rules.json. "
            "Defaults to <workspace_root>/state via cross-skill discovery."
        ),
    )
    args = parser.parse_args(argv)
    try:
        path = build_outbound_bundle(
            Path(args.grailzee_root),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            workspace_state_dir=(
                Path(args.workspace_state_dir)
                if args.workspace_state_dir
                else None
            ),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Bundle build failed: {exc}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
