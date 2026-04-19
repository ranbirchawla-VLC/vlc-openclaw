"""Historical trade backfill tool for the Grailzee ledger.

Three modes:
  backfill_ledger.py validate <input.csv>
  backfill_ledger.py preview <input.csv>
  backfill_ledger.py commit <input.csv> [--ledger PATH]

Validates input rows against the ledger schema, computes aggregates,
and optionally appends to the production ledger. All output is JSON
on stdout. Errors to stderr.

Exit codes: 0 = clean (warnings ok), 2 = validation failures, 1 = other.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter
from datetime import date
from io import StringIO
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    ACCOUNT_FEES,
    LEDGER_COLUMNS,
    LEDGER_PATH,
    LedgerRow,
    VALID_ACCOUNTS,
    append_ledger_row,
    cycle_id_from_date,
    get_tracer,
    parse_ledger_csv,
)

tracer = get_tracer(__name__)


# ─── Parsing ──────────────────────────────────────────────────────────


def _strip_comments_and_blanks(text: str) -> str:
    """Remove comment lines (# prefix) and trailing blank lines."""
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped.strip() == "" and out:
            continue
        out.append(line)
    return "".join(out)


def _strip_bom(text: str) -> str:
    """Remove UTF-8 BOM if present."""
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def parse_input(path: str) -> tuple[list[dict], list[str]]:
    """Parse a backfill CSV. Returns (rows, errors).

    Rows are raw dicts from csv.DictReader. Errors are per-row
    messages; if errors is non-empty, no rows should be committed.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    raw = _strip_bom(raw)
    raw = _strip_comments_and_blanks(raw)

    reader = csv.DictReader(StringIO(raw))

    # Validate header
    if reader.fieldnames is None or list(reader.fieldnames) != LEDGER_COLUMNS:
        return [], [
            f"Header mismatch. Expected: {LEDGER_COLUMNS}. "
            f"Got: {reader.fieldnames}"
        ]

    rows = list(reader)
    return rows, []


# ─── Validation ───────────────────────────────────────────────────────


def validate_row(raw: dict, row_num: int) -> tuple[
    LedgerRow | None, list[str], list[str]
]:
    """Validate one row. Returns (LedgerRow | None, errors, warnings).

    If errors is non-empty, the LedgerRow is None.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. date_closed
    ds = (raw.get("date_closed") or "").strip()
    trade_date: date | None = None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ds):
        errors.append(f"Row {row_num}: Invalid date format '{ds}' (need YYYY-MM-DD)")
    else:
        try:
            y, m, d = ds.split("-")
            trade_date = date(int(y), int(m), int(d))
            if trade_date > date.today():
                errors.append(f"Row {row_num}: Future date {ds}")
        except ValueError:
            errors.append(f"Row {row_num}: Invalid date '{ds}'")

    # 2. cycle_id
    raw_cycle = (raw.get("cycle_id") or "").strip()
    cycle = raw_cycle
    if trade_date and raw_cycle:
        expected = cycle_id_from_date(trade_date)
        if raw_cycle != expected:
            errors.append(
                f"Row {row_num}: cycle_id '{raw_cycle}' does not match "
                f"computed '{expected}' for date {ds}"
            )
    elif trade_date and not raw_cycle:
        cycle = cycle_id_from_date(trade_date)

    # 3. brand
    brand = (raw.get("brand") or "").strip()
    if not brand:
        errors.append(f"Row {row_num}: brand is empty")

    # 4. reference
    reference = (raw.get("reference") or "").strip()
    if not reference:
        errors.append(f"Row {row_num}: reference is empty")
    elif "," in reference or '"' in reference:
        errors.append(
            f"Row {row_num}: reference contains comma or quote (CSV corruption?)"
        )

    # 5. account
    account_raw = (raw.get("account") or "").strip().upper()
    if account_raw not in VALID_ACCOUNTS:
        errors.append(
            f"Row {row_num}: invalid account '{raw.get('account')}' "
            f"(must be NR or RES)"
        )

    # 6. buy_price
    buy: float = 0
    buy_raw = (raw.get("buy_price") or "").strip()
    try:
        buy = float(buy_raw.replace("$", "").replace(",", ""))
        if buy <= 0:
            errors.append(f"Row {row_num}: buy_price must be positive, got {buy}")
    except (ValueError, TypeError):
        errors.append(f"Row {row_num}: buy_price not numeric: '{buy_raw}'")

    # 7. sell_price
    sell: float = 0
    sell_raw = (raw.get("sell_price") or "").strip()
    try:
        sell = float(sell_raw.replace("$", "").replace(",", ""))
        if sell <= 0:
            errors.append(f"Row {row_num}: sell_price must be positive, got {sell}")
    except (ValueError, TypeError):
        errors.append(f"Row {row_num}: sell_price not numeric: '{sell_raw}'")

    # 8. sell < buy warning
    if buy > 0 and sell > 0 and sell < buy:
        warnings.append(
            f"Row {row_num}: Losing trade (sell {sell} < buy {buy})"
        )

    # 9. High-value warning
    if buy > 50000:
        warnings.append(
            f"Row {row_num}: High-value trade (buy_price={buy})"
        )

    if errors:
        return None, errors, warnings

    return LedgerRow(
        date_closed=trade_date,  # type: ignore[arg-type]
        cycle_id=cycle,
        brand=brand,
        reference=reference,
        account=account_raw,
        buy_price=buy,
        sell_price=sell,
    ), errors, warnings


