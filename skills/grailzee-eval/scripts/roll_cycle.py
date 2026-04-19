"""Produce cycle_outcome.json for the previous cycle.

New in v2 per guide Section 5.7. v1 has no cycle concept.
Thin wrapper around read_ledger.cycle_rollup(): loads inputs, delegates
computation, writes JSON output.

Called by orchestrator as:
    roll_cycle.run(previous_cycle_id=prev_cycle(current_cycle_id))

Usage:
    roll_cycle.py <previous_cycle_id> [--ledger PATH] [--cache PATH]
                  [--cycle-focus PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    CYCLE_OUTCOME_PATH,
    get_tracer,
    load_cycle_focus,
)
from scripts.read_ledger import cycle_rollup

tracer = get_tracer(__name__)


def run(
    previous_cycle_id: str,
    ledger_path: str | None = None,
    cache_path: str | None = None,
    cycle_focus_path: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Produce cycle_outcome.json for the given cycle.

    Loads cycle_focus, delegates to read_ledger.cycle_rollup(),
    writes JSON to output_path. Returns the outcome dict.
    """
    focus = load_cycle_focus(cycle_focus_path)
    outcome = cycle_rollup(
        previous_cycle_id,
        ledger_path=ledger_path,
        cache_path=cache_path,
        cycle_focus=focus,
    )

    out = output_path or CYCLE_OUTCOME_PATH
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(outcome, f, indent=2, default=str)
        f.write("\n")

    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous_cycle_id", help="Cycle ID to roll (e.g. cycle_2026-14)")
    parser.add_argument("--ledger", default=None, help="Path to trade_ledger.csv")
    parser.add_argument("--cache", default=None, help="Path to analysis_cache.json")
    parser.add_argument("--cycle-focus", default=None, help="Path to cycle_focus.json")
    parser.add_argument("--output", default=None, help="Path to write cycle_outcome.json")
    args = parser.parse_args()

    with tracer.start_as_current_span("roll_cycle.run") as span:
        span.set_attribute("cycle_id", args.previous_cycle_id)

        outcome = run(
            args.previous_cycle_id,
            ledger_path=args.ledger,
            cache_path=args.cache,
            cycle_focus_path=args.cycle_focus,
            output_path=args.output,
        )
        span.set_attribute("total_trades", outcome["summary"]["total_trades"])

        print(json.dumps(outcome, indent=2, default=str))
        return 0


if __name__ == "__main__":
    sys.exit(main())
