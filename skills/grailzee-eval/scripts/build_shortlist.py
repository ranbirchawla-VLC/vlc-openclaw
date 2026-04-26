"""Wave 1.1: build the cycle shortlist CSV for the strategy reading-partner flow.

Produces ``cycle_shortlist_<cycle_id>.csv`` in ``STATE_PATH`` (Drive).
Schema v3: one row per bucket. Reference-level fields repeat across that
reference's bucket rows. Keying axes (dial_numerals, auction_type,
dial_color) and named_special metadata distinguish bucket rows within a
reference.

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
    # Reference-level identity (repeat across bucket rows of the same ref)
    "brand",
    "reference",
    "model",
    # Bucket keying axes (distinguish rows within a reference)
    "dial_numerals",
    "auction_type",
    "dial_color",
    "named_special",
    # Per-bucket market fields (null on Low data buckets)
    "signal",
    "median",
    "max_buy_nr",
    "max_buy_res",
    "st_pct",
    "volume",
    "risk_nr",
    "capital_required_nr",
    "capital_required_res",
    "expected_net_at_median_nr",
    "expected_net_at_median_res",
    # Reference-level trend (repeat across bucket rows)
    "trend_signal",
    "trend_median_change",
    "trend_median_pct",
    # Reference-level momentum (repeat)
    "momentum_score",
    "momentum_label",
    # Reference-level confidence / own-ledger rollup (repeat)
    "confidence_trades",
    "confidence_profitable",
    "confidence_win_rate",
    "confidence_avg_roi",
    "confidence_avg_premium",
    "confidence_last_trade",
    # Strategy session marker (always empty at generation)
    "keep",
]

SIGNAL_ORDER: list[str] = [
    "Strong", "Normal", "Reserve", "Careful", "Pass", "Low data",
]
_SIGNAL_RANK: dict[str, int] = {s: i for i, s in enumerate(SIGNAL_ORDER)}

DEFAULT_SORT_KEY = "signal,volume_desc"


def _empty_if_none(v: object) -> object:
    """Null market field -> empty string. Zero stays 0."""
    return "" if v is None else v


def _bucket_key_str(row: dict) -> str:
    """Reconstruct the lowercase pipe-joined bucket key from a CSV row."""
    return (
        f"{row.get('dial_numerals', '').lower()}"
        f"|{row.get('auction_type', '').lower()}"
        f"|{row.get('dial_color', '').lower()}"
    )


def _flatten_row(ref_entry: dict, bucket_key: str, bucket: dict) -> dict:
    """Project one (reference_entry, bucket) pair to the 30-column row shape.

    Reference-level fields (brand, model, trend, momentum, confidence)
    repeat identically for every bucket row of the same reference.
    Bucket-level market fields (signal, median, max_buy_*, ...) come
    from the bucket dict and differ across rows of the same reference.
    """
    conf = ref_entry.get("confidence") or {}
    mom = ref_entry.get("momentum") or {}
    return {
        "brand": ref_entry.get("brand", ""),
        "reference": ref_entry.get("reference", ""),
        "model": ref_entry.get("model", ""),
        "dial_numerals": bucket.get("dial_numerals", ""),
        "auction_type": bucket.get("auction_type", ""),
        "dial_color": bucket.get("dial_color", ""),
        "named_special": bucket.get("named_special") or "",
        "signal": bucket.get("signal", ""),
        "median": _empty_if_none(bucket.get("median")),
        "max_buy_nr": _empty_if_none(bucket.get("max_buy_nr")),
        "max_buy_res": _empty_if_none(bucket.get("max_buy_res")),
        "st_pct": _empty_if_none(bucket.get("st_pct")),
        "volume": bucket.get("volume", 0),
        "risk_nr": _empty_if_none(bucket.get("risk_nr")),
        "capital_required_nr": _empty_if_none(bucket.get("capital_required_nr")),
        "capital_required_res": _empty_if_none(bucket.get("capital_required_res")),
        "expected_net_at_median_nr": _empty_if_none(bucket.get("expected_net_at_median_nr")),
        "expected_net_at_median_res": _empty_if_none(bucket.get("expected_net_at_median_res")),
        "trend_signal": _empty_if_none(ref_entry.get("trend_signal")),
        "trend_median_change": _empty_if_none(ref_entry.get("trend_median_change")),
        "trend_median_pct": _empty_if_none(ref_entry.get("trend_median_pct")),
        "momentum_score": _empty_if_none(mom.get("score")) if mom else "",
        "momentum_label": mom.get("label", "") if mom else "",
        "confidence_trades": _empty_if_none(conf.get("trades")) if conf else "",
        "confidence_profitable": _empty_if_none(conf.get("profitable")) if conf else "",
        "confidence_win_rate": _empty_if_none(conf.get("win_rate")) if conf else "",
        "confidence_avg_roi": _empty_if_none(conf.get("avg_roi")) if conf else "",
        "confidence_avg_premium": _empty_if_none(conf.get("avg_premium")) if conf else "",
        "confidence_last_trade": _empty_if_none(conf.get("last_trade")) if conf else "",
        "keep": "",
    }


def _signal_rank(row: dict) -> int:
    """Unknown signals sort last (past Low data)."""
    return _SIGNAL_RANK.get(row.get("signal", ""), len(SIGNAL_ORDER))


def _volume_desc(row: dict) -> int:
    """Descending volume via negation. Missing/zero volume sorts last."""
    v = row.get("volume")
    return -(v if isinstance(v, (int, float)) else 0)


_SORT_FIELD_FNS: dict[str, Callable[[dict], object]] = {
    "signal": _signal_rank,
    "volume_desc": _volume_desc,
    "volume": lambda r: r.get("volume") if isinstance(r.get("volume"), (int, float)) else 0,
    "median_desc": lambda r: -(r.get("median") if isinstance(r.get("median"), (int, float)) else 0),
    "reference": lambda r: r.get("reference", ""),
    "brand": lambda r: r.get("brand", ""),
    "bucket_key": _bucket_key_str,
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
    """tmp + fsync + os.replace. Tmp cleaned up on OSError."""
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
        The cache's ``references`` sub-dict (ref-id -> v3 per-reference
        entry). Each entry carries a ``buckets`` sub-dict; one CSV row
        is emitted per bucket. DJ configs are not emitted.
    cycle_id:
        Passed by the orchestrator; used in the filename. Standalone
        CLI derives from the cache's top-level ``cycle_id``.
    state_path:
        Output directory. Defaults to ``STATE_PATH``. Tests pass a tmp path.
    sort_key:
        Comma-separated field spec. Default ``"signal,volume_desc"``.
        ``reference`` and ``bucket_key`` are always appended as tiebreaks
        for determinism regardless of sort_key.
    """
    target_dir = state_path or STATE_PATH
    output_path = os.path.join(target_dir, f"cycle_shortlist_{cycle_id}.csv")

    rows: list[dict] = []
    for ref_entry in all_references.values():
        for bk, bucket in ref_entry.get("buckets", {}).items():
            rows.append(_flatten_row(ref_entry, bk, bucket))

    primary_fn = _sort_key_fn(sort_key)

    def _full_sort_key(row: dict) -> tuple:
        return primary_fn(row) + (row.get("reference", ""), _bucket_key_str(row))

    rows.sort(key=_full_sort_key)

    span = get_current_span()
    span.set_attribute("cycle_id", cycle_id)
    span.set_attribute("row_count", len(rows))  # v3: bucket count, not reference count
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
            "Comma-separated sort spec. Fields: signal, volume, volume_desc, "
            f"median_desc, reference, brand, bucket_key. Default: {DEFAULT_SORT_KEY}"
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
