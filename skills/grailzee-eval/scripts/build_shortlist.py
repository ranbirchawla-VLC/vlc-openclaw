"""Phase B.7: build the cycle shortlist CSV for the strategy reading-partner flow.

Produces ``cycle_shortlist_<cycle_id>.csv`` in ``STATE_PATH`` (Drive).
Every scored reference becomes one row. Ledger-derived columns write
as empty strings when the reference has no Vardalux trades (per §5.4
of the B.7 task: CSV scans cleanly with empty, not "null" / "None" / 0).

Invocation:
    Orchestrator (run_analysis.py Step 16):
        build_shortlist.run(all_references, cycle_id=..., state_path=...)

    Standalone CLI:
        python3 scripts/build_shortlist.py --cache <path> [--cycle-id <id>]
            [--state-path DIR] [--sort-key signal,volume_desc]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from opentelemetry.trace import get_current_span

from scripts.grailzee_common import STATE_PATH, get_tracer

tracer = get_tracer(__name__)


FIELDNAMES: list[str] = [
    "brand",
    "reference",
    "model",
    "signal",
    "median",
    "max_buy_nr",
    "st_pct",
    "volume",
    "risk_nr",
    "premium_vs_market_pct",
    "realized_premium_pct",
    "realized_premium_trade_count",
    "confidence_trades",
    "confidence_profitable",
    "confidence_win_rate",
    "confidence_avg_roi",
    "confidence_avg_premium",
    "confidence_last_trade",
    "momentum_score",
    "momentum_label",
    "capital_required_nr",
    "expected_net_at_median_nr",
    "keep",
]

SIGNAL_ORDER: list[str] = [
    "Strong", "Normal", "Reserve", "Careful", "Pass", "Low data",
]
_SIGNAL_RANK: dict[str, int] = {s: i for i, s in enumerate(SIGNAL_ORDER)}

DEFAULT_SORT_KEY = "signal,volume_desc"

_CONFIDENCE_SUBFIELDS = (
    "trades", "profitable", "win_rate", "avg_roi", "avg_premium", "last_trade",
)


def _empty_if_none(v):
    """Ledger-derived null → empty string (per §5.4). Zero stays 0."""
    return "" if v is None else v


def _flatten_row(ref: str, entry: dict) -> dict:
    """Project one cache ``references[<ref>]`` entry to the 23-col row shape.

    ``confidence`` and ``momentum`` are dicts in the cache; flatten to
    scalar columns with the ``<parent>_<field>`` naming from §5.2. A
    null ``confidence`` (reference has no Vardalux trades) expands to
    six empty-string columns.
    """
    conf = entry.get("confidence") or {}
    mom = entry.get("momentum") or {}
    return {
        "brand": entry.get("brand", ""),
        "reference": entry.get("reference", ref),
        "model": entry.get("model", ""),
        "signal": entry.get("signal", ""),
        "median": _empty_if_none(entry.get("median")),
        "max_buy_nr": _empty_if_none(entry.get("max_buy_nr")),
        "st_pct": _empty_if_none(entry.get("st_pct")),
        "volume": _empty_if_none(entry.get("volume")),
        "risk_nr": _empty_if_none(entry.get("risk_nr")),
        "premium_vs_market_pct": _empty_if_none(entry.get("premium_vs_market_pct")),
        "realized_premium_pct": _empty_if_none(entry.get("realized_premium_pct")),
        "realized_premium_trade_count": _empty_if_none(
            entry.get("realized_premium_trade_count")
        ),
        "confidence_trades": _empty_if_none(conf.get("trades")) if conf else "",
        "confidence_profitable": _empty_if_none(conf.get("profitable")) if conf else "",
        "confidence_win_rate": _empty_if_none(conf.get("win_rate")) if conf else "",
        "confidence_avg_roi": _empty_if_none(conf.get("avg_roi")) if conf else "",
        "confidence_avg_premium": _empty_if_none(conf.get("avg_premium")) if conf else "",
        "confidence_last_trade": _empty_if_none(conf.get("last_trade")) if conf else "",
        "momentum_score": _empty_if_none(mom.get("score")) if mom else "",
        "momentum_label": mom.get("label", "") if mom else "",
        "capital_required_nr": _empty_if_none(entry.get("capital_required_nr")),
        "expected_net_at_median_nr": _empty_if_none(entry.get("expected_net_at_median_nr")),
        "keep": "",
    }


def _signal_rank(row: dict) -> int:
    """Unknown signals sort last (past Low data)."""
    return _SIGNAL_RANK.get(row.get("signal", ""), len(SIGNAL_ORDER))


def _volume_desc(row: dict) -> int:
    """Descending volume via negation. Empty/missing volume sorts last."""
    v = row.get("volume")
    return -(v if isinstance(v, (int, float)) else 0)


_SORT_FIELD_FNS: dict[str, Callable[[dict], object]] = {
    "signal": _signal_rank,
    "volume_desc": _volume_desc,
    "volume": lambda r: r.get("volume") if isinstance(r.get("volume"), (int, float)) else 0,
    "median_desc": lambda r: -(r.get("median") if isinstance(r.get("median"), (int, float)) else 0),
    "reference": lambda r: r.get("reference", ""),
    "brand": lambda r: r.get("brand", ""),
}


def _sort_key_fn(sort_key: str) -> Callable[[dict], tuple]:
    """Build a composite-key function from a comma-separated spec."""
    parts = [p.strip() for p in sort_key.split(",") if p.strip()]
    if not parts:
        parts = [p.strip() for p in DEFAULT_SORT_KEY.split(",")]
    fns = []
    for p in parts:
        if p not in _SORT_FIELD_FNS:
            raise ValueError(
                f"Unknown sort field {p!r}. Known: {sorted(_SORT_FIELD_FNS)}"
            )
        fns.append(_SORT_FIELD_FNS[p])
    return lambda row: tuple(fn(row) for fn in fns)


def _atomic_write_csv(rows: list[dict], fieldnames: list[str], path: str) -> None:
    """tmp + fsync + os.replace. Tmp cleaned up on OSError.

    Ports the durability posture from
    ``backfill_ledger.write_ledger_atomic``: a kill -9 or power loss
    after ``os.replace`` cannot surface a rename-completed-but-contents-
    truncated CSV.
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def run(
    all_references: dict,
    cycle_id: str,
    state_path: str | None = None,
    sort_key: str = DEFAULT_SORT_KEY,
) -> str:
    """Write ``cycle_shortlist_<cycle_id>.csv``. Return the output path.

    all_references:
        The cache's ``references`` sub-dict (ref-id → per-reference
        entry). DJ configs are NOT emitted — the shortlist tracks only
        top-level references (scored refs with 3+ sales per A.2
        ``min_sales_for_scoring``). ``write_cache`` already drops
        unscored refs upstream, so this function trusts its input.
    cycle_id:
        Passed by the orchestrator; used in the filename. Standalone
        CLI derives from the cache's top-level ``cycle_id``.
    state_path:
        Directory for the CSV. Defaults to ``STATE_PATH``. Tests pass
        a tmp path.
    sort_key:
        Comma-separated field spec. Default
        ``"signal,volume_desc"``: signal order Strong → Low data, then
        descending volume.
    """
    target_dir = state_path or STATE_PATH
    output_path = os.path.join(target_dir, f"cycle_shortlist_{cycle_id}.csv")

    rows = [_flatten_row(ref, entry) for ref, entry in all_references.items()]
    rows.sort(key=_sort_key_fn(sort_key))

    # Attributes on the caller's span (orchestrator's
    # ``build_shortlist.run`` span, or ``main()``'s). Silent no-op
    # outside any span context. Matches the write_cache convention.
    span = get_current_span()
    span.set_attribute("cycle_id", cycle_id)
    span.set_attribute("row_count", len(rows))
    span.set_attribute("sort_key", sort_key)
    span.set_attribute("output_path", output_path)

    _atomic_write_csv(rows, FIELDNAMES, output_path)
    return output_path


# --- CLI entry ────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", required=True,
        help="Path to analysis_cache.json; reads ``references`` sub-dict.",
    )
    parser.add_argument(
        "--cycle-id", default=None,
        help="Override cycle_id used in the filename. Defaults to the "
             "cache file's top-level cycle_id.",
    )
    parser.add_argument(
        "--state-path", default=None,
        help="Output directory. Defaults to STATE_PATH from grailzee_common.",
    )
    parser.add_argument(
        "--sort-key", default=DEFAULT_SORT_KEY,
        help=(
            "Comma-separated sort spec. Fields: signal, volume, "
            "volume_desc, median_desc, reference, brand. Default: "
            f"{DEFAULT_SORT_KEY}"
        ),
    )
    args = parser.parse_args()

    with open(args.cache, "r", encoding="utf-8") as f:
        cache = json.load(f)
    cycle_id = args.cycle_id or cache.get("cycle_id")
    if not cycle_id:
        print("error: --cycle-id not provided and cache has no cycle_id", file=sys.stderr)
        return 2
    references = cache.get("references", {})

    with tracer.start_as_current_span("build_shortlist.run"):
        output = run(
            references, cycle_id=cycle_id,
            state_path=args.state_path, sort_key=args.sort_key,
        )
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
