"""Backfill historical trades into the Grailzee trade ledger.

Reads a hand-curated CSV of historical trades, validates each row,
derives cycle_id from date_closed, and appends to trade_ledger.csv.

Usage:
    backfill_ledger.py <input.csv> [--dry-run] [--force] [--no-roll]
                       [--ledger PATH] [--name-cache PATH]

Exit codes:
    0  success, or dry-run completed with no validation errors
    1  validation error (ledger untouched)
    2  I/O error during write (ledger untouched)
    3  dependency / primitive error (see Section 12.3)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

import scripts.grailzee_common as gc  # noqa: E402


REQUIRED_ATTRS: list[str] = [
    "LEDGER_PATH",
    "ACCOUNT_FEES",
    "cycle_id_from_date",
    "normalize_ref",
    "NAME_CACHE_PATH",
]

INPUT_COLUMNS: list[str] = [
    "date_closed", "brand", "reference", "account",
    "buy_price", "sell_price", "notes",
]

OUTPUT_COLUMNS: list[str] = [
    "date_closed", "cycle_id", "brand", "reference",
    "account", "buy_price", "sell_price",
]

VALID_ACCOUNTS: set[str] = {"NR", "RES"}

SECTION_12_3_HINT = (
    "See Grailzee_Eval_v2_Implementation.md Section 12.3 for required "
    "grailzee_common primitives."
)


# ─── Dependency check ─────────────────────────────────────────────────


def check_dependencies() -> int:
    """Return 0 if all REQUIRED_ATTRS present on grailzee_common, else 3.

    Prints a pointer to Section 12.3 on failure. Reads attrs via hasattr
    so tests can monkeypatch-delete an attr and re-invoke main().
    """
    missing = [a for a in REQUIRED_ATTRS if not hasattr(gc, a)]
    if missing:
        print(
            f"ERROR: grailzee_common missing required attrs: {missing}",
            file=sys.stderr,
        )
        print(SECTION_12_3_HINT, file=sys.stderr)
        return 3
    return 0


# ─── Input parsing ────────────────────────────────────────────────────


def parse_date(raw: str) -> Optional[date]:
    """Accept YYYY-MM-DD, M/D/YY, or M/D/YYYY. Return None on parse failure."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_price(raw: str) -> Optional[float]:
    """Parse positive price. Reject $, comma, or any whitespace."""
    if raw is None:
        return None
    if raw != raw.strip():
        return None
    if "$" in raw or "," in raw:
        return None
    if re.search(r"\s", raw):
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    if v <= 0:
        return None
    return v


def read_input(path: str) -> tuple[list[dict], list[str]]:
    """Read input CSV with BOM strip and header/value whitespace trim.

    Returns (rows, file_errors). Each row dict includes '_line_num' (the
    CSV line number, 2-indexed for data rows). On file-level errors (not
    found, missing columns, empty file) rows is empty and file_errors
    contains the reason.
    """
    errors: list[str] = []
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            try:
                raw_header = next(reader)
            except StopIteration:
                errors.append(f"Input file is empty: {path}")
                return rows, errors
            header = [h.strip() for h in raw_header]
            missing_cols = [c for c in INPUT_COLUMNS if c not in header]
            if missing_cols:
                errors.append(
                    f"Missing required columns: {missing_cols}. "
                    f"Expected: {INPUT_COLUMNS}. Got: {header}"
                )
                return rows, errors
            for line_num, raw in enumerate(reader, start=2):
                if not raw or all(
                    (c is None or c.strip() == "") for c in raw
                ):
                    continue
                if len(raw) != len(header):
                    errors.append(
                        f"line {line_num}: column count mismatch "
                        f"(expected {len(header)}, got {len(raw)})"
                    )
                    continue
                row = {h: (v or "").strip() for h, v in zip(header, raw)}
                row["_line_num"] = line_num
                rows.append(row)
    except FileNotFoundError:
        errors.append(f"Input file not found: {path}")
    except OSError as e:
        errors.append(f"Cannot read input file {path}: {e}")
    return rows, errors


# ─── Validation ───────────────────────────────────────────────────────


