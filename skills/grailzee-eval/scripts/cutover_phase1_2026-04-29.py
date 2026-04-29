"""
Phase 1 cutover — regenerate production trade_ledger.csv from WatchTrack.

One-time script (design v1 §2 cutover posture amendment). Archives the
existing production ledger, primes an empty starting state, invokes the
Phase 1 orchestrator, and verifies the output. Safe to inspect before
running; halts on any verification failure without touching the live ledger
beyond what it has already done.

Usage:
    cd skills/grailzee-eval
    export GRAILZEE_ROOT="<path to GrailzeeData>"
    python3.12 scripts/cutover_phase1_2026-04-29.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

# Ensure the package root is importable when run as a script.
_pkg_root = Path(__file__).resolve().parents[1]
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from scripts.ingest_sales import (  # noqa: E402
    _get_data_root,
    ingest_sales,
    read_ledger_csv,
)

BAK_SUFFIX = ".pre-redo-2026-04-29.bak"
REPO_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "state_seeds"
    / "gate3_fixtures"
    / "watchtrack_full_final.jsonl"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def halt(msg: str) -> None:
    print(f"\nHALT: {msg}", file=sys.stderr)
    print("Recovery: restore from the .bak file if the ledger was already removed.",
          file=sys.stderr)
    sys.exit(1)


def main() -> None:
    # ── 1. Resolve production paths ──────────────────────────────────────
    try:
        data_root = _get_data_root()
    except EnvironmentError as exc:
        halt(str(exc))

    ledger_path = data_root / "state" / "trade_ledger.csv"
    sales_data_dir = data_root / "sales_data"
    archive_dir = sales_data_dir / "archive"
    lock_path = Path.home() / ".grailzee" / "trade_ledger.lock"

    print(f"GRAILZEE_ROOT : {data_root}")
    print(f"Ledger        : {ledger_path}")
    print(f"Sales data    : {sales_data_dir}")

    # ── 2. Archive existing production ledger ────────────────────────────
    bak_path = ledger_path.with_suffix(ledger_path.suffix + BAK_SUFFIX)
    if bak_path.exists():
        print(f"\n.bak already exists at {bak_path}")
        print("Skipping backup (migration already ran once on this machine).")
        pre_rows = None
    elif not ledger_path.exists():
        print("\nNo existing ledger found; skipping backup.")
        pre_rows = None
    else:
        pre_rows_raw = ledger_path.read_text(encoding="utf-8").splitlines()
        pre_rows = len(pre_rows_raw) - 1  # subtract header
        shutil.copy2(ledger_path, bak_path)
        print(f"\nArchived: {ledger_path.name} → {bak_path.name}")
        print(f"  Pre-cutover rows: {pre_rows}")
        print(f"  .bak size       : {bak_path.stat().st_size} bytes")
        print(f"  .bak sha256     : {_sha256(bak_path)[:16]}...")

    # ── 3. Stage fixture ─────────────────────────────────────────────────
    fixture_dest = sales_data_dir / "watchtrack_full_final.jsonl"
    archived_fixture = archive_dir / "watchtrack_full_final.jsonl"

    if fixture_dest.exists():
        print(f"\nFixture already at sales_data/ ({fixture_dest.stat().st_size} bytes).")
    elif archived_fixture.exists():
        print(f"\nFixture found in archive/; copying back to sales_data/.")
        shutil.copy2(archived_fixture, fixture_dest)
        print(f"  Staged: {fixture_dest.stat().st_size} bytes.")
    elif REPO_FIXTURE.exists():
        print(f"\nFixture not in production paths; using repo copy as fallback.")
        shutil.copy2(REPO_FIXTURE, fixture_dest)
        print(f"  Staged from repo: {fixture_dest.stat().st_size} bytes.")
    else:
        halt(
            "watchtrack_full_final.jsonl not found in sales_data/, archive/, "
            "or repo state_seeds/. Cannot proceed."
        )

    fixture_sha = _sha256(fixture_dest)
    print(f"  Fixture sha256: {fixture_sha[:16]}...")

    # ── 4. Prime empty starting state ────────────────────────────────────
    if ledger_path.exists():
        ledger_path.unlink()
        print(f"\nRemoved existing ledger to prime empty starting state.")
    else:
        print(f"\nLedger absent; starting state is already empty.")

    # ── 5. Invoke pipeline ───────────────────────────────────────────────
    print("\nInvoking ingest_sales()...")
    manifest = ingest_sales(
        sales_data_dir=sales_data_dir,
        archive_dir=archive_dir,
        ledger_path=ledger_path,
        lock_path=lock_path,
    )

    skipped_json = json.dumps(manifest.rows_skipped, indent=2)
    print(f"\n── Manifest ──────────────────────────────────")
    print(f"  files_found      : {manifest.files_found}")
    print(f"  files_processed  : {manifest.files_processed}")
    print(f"  rows_added       : {manifest.rows_added}")
    print(f"  rows_updated     : {manifest.rows_updated}")
    print(f"  rows_unchanged   : {manifest.rows_unchanged}")
    print(f"  rows_unmatched   : {manifest.rows_unmatched}")
    print(f"  rows_pruned      : {manifest.rows_pruned}")
    print(f"  rows_skipped     : {skipped_json}")

    # ── 6. Verify post-run state ─────────────────────────────────────────
    print(f"\n── Verification ──────────────────────────────")

    if not ledger_path.exists():
        halt("trade_ledger.csv does not exist after pipeline run.")

    rows = read_ledger_csv(ledger_path)
    row_count = len(rows)
    accounts: dict[str, int] = {}
    for r in rows:
        accounts[r.account] = accounts.get(r.account, 0) + 1

    print(f"  Ledger rows     : {row_count} (expected 16)")
    print(f"  Account dist    : {accounts} (expected NR=11 RES=5)")
    unknown_rows = [r for r in rows if r.account not in ("NR", "RES")]
    print(f"  UNKNOWN rows    : {len(unknown_rows)} (expected 0)")

    errors: list[str] = []

    if manifest.files_processed != 1:
        errors.append(f"files_processed={manifest.files_processed}, expected 1")
    if manifest.rows_added != 19:
        errors.append(f"rows_added={manifest.rows_added}, expected 19")
    if manifest.rows_pruned != 3:
        errors.append(f"rows_pruned={manifest.rows_pruned}, expected 3")
    if len(manifest.rows_skipped) != 2:
        errors.append(f"rows_skipped count={len(manifest.rows_skipped)}, expected 2")
    else:
        skipped_tids = {s["transaction_id"] for s in manifest.rows_skipped}
        expected_skipped = {"TEY1104", "TEY1092"}
        if skipped_tids != expected_skipped:
            errors.append(f"rows_skipped={skipped_tids}, expected {expected_skipped}")
    if row_count != 16:
        errors.append(f"post-prune row count={row_count}, expected 16")
    if accounts.get("NR", 0) != 11:
        errors.append(f"NR count={accounts.get('NR', 0)}, expected 11")
    if accounts.get("RES", 0) != 5:
        errors.append(f"RES count={accounts.get('RES', 0)}, expected 5")
    if unknown_rows:
        errors.append(f"found {len(unknown_rows)} UNKNOWN-account rows")

    if errors:
        print("\n  VERIFICATION FAILURES:")
        for e in errors:
            print(f"    - {e}")
        halt("Post-run verification failed. See .bak for recovery.")

    print("  All checks passed ✓")

    # ── 7. Idempotency check ─────────────────────────────────────────────
    print("\n── Idempotency check ─────────────────────────")
    ledger_bytes_before = ledger_path.read_bytes()

    manifest2 = ingest_sales(
        sales_data_dir=sales_data_dir,
        archive_dir=archive_dir,
        ledger_path=ledger_path,
        lock_path=lock_path,
    )
    print(f"  Second run files_found : {manifest2.files_found} (expected 0)")
    print(f"  Ledger unchanged       : {ledger_path.read_bytes() == ledger_bytes_before}")

    if manifest2.files_found != 0:
        halt(f"Second run found files_found={manifest2.files_found}; fixture not archived.")
    if ledger_path.read_bytes() != ledger_bytes_before:
        halt("Ledger bytes changed on second run; idempotency broken.")

    print("  Idempotency confirmed ✓")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n── Cutover complete ──────────────────────────")
    if pre_rows is not None:
        print(f"  Pre-cutover rows  : {pre_rows} (archived to {bak_path.name})")
    print(f"  Post-cutover rows : {row_count}")
    print(f"  NR={accounts.get('NR', 0)}  RES={accounts.get('RES', 0)}  UNKNOWN={len(unknown_rows)}")
    print(f"  Fixture sha256    : {fixture_sha[:16]}...")
    if bak_path.exists():
        print(f"  .bak              : {bak_path} ({bak_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
