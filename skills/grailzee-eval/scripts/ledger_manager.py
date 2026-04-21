"""Grailzee Trade Ledger Manager — CLI interface.

Four subcommands: log, summary, premium, cycle_rollup.
All output is JSON on stdout. Errors to stderr.
Exit codes: 0 success, 2 bad input, 1 other errors.

Usage:
    ledger_manager.py log <brand> <ref> <account> <buy> <sell> --buy-date YYYY-MM-DD [--sell-date YYYY-MM-DD] [--ledger PATH] [--cache PATH]
    ledger_manager.py summary [--brand NAME] [--since YYYY-MM-DD] [--reference REF] [--cycle ID] [--ledger PATH] [--cache PATH]
    ledger_manager.py premium [--ledger PATH] [--cache PATH]
    ledger_manager.py cycle_rollup <cycle_id> [--ledger PATH] [--cache PATH] [--focus PATH]

Phase A.6 / schema v1 §4.3: --date split into --buy-date and --sell-date.
--buy-date is required on the script path (bot-side will prompt when
integration lands in a B-phase task). --sell-date defaults to today.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Ensure the v2 root is importable
SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    LEDGER_PATH,
    VALID_ACCOUNTS,
    LedgerRow,
    append_ledger_row,
    calculate_presentation_premium,
    cycle_id_from_date,
    get_tracer,
)
from scripts.read_ledger import (
    cycle_rollup,
    reference_confidence,
    run as ledger_run,
)

tracer = get_tracer(__name__)


def cmd_log(args: argparse.Namespace) -> int:
    """Log a new trade to the ledger."""
    with tracer.start_as_current_span("ledger_log") as span:
        span.set_attribute("brand", args.brand)
        span.set_attribute("reference", args.reference)
        span.set_attribute("account", args.account)

        # Validate account
        account = args.account.upper()
        if account not in VALID_ACCOUNTS:
            print(json.dumps({
                "status": "error",
                "error": "invalid_account",
                "message": f"Account must be one of {sorted(VALID_ACCOUNTS)}, got '{args.account}'",
            }), file=sys.stderr)
            return 2

        # Validate prices
        try:
            buy = float(str(args.buy_price).replace("$", "").replace(",", ""))
            sell = float(str(args.sell_price).replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            print(json.dumps({
                "status": "error",
                "error": "invalid_price",
                "message": f"Cannot parse prices: buy={args.buy_price}, sell={args.sell_price}",
            }), file=sys.stderr)
            return 2

        if buy <= 0 or sell <= 0:
            print(json.dumps({
                "status": "error",
                "error": "invalid_price",
                "message": "Prices must be positive",
            }), file=sys.stderr)
            return 2

        # A.6: buy_date is required on the script path; sell_date defaults
        # to today when omitted. See schema v1 §4.3.
        if not args.buy_date:
            print(json.dumps({
                "status": "error",
                "error": "missing_buy_date",
                "message": (
                    "--buy-date is required (YYYY-MM-DD). "
                    "Schema v1 §4.3; script-side fails loud when absent."
                ),
            }), file=sys.stderr)
            return 2
        try:
            y, m, d = args.buy_date.split("-")
            buy_date = date(int(y), int(m), int(d))
        except (ValueError, TypeError):
            print(json.dumps({
                "status": "error",
                "error": "invalid_date",
                "message": f"Cannot parse --buy-date: {args.buy_date}. Use YYYY-MM-DD.",
            }), file=sys.stderr)
            return 2

        if args.sell_date:
            try:
                y, m, d = args.sell_date.split("-")
                sell_date = date(int(y), int(m), int(d))
            except (ValueError, TypeError):
                print(json.dumps({
                    "status": "error",
                    "error": "invalid_date",
                    "message": f"Cannot parse --sell-date: {args.sell_date}. Use YYYY-MM-DD.",
                }), file=sys.stderr)
                return 2
        else:
            sell_date = date.today()

        buy_cycle_id = cycle_id_from_date(buy_date)
        sell_cycle_id = cycle_id_from_date(sell_date)
        span.set_attribute("buy_date_present", True)
        span.set_attribute("buy_cycle_id", buy_cycle_id)
        span.set_attribute("sell_cycle_id", sell_cycle_id)
        span.set_attribute("buy_price", buy)
        span.set_attribute("sell_price", sell)

        row = LedgerRow(
            sell_date=sell_date,
            sell_cycle_id=sell_cycle_id,
            buy_date=buy_date,
            buy_cycle_id=buy_cycle_id,
            brand=args.brand,
            reference=args.reference,
            account=account,
            buy_price=buy,
            sell_price=sell,
        )
        append_ledger_row(row, args.ledger)

        print(json.dumps({
            "status": "ok",
            "trade": {
                "buy_date": buy_date.isoformat(),
                "sell_date": sell_date.isoformat(),
                "buy_cycle_id": buy_cycle_id,
                "sell_cycle_id": sell_cycle_id,
                "brand": args.brand,
                "reference": args.reference,
                "account": account,
                "buy_price": buy,
                "sell_price": sell,
            },
        }))
        return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Query ledger summary with optional filters."""
    with tracer.start_as_current_span("ledger_summary") as span:
        since = None
        if args.since:
            try:
                y, m, d = args.since.split("-")
                since = date(int(y), int(m), int(d))
            except (ValueError, TypeError):
                print(json.dumps({
                    "status": "error",
                    "error": "invalid_date",
                    "message": f"Cannot parse --since: {args.since}",
                }), file=sys.stderr)
                return 2

        if args.brand:
            span.set_attribute("filter.brand", args.brand)
        if args.reference:
            span.set_attribute("filter.reference", args.reference)
        if args.cycle:
            span.set_attribute("filter.cycle_id", args.cycle)

        result = ledger_run(
            ledger_path=args.ledger,
            cache_path=args.cache,
            brand=args.brand,
            since=since,
            reference=args.reference,
            cycle_id=args.cycle,
        )
        print(json.dumps(result, default=str))
        return 0