def validate_row(row: dict, today: date) -> tuple[Optional[dict], list[str]]:
    """Validate one raw row. Return (normalized_dict_or_None, errors)."""
    errors: list[str] = []
    ln = row.get("_line_num", "?")

    date_raw = row.get("date_closed", "")
    dt = parse_date(date_raw)
    if dt is None:
        errors.append(
            f"line {ln}: invalid date_closed '{date_raw}' "
            f"(expected YYYY-MM-DD, M/D/YY, or M/D/YYYY)"
        )
    elif dt > today:
        errors.append(
            f"line {ln}: date_closed {dt.isoformat()} is in the future"
        )
        dt = None

    brand = row.get("brand", "")
    if not brand:
        errors.append(f"line {ln}: brand is empty")

    reference = row.get("reference", "")
    if not reference:
        errors.append(f"line {ln}: reference is empty")
    elif re.search(r"\s", reference):
        errors.append(
            f"line {ln}: reference '{reference}' contains internal whitespace"
        )

    account = row.get("account", "")
    if account not in VALID_ACCOUNTS:
        errors.append(
            f"line {ln}: invalid account '{account}' "
            f"(must be exactly 'NR' or 'RES')"
        )

    buy_raw = row.get("buy_price", "")
    buy = parse_price(buy_raw)
    if buy is None:
        errors.append(
            f"line {ln}: buy_price '{buy_raw}' invalid "
            f"(positive number, no $/comma/whitespace)"
        )

    sell_raw = row.get("sell_price", "")
    sell = parse_price(sell_raw)
    if sell is None:
        errors.append(
            f"line {ln}: sell_price '{sell_raw}' invalid "
            f"(positive number, no $/comma/whitespace)"
        )

    if errors or dt is None or buy is None or sell is None:
        return None, errors
    return {
        "_line_num": ln,
        "_date_obj": dt,
        "date_closed": dt.isoformat(),
        "brand": brand,
        "reference": reference,
        "account": account,
        "buy_price": buy,
        "sell_price": sell,
    }, errors


def validate_all(
    rows: list[dict], today: date, force: bool
) -> tuple[list[dict], list[str]]:
    """Validate every row. Return (valid_rows, errors).

    force=True skips rows with errors but keeps the good ones.
    force=False returns all errors; caller aborts the run.
    """
    valid: list[dict] = []
    all_errors: list[str] = []
    for row in rows:
        norm, errs = validate_row(row, today)
        if norm:
            valid.append(norm)
        all_errors.extend(errs)
    if force:
        return valid, all_errors
    return valid, all_errors


# ─── Brand-mismatch warnings ──────────────────────────────────────────