def validate_all(raw_rows: list[dict]) -> tuple[
    list[LedgerRow], list[str], list[str]
]:
    """Validate all rows. Returns (valid_rows, all_errors, all_warnings)."""
    valid: list[LedgerRow] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []
    for i, raw in enumerate(raw_rows, start=2):
        row, errs, warns = validate_row(raw, i)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        if row:
            valid.append(row)
    return valid, all_errors, all_warnings


# ─── Aggregates ───────────────────────────────────────────────────────


def compute_aggregates(rows: list[LedgerRow]) -> dict:
    """Compute preview aggregates for validated rows."""
    if not rows:
        return {
            "total_trades": 0, "total_buy": 0, "total_sell": 0,
            "total_fees": 0, "total_net_profit": 0, "avg_roi_pct": 0,
            "profitable_count": 0, "losing_count": 0,
            "accounts": {}, "brands": {}, "date_range": {},
            "cycles": [],
        }

    rois = []
    profitable = 0
    total_fees = 0
    for r in rows:
        fees = ACCOUNT_FEES.get(r.account, 149)
        net = r.sell_price - r.buy_price - fees
        roi = (net / r.buy_price) * 100 if r.buy_price > 0 else 0
        rois.append(roi)
        total_fees += fees
        if net > 0:
            profitable += 1

    total_buy = sum(r.buy_price for r in rows)
    total_sell = sum(r.sell_price for r in rows)

    return {
        "total_trades": len(rows),
        "total_buy": round(total_buy, 2),
        "total_sell": round(total_sell, 2),
        "total_fees": round(total_fees, 2),
        "total_net_profit": round(total_sell - total_buy - total_fees, 2),
        "avg_roi_pct": round(statistics.mean(rois), 2),
        "profitable_count": profitable,
        "losing_count": len(rows) - profitable,
        "accounts": dict(Counter(r.account for r in rows)),
        "brands": dict(Counter(r.brand for r in rows)),
        "date_range": {
            "earliest": min(r.date_closed for r in rows).isoformat(),
            "latest": max(r.date_closed for r in rows).isoformat(),
        },
        "cycles": sorted(set(r.cycle_id for r in rows)),
    }


# ─── Commands ─────────────────────────────────────────────────────────