def cmd_premium(args: argparse.Namespace) -> int:
    """Compute presentation premium stats from the ledger."""
    with tracer.start_as_current_span("ledger_premium") as span:
        result = ledger_run(ledger_path=args.ledger, cache_path=args.cache)
        trades = result.get("trades", [])
        # Build rows compatible with calculate_presentation_premium
        prem_rows = [
            {"premium_vs_median": t["premium_vs_median"],
             "median_at_trade": t["median_at_trade"]}
            for t in trades
        ]
        premium = calculate_presentation_premium(prem_rows)
        span.set_attribute("trade_count", premium["trade_count"])
        span.set_attribute("threshold_met", premium["threshold_met"])
        print(json.dumps(premium))
        return 0


def cmd_cycle_rollup(args: argparse.Namespace) -> int:
    """Produce cycle outcome rollup."""
    with tracer.start_as_current_span("ledger_cycle_rollup") as span:
        span.set_attribute("cycle_id", args.cycle_id)

        focus = None
        if args.focus:
            try:
                with open(args.focus, "r") as f:
                    focus = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                print(json.dumps({
                    "status": "error",
                    "error": "invalid_focus",
                    "message": f"Cannot read focus file: {exc}",
                }), file=sys.stderr)
                return 2

        result = cycle_rollup(
            args.cycle_id,
            ledger_path=args.ledger,
            cache_path=args.cache,
            cycle_focus=focus,
        )
        print(json.dumps(result, default=str))
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Grailzee Trade Ledger Manager")
    parser.add_argument("--ledger", default=LEDGER_PATH,
                        help="Override ledger CSV path")
    parser.add_argument("--cache", default=None,
                        help="Override analysis cache JSON path")
    sub = parser.add_subparsers(dest="command")

    # log
    p_log = sub.add_parser("log", help="Log a trade")
    p_log.add_argument("brand")
    p_log.add_argument("reference")
    p_log.add_argument("account")
    p_log.add_argument("buy_price")
    p_log.add_argument("sell_price")
    p_log.add_argument(
        "--buy-date", dest="buy_date", default=None,
        help="YYYY-MM-DD. Required (A.6 / schema v1 §4.3).",
    )
    p_log.add_argument(
        "--sell-date", dest="sell_date", default=None,
        help="YYYY-MM-DD. Defaults to today when omitted.",
    )

    # summary
    p_sum = sub.add_parser("summary", help="Query ledger summary")
    p_sum.add_argument("--brand", default=None)
    p_sum.add_argument("--since", default=None, help="YYYY-MM-DD")
    p_sum.add_argument("--reference", default=None)
    p_sum.add_argument("--cycle", default=None)

    # premium
    sub.add_parser("premium", help="Presentation premium stats")

    # cycle_rollup
    p_cr = sub.add_parser("cycle_rollup", help="Cycle outcome rollup")
    p_cr.add_argument("cycle_id")
    p_cr.add_argument("--focus", default=None, help="Path to cycle_focus.json")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 2

    dispatch = {
        "log": cmd_log,
        "summary": cmd_summary,
        "premium": cmd_premium,
        "cycle_rollup": cmd_cycle_rollup,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