def load_name_cache(path: str) -> dict:
    """Load name_cache.json. Returns {} if missing or malformed."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Handle both flat {ref: {...}} and wrapped {"references": {ref: {...}}}
    if "references" in data and isinstance(data["references"], dict):
        return data["references"]
    return data


def brand_mismatch_warnings(
    valid_rows: list[dict], name_cache: dict
) -> list[str]:
    """Return one WARNING string per row whose brand disagrees with cache."""
    warnings: list[str] = []
    if not name_cache:
        return warnings

    lookup: dict[str, dict] = {}
    for key, entry in name_cache.items():
        if not isinstance(entry, dict):
            continue
        lookup[gc.normalize_ref(key)] = entry
        for alt in entry.get("alt_refs", []) or []:
            lookup[gc.normalize_ref(alt)] = entry

    for r in valid_rows:
        entry = lookup.get(gc.normalize_ref(r["reference"]))
        if not entry:
            continue
        cached_brand = str(entry.get("brand", "")).strip()
        if not cached_brand:
            continue
        if cached_brand.lower() != r["brand"].lower():
            warnings.append(
                f"WARNING line {r['_line_num']}: reference {r['reference']} "
                f"brand mismatch — input '{r['brand']}', "
                f"name_cache '{cached_brand}'"
            )
    return warnings


# ─── Cycle-id derivation ──────────────────────────────────────────────


def derive_cycle_ids(
    valid_rows: list[dict],
) -> tuple[list[dict], Optional[str]]:
    """Inject cycle_id on every valid row. Return (rows, error_msg_or_None).

    If cycle_id_from_date raises or produces an empty string, abort with a
    descriptive error. Callers should exit 3 in that case.
    """
    fn = gc.cycle_id_from_date
    out: list[dict] = []
    for r in valid_rows:
        try:
            cid = fn(r["_date_obj"])
        except Exception as e:
            return out, (
                f"cycle_id_from_date failed on line {r['_line_num']} "
                f"(date {r['date_closed']}): {e}"
            )
        if not cid:
            return out, (
                f"cycle_id_from_date returned empty on line {r['_line_num']} "
                f"(date {r['date_closed']})"
            )
        r2 = dict(r)
        r2["cycle_id"] = cid
        out.append(r2)
    return out, None


# ─── Dedup ────────────────────────────────────────────────────────────


def load_existing_ledger_keys(ledger_path: str) -> set[tuple]:
    """Return set of dedup keys from existing ledger file.

    Key: (iso_date, normalized_ref, account, buy_price, sell_price).
    """
    keys: set[tuple] = set()
    if not os.path.exists(ledger_path):
        return keys
    try:
        with open(ledger_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    buy = float(row.get("buy_price", "") or 0)
                    sell = float(row.get("sell_price", "") or 0)
                except (ValueError, TypeError):
                    continue
                keys.add((
                    (row.get("date_closed", "") or "").strip(),
                    gc.normalize_ref(row.get("reference", "") or ""),
                    (row.get("account", "") or "").strip(),
                    buy,
                    sell,
                ))
    except OSError:
        return keys
    return keys


def filter_duplicates(
    valid_rows: list[dict], existing_keys: set[tuple]
) -> tuple[list[dict], list[str]]:
    """Split rows into (kept, dup_messages). In-batch dupes also caught."""
    seen = set(existing_keys)
    kept: list[dict] = []
    dupes: list[str] = []
    for r in valid_rows:
        key = (
            r["date_closed"],
            gc.normalize_ref(r["reference"]),
            r["account"],
            r["buy_price"],
            r["sell_price"],
        )
        if key in seen:
            dupes.append(
                f"line {r['_line_num']}: duplicate of existing ledger row "
                f"({r['date_closed']} {r['reference']} {r['account']} "
                f"buy={r['buy_price']} sell={r['sell_price']})"
            )
            continue
        seen.add(key)
        kept.append(r)
    return kept, dupes


# ─── Summary rendering ────────────────────────────────────────────────


def _fmt_price(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def print_summary(
    parsed_count: int,
    valid_count: int,
    errors: list[str],
    warnings: list[str],
    dupes: list[str],
    rows_with_cycle: list[dict],
) -> None:
    print(f"Parsed rows:        {parsed_count}")
    print(f"Valid rows:         {valid_count}")
    print(f"Validation errors:  {len(errors)}")
    for e in errors:
        print(f"  {e}")
    print(f"Brand warnings:     {len(warnings)}")
    for w in warnings:
        print(f"  {w}")
    print(f"Duplicates:         {len(dupes)}")
    for d in dupes:
        print(f"  {d}")
    cycles = Counter(
        r["cycle_id"] for r in rows_with_cycle if r.get("cycle_id")
    )
    print("Cycle distribution:")
    if not cycles:
        print("  (none)")
    for cid in sorted(cycles):
        n = cycles[cid]
        print(f"  {cid}:  {n} trade{'s' if n != 1 else ''}")
    accounts = Counter(r["account"] for r in rows_with_cycle)
    print("Accounts:")
    if not accounts:
        print("  (none)")
    for a in sorted(accounts):
        print(f"  {a}:  {accounts[a]}")


# ─── Atomic write ─────────────────────────────────────────────────────


def write_ledger_atomic(rows: list[dict], ledger_path: str) -> None:
    """Append rows to ledger via .tmp + os.replace.

    If the ledger file is missing or empty (no header), writes the header
    before the new rows. If the file already has a header (or rows), the
    existing content is preserved and new rows are appended.
    Raises OSError on any filesystem failure.
    """
    tmp_path = ledger_path + ".tmp"
    existing = ""
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8", newline="") as src:
            existing = src.read()

    parent = os.path.dirname(ledger_path) or "."
    os.makedirs(parent, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8", newline="") as dst:
        if existing.strip():
            dst.write(existing)
            if not existing.endswith("\n"):
                dst.write("\n")
        else:
            writer = csv.writer(dst)
            writer.writerow(OUTPUT_COLUMNS)
        writer = csv.writer(dst)
        for r in rows:
            writer.writerow([
                r["date_closed"],
                r["cycle_id"],
                r["brand"],
                r["reference"],
                r["account"],
                _fmt_price(r["buy_price"]),
                _fmt_price(r["sell_price"]),
            ])
    os.replace(tmp_path, ledger_path)


# ─── Post-write sibling calls ─────────────────────────────────────────


def _run_subcmd(cmd: list[str], label: str) -> None:
    """Invoke a sibling script via subprocess; print label + stdout/stderr."""
    print(f"\n── {label} ──")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        print(f"ERROR invoking {label}: {e}", file=sys.stderr)
        return
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip(), file=sys.stderr)


def post_write_hooks(
    rows: list[dict],
    skip_roll: bool,
) -> None:
    python = sys.executable
    ledger_mgr = str(SCRIPT_DIR / "ledger_manager.py")
    roll_script = str(SCRIPT_DIR / "roll_cycle.py")

    _run_subcmd([python, ledger_mgr, "summary"], "ledger_manager summary")
    _run_subcmd([python, ledger_mgr, "premium"], "ledger_manager premium")

    if skip_roll:
        print("\n-- roll_cycle skipped (--no-roll) --")
        return

    cycles = sorted({r["cycle_id"] for r in rows})
    for cid in cycles:
        _run_subcmd([python, roll_script, cid], f"roll_cycle {cid}")


# ─── Main ─────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical trades into the Grailzee ledger."
    )
    parser.add_argument("input", help="Path to input CSV")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and print summary; no writes.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip bad rows and import the good ones anyway.",
    )
    parser.add_argument(
        "--no-roll", action="store_true",
        help="Skip roll_cycle.py invocation after write.",
    )
    parser.add_argument(
        "--ledger", default=None,
        help="Override LEDGER_PATH (for tests).",
    )
    parser.add_argument(
        "--name-cache", default=None,
        help="Override NAME_CACHE_PATH (for tests).",
    )
    args = parser.parse_args(argv)

    rc = check_dependencies()
    if rc != 0:
        return rc

    ledger_path = args.ledger or gc.LEDGER_PATH
    name_cache_path = args.name_cache or gc.NAME_CACHE_PATH

    rows, file_errors = read_input(args.input)
    if file_errors:
        for e in file_errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    today = date.today()
    valid, validation_errors = validate_all(rows, today, force=args.force)

    with_cycle, cycle_err = derive_cycle_ids(valid)
    if cycle_err is not None:
        print(f"ERROR: {cycle_err}", file=sys.stderr)
        print(SECTION_12_3_HINT, file=sys.stderr)
        return 3

    existing_keys = load_existing_ledger_keys(ledger_path)
    to_write, dupe_messages = filter_duplicates(with_cycle, existing_keys)

    name_cache = load_name_cache(name_cache_path)
    warnings = brand_mismatch_warnings(to_write, name_cache)

    print_summary(
        parsed_count=len(rows),
        valid_count=len(valid),
        errors=validation_errors,
        warnings=warnings,
        dupes=dupe_messages,
        rows_with_cycle=to_write,
    )

    blocking_errors = validation_errors and not args.force
    if blocking_errors:
        print("\nAborting: validation errors present (use --force to import "
              "only the valid rows).", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\n── Dry run: rows that would be appended ──")
        for r in to_write:
            print(
                f"  {r['date_closed']}  {r['cycle_id']}  {r['brand']:<12} "
                f"{r['reference']:<20} {r['account']:<3} "
                f"buy={_fmt_price(r['buy_price'])} "
                f"sell={_fmt_price(r['sell_price'])}"
            )
        print("\nDry run complete. No disk writes performed.")
        return 0

    if not to_write:
        print("\nNothing to write (0 rows after dedup).")
        return 0

    try:
        write_ledger_atomic(to_write, ledger_path)
    except OSError as e:
        print(f"ERROR writing ledger: {e}", file=sys.stderr)
        return 2

    print(f"\nAppended {len(to_write)} row(s) to {ledger_path}.")

    post_write_hooks(to_write, skip_roll=args.no_roll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