def cmd_validate(args: argparse.Namespace) -> int:
    with tracer.start_as_current_span("backfill_ledger.validate") as span:
        span.set_attribute("input_path", args.input)
        raw_rows, parse_errors = parse_input(args.input)
        if parse_errors:
            result = {"status": "error", "errors": parse_errors}
            span.set_attribute("rows_total", 0)
            span.set_attribute("rows_rejected", len(parse_errors))
            print(json.dumps(result, indent=2))
            return 2

        valid, errors, warnings = validate_all(raw_rows)
        span.set_attribute("rows_total", len(raw_rows))
        span.set_attribute("rows_valid", len(valid))
        span.set_attribute("rows_rejected", len(errors))
        span.set_attribute("warning_count", len(warnings))

        result = {
            "status": "error" if errors else "ok",
            "rows_total": len(raw_rows),
            "rows_valid": len(valid),
            "rows_rejected": len(raw_rows) - len(valid),
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(result, indent=2))
        return 2 if errors else 0


def cmd_preview(args: argparse.Namespace) -> int:
    with tracer.start_as_current_span("backfill_ledger.preview") as span:
        span.set_attribute("input_path", args.input)
        raw_rows, parse_errors = parse_input(args.input)
        if parse_errors:
            print(json.dumps({"status": "error", "errors": parse_errors}, indent=2))
            return 2

        valid, errors, warnings = validate_all(raw_rows)
        span.set_attribute("rows_total", len(raw_rows))
        span.set_attribute("rows_valid", len(valid))
        span.set_attribute("rows_rejected", len(errors))
        span.set_attribute("warning_count", len(warnings))

        if errors:
            print(json.dumps({
                "status": "error",
                "rows_validated": len(raw_rows),
                "rows_rejected": len(raw_rows) - len(valid),
                "errors": errors,
                "warnings": warnings,
            }, indent=2))
            return 2

        agg = compute_aggregates(valid)
        span.set_attribute("total_net_profit", agg["total_net_profit"])

        print(json.dumps({
            "input_file": args.input,
            "rows_validated": len(valid),
            "rows_rejected": 0,
            "warnings": warnings,
            "aggregates": agg,
        }, indent=2))
        return 0


def cmd_commit(args: argparse.Namespace) -> int:
    with tracer.start_as_current_span("backfill_ledger.commit") as span:
        span.set_attribute("input_path", args.input)
        span.set_attribute("ledger_path", args.ledger)

        raw_rows, parse_errors = parse_input(args.input)
        if parse_errors:
            print(json.dumps({"status": "error", "errors": parse_errors}, indent=2),
                  file=sys.stderr)
            return 2

        # Validate ALL rows before any write (atomic: all or nothing)
        valid, errors, warnings = validate_all(raw_rows)
        if errors:
            print(json.dumps({
                "status": "error",
                "message": "Validation failed; zero rows written.",
                "rows_rejected": len(raw_rows) - len(valid),
                "errors": errors,
                "warnings": warnings,
            }, indent=2), file=sys.stderr)
            return 2

        # Check existing ledger state
        existing = parse_ledger_csv(args.ledger)
        rows_before = len(existing)
        span.set_attribute("ledger_rows_before", rows_before)

        if rows_before > 0:
            print(
                f"WARNING: Target ledger has {rows_before} existing rows. "
                f"Appending {len(valid)} new rows.",
                file=sys.stderr,
            )

        # Write all validated rows
        for row in valid:
            append_ledger_row(row, args.ledger)

        rows_after = len(parse_ledger_csv(args.ledger))
        span.set_attribute("ledger_rows_after", rows_after)

        print(json.dumps({
            "status": "ok",
            "rows_committed": len(valid),
            "ledger_rows_before": rows_before,
            "ledger_rows_after": rows_after,
            "warnings": warnings,
            "aggregates": compute_aggregates(valid),
        }, indent=2))
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_val = sub.add_parser("validate", help="Validate input CSV")
    p_val.add_argument("input", help="Path to input CSV")

    p_pre = sub.add_parser("preview", help="Validate + show aggregates")
    p_pre.add_argument("input", help="Path to input CSV")

    p_com = sub.add_parser("commit", help="Validate + append to ledger")
    p_com.add_argument("input", help="Path to input CSV")
    p_com.add_argument("--ledger", default=LEDGER_PATH,
                       help=f"Target ledger (default: {LEDGER_PATH})")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2

    dispatch = {
        "validate": cmd_validate,
        "preview": cmd_preview,
        "commit": cmd_commit,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
