"""Phase A.6 one-shot migration: rewrite trade_ledger.csv in v2 shape.

Reads the current ledger (v1 schema: ``date_closed, cycle_id, brand,
reference, account, buy_price, sell_price``) and writes the v2 schema
(``buy_date, sell_date, buy_cycle_id, sell_cycle_id, brand, reference,
account, buy_price, sell_price``). Legacy rows lack buy information,
so per schema v1 §4 S6 the output leaves ``buy_date`` and
``buy_cycle_id`` blank. ``sell_date`` is the old ``date_closed``;
``sell_cycle_id`` is re-derived from ``sell_date`` via
``cycle_id_from_date`` and sanity-checked against the legacy
``cycle_id`` column (they should match exactly).

Before rewriting the live file, the script copies the current contents
to ``<ledger_path>.v1_backup``. Rollback is a simple
``mv <path>.v1_backup <path>`` after restoring consumers. The backup
is never deleted by this script.

Idempotence: a file that is already v2 shape (header contains
``sell_date``) is left alone with a notice. The migration is a one-way
schema change; running it twice in a row on a v2 file is a no-op.

Usage:
    migrate_ledger_v2.py                     # migrate state/trade_ledger.csv
    migrate_ledger_v2.py --ledger PATH       # custom target
    migrate_ledger_v2.py --dry-run           # validate + preview, no writes
    migrate_ledger_v2.py --force             # rewrite even if a .v1_backup exists

Exit codes:
    0  migrated (or dry-run preview ok, or already-v2 no-op)
    1  validation error (file malformed, cycle mismatch, etc.)
    2  filesystem error during atomic write
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    LEDGER_COLUMNS,
    LEDGER_PATH,
    cycle_id_from_date,
    get_tracer,
)

tracer = get_tracer(__name__)

V1_REQUIRED_COLUMNS = ("date_closed", "cycle_id", "brand", "reference",
                       "account", "buy_price", "sell_price")
BACKUP_SUFFIX = ".v1_backup"


def _looks_like_v2(header: list[str]) -> bool:
    return "sell_date" in header and "date_closed" not in header


def _parse_iso_date(raw: str) -> date:
    y, m, d = raw.split("-")
    return date(int(y), int(m), int(d))


def _atomic_write_rows(path: str, header: list[str], rows: list[list[str]]) -> None:
    tmp = path + ".tmp"
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _migrate_row(raw: dict, line_num: int) -> tuple[list[str], list[str]]:
    """Return (new_row_values, warnings_or_errors) for one v1 row.

    Warnings/errors are strings; an empty list means the row migrated
    cleanly. A descriptive error disables the row from the output (caller
    aborts unless --force is added later).
    """
    errors: list[str] = []
    sell_date_raw = (raw.get("date_closed") or "").strip()
    try:
        sell_date = _parse_iso_date(sell_date_raw)
    except ValueError:
        errors.append(
            f"line {line_num}: invalid date_closed '{sell_date_raw}'"
        )
        return [], errors

    derived_cycle = cycle_id_from_date(sell_date)
    legacy_cycle = (raw.get("cycle_id") or "").strip()
    if legacy_cycle and legacy_cycle != derived_cycle:
        errors.append(
            f"line {line_num}: legacy cycle_id '{legacy_cycle}' disagrees "
            f"with cycle_id_from_date({sell_date_raw}) = '{derived_cycle}'. "
            f"Fix the input before re-running."
        )
        return [], errors

    return [
        "",                                 # buy_date (blank per S6)
        sell_date.isoformat(),              # sell_date (was date_closed)
        "",                                 # buy_cycle_id (blank per S6)
        derived_cycle,                      # sell_cycle_id (derived)
        raw.get("brand", "").strip(),
        raw.get("reference", "").strip(),
        raw.get("account", "").strip(),
        (raw.get("buy_price") or "").strip(),
        (raw.get("sell_price") or "").strip(),
    ], errors


def migrate(ledger_path: str, *, dry_run: bool, force: bool) -> int:
    """Run the one-shot v1 -> v2 migration. Returns exit code."""
    with tracer.start_as_current_span("migrate_ledger_v2") as span:
        span.set_attribute("ledger_path", ledger_path)
        span.set_attribute("dry_run", dry_run)
        span.set_attribute("force", force)

        if not os.path.exists(ledger_path):
            print(f"Ledger not found at {ledger_path}. Nothing to migrate.",
                  file=sys.stderr)
            span.set_attribute("outcome", "missing")
            return 1

        with open(ledger_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            raw_rows = list(reader)

        if _looks_like_v2(header):
            print(
                f"{ledger_path} already in v2 shape (has 'sell_date'). "
                f"No migration needed.",
                file=sys.stderr,
            )
            span.set_attribute("outcome", "already_v2")
            return 0

        missing = [c for c in V1_REQUIRED_COLUMNS if c not in header]
        if missing:
            print(
                f"{ledger_path} header missing expected v1 columns {missing}. "
                f"Got: {header}. Aborting.",
                file=sys.stderr,
            )
            span.set_attribute("outcome", "bad_header")
            return 1

        span.set_attribute("rows_in", len(raw_rows))

        new_rows: list[list[str]] = []
        errors: list[str] = []
        for i, raw in enumerate(raw_rows, start=2):
            new_row, row_errs = _migrate_row(raw, i)
            if row_errs:
                errors.extend(row_errs)
                continue
            new_rows.append(new_row)

        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            span.set_attribute("outcome", "validation_error")
            return 1

        blank_buy = sum(1 for r in new_rows if r[0] == "")
        span.set_attribute("rows_migrated", len(new_rows))
        span.set_attribute("rows_with_blank_buy_date", blank_buy)

        print(json.dumps({
            "ledger_path": ledger_path,
            "rows_in": len(raw_rows),
            "rows_migrated": len(new_rows),
            "rows_with_blank_buy_date": blank_buy,
            "backup_path": ledger_path + BACKUP_SUFFIX,
            "dry_run": dry_run,
        }, indent=2))

        if dry_run:
            print("\n── dry-run preview (no disk writes) ──")
            print(",".join(LEDGER_COLUMNS))
            for r in new_rows:
                print(",".join(r))
            span.set_attribute("outcome", "dry_run")
            return 0

        backup_path = ledger_path + BACKUP_SUFFIX
        if os.path.exists(backup_path) and not force:
            print(
                f"Backup already exists at {backup_path}. Refusing to "
                f"overwrite. Pass --force to proceed.",
                file=sys.stderr,
            )
            span.set_attribute("outcome", "backup_exists")
            return 1

        try:
            shutil.copy2(ledger_path, backup_path)
        except OSError as exc:
            print(f"Failed to write backup {backup_path}: {exc}", file=sys.stderr)
            span.set_attribute("outcome", "backup_failed")
            return 2
        span.set_attribute("backup_path", backup_path)

        try:
            _atomic_write_rows(ledger_path, LEDGER_COLUMNS, new_rows)
        except OSError as exc:
            print(f"Failed to write migrated ledger {ledger_path}: {exc}",
                  file=sys.stderr)
            span.set_attribute("outcome", "io_error")
            return 2

        print(
            f"Migrated {len(new_rows)} row(s). Backup at {backup_path}.",
            file=sys.stderr,
        )
        span.set_attribute("outcome", "migrated")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger", default=None,
        help="Target ledger CSV. Defaults to LEDGER_PATH on Drive.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate + preview the migrated rows without writing.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if <path>.v1_backup already exists.",
    )
    args = parser.parse_args()

    ledger = args.ledger or LEDGER_PATH
    return migrate(ledger, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
