"""Query active hunting targets with strict cycle discipline.

Reads analysis_cache.json and cycle_focus.json to produce a cycle-filtered,
momentum-sorted target list enriched with ledger confidence data.

Unlike evaluate_deal (always available), query_targets enforces cycle
discipline: no filtered list until cycle_focus.json is current. An
explicit --ignore-cycle flag bypasses the gate for ad hoc exploration.

Extracted and refactored from v1 query_targets.py. v1 read sourcing_brief.json
with priority tiers; v2 reads analysis_cache.json with signal-based filtering,
momentum sorting, and cycle focus gating.

Usage:
    python3 query_targets.py [--cache PATH] [--ledger PATH] [--cycle-focus PATH]
        [--ignore-cycle] [--brand NAME] [--signal SIGNAL] [--budget AMOUNT]
        [--format FMT] [--sort FIELD]

Output: JSON to stdout
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    CACHE_PATH,
    CACHE_SCHEMA_VERSION,
    CYCLE_FOCUS_PATH,
    LEDGER_PATH,
    RISK_RESERVE_THRESHOLD,
    get_tracer,
)

from scripts import read_ledger

tracer = get_tracer(__name__)


# ─── Valid filter values ─────────────────────────────────────────────

VALID_SORT_FIELDS = {"momentum", "volume", "signal", "max_buy"}
VALID_FORMATS = {"NR", "Reserve"}
VALID_SIGNALS = {"Strong", "Normal", "Reserve", "Careful", "Pass"}

# Signal strength ordering for sort-by-signal (strongest first)
_SIGNAL_RANK = {
    "Strong": 0, "Normal": 1, "Reserve": 2,
    "Careful": 3, "Pass": 4, "Low data": 5,
}


# ─── Filter validation ──────────────────────────────────────────────


def _validate_filters(filters: dict | None) -> dict | None:
    """Validate filter values. Returns error response dict or None if valid."""
    if not filters:
        return None

    sort_by = filters.get("sort_by")
    if sort_by is not None and sort_by not in VALID_SORT_FIELDS:
        return {
            "status": "error",
            "error": "bad_filter",
            "message": (
                f"Invalid sort field: '{sort_by}'. "
                f"Accepted values: {', '.join(sorted(VALID_SORT_FIELDS))}"
            ),
        }

    fmt = filters.get("format")
    if fmt is not None and fmt not in VALID_FORMATS:
        return {
            "status": "error",
            "error": "bad_filter",
            "message": (
                f"Invalid format filter: '{fmt}'. "
                f"Accepted values: {', '.join(sorted(VALID_FORMATS))}"
            ),
        }

    signal = filters.get("signal")
    if signal is not None and signal not in VALID_SIGNALS:
        return {
            "status": "error",
            "error": "bad_filter",
            "message": (
                f"Invalid signal filter: '{signal}'. "
                f"Accepted values: {', '.join(sorted(VALID_SIGNALS))}"
            ),
        }

    return None


# ─── Cache loading ───────────────────────────────────────────────────


def _load_cache(cache_path: str) -> tuple[dict | None, dict | None]:
    """Load and validate analysis_cache.json.

    Returns (cache_dict, None) on success.
    Returns (None, error_response_dict) on missing file or stale schema.
    """
    if not os.path.exists(cache_path):
        return None, {
            "status": "error",
            "error": "no_cache",
            "message": (
                f"No analysis cache found at {cache_path}. "
                "Run the full Grailzee analyzer first to generate the cache."
            ),
        }

    with open(cache_path, "r") as f:
        cache = json.load(f)

    schema_version = cache.get("schema_version", 0)
    if schema_version < CACHE_SCHEMA_VERSION:
        return None, {
            "status": "error",
            "error": "stale_schema",
            "message": (
                f"Cache schema version {schema_version} is below required "
                f"version {CACHE_SCHEMA_VERSION}. Re-run the full analyzer."
            ),
        }

    return cache, None


# ─── Cycle gate ──────────────────────────────────────────────────────


def _check_cycle_gate(
    cycle_focus_path: str | None,
    cache_cycle_id: str | None,
    premium_status: dict | None,
    cache_meta: dict,
) -> tuple[dict | None, dict | None]:
    """Check cycle discipline gate.

    Returns (focus_dict, None) when gate passes.
    Returns (None, gate_response_dict) when gate fires.

    Gate fires on: missing file, malformed JSON, missing cycle_id key,
    stale cycle_id. Differentiated state in the response so the LLM
    can frame the message appropriately.
    """
    path = cycle_focus_path or CYCLE_FOCUS_PATH

    if not os.path.exists(path):
        return None, {
            "status": "gate",
            "state": "no_focus",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "message": (
                f"No active cycle focus for {cache_cycle_id or 'current cycle'}. "
                "Strategy session required before targets are set. "
                "Run grailzee-strategy in Chat to plan this cycle."
            ),
            "premium_status": premium_status,
            "cache_date": cache_meta.get("generated_at", "unknown"),
            "cache_report": cache_meta.get("source_report", "unknown"),
        }

    try:
        with open(path, "r") as f:
            focus = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return None, {
            "status": "gate",
            "state": "error",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "message": f"cycle_focus.json parse error: {exc}",
            "premium_status": premium_status,
            "cache_date": cache_meta.get("generated_at", "unknown"),
            "cache_report": cache_meta.get("source_report", "unknown"),
        }

    focus_cycle_id = focus.get("cycle_id")
    if focus_cycle_id is None:
        return None, {
            "status": "gate",
            "state": "error",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": None,
            "message": "cycle_focus.json missing cycle_id key",
            "premium_status": premium_status,
            "cache_date": cache_meta.get("generated_at", "unknown"),
            "cache_report": cache_meta.get("source_report", "unknown"),
        }

    if focus_cycle_id != cache_cycle_id:
        return None, {
            "status": "gate",
            "state": "stale_focus",
            "cycle_id_current": cache_cycle_id,
            "cycle_id_focus": focus_cycle_id,
            "message": (
                f"Cycle focus is for {focus_cycle_id}, "
                f"but current cycle is {cache_cycle_id}. "
                "Strategy session required to set targets for this cycle. "
                "Run grailzee-strategy in Chat."
            ),
            "premium_status": premium_status,
            "cache_date": cache_meta.get("generated_at", "unknown"),
            "cache_report": cache_meta.get("source_report", "unknown"),
        }

    return focus, None


# ─── Target collection ───────────────────────────────────────────────


def _build_target_entry(
    ref_key: str,
    ref_data: dict,
    focus_target: dict | None,
) -> dict:
    """Transform cache ref entry into target response entry.

    Computes format and max_buy from risk_nr + RISK_RESERVE_THRESHOLD.
    Honors max_buy_override from cycle_focus target when present.

    The format derivation (recommend_reserve from risk_nr) is identical
    to evaluate_deal._score_decision. When this is extracted to
    grailzee_common.derive_format_and_max_buy(), both callers should
    be updated. See Batch B backlog.
    """
    risk_nr = ref_data.get("risk_nr")
    recommend_reserve = (
        risk_nr is not None and risk_nr > RISK_RESERVE_THRESHOLD * 100
    )
    if recommend_reserve:
        computed_format = "Reserve"
        computed_max_buy = ref_data.get("max_buy_res", 0)
    else:
        computed_format = "NR"
        computed_max_buy = ref_data.get("max_buy_nr", 0)

    # Honor max_buy_override from cycle_focus target when present
    max_buy_override = None
    cycle_reason = None
    if focus_target is not None:
        max_buy_override = focus_target.get("max_buy_override")
        cycle_reason = focus_target.get("cycle_reason")

    effective_max_buy = (
        max_buy_override if max_buy_override is not None else computed_max_buy
    )

    momentum = ref_data.get("momentum") or {"score": 0, "label": "Stable"}

    return {
        "brand": ref_data.get("brand", ""),
        "model": ref_data.get("model", ""),
        "reference": ref_key,
        "momentum": momentum,
        "signal": ref_data.get("signal", "Low data"),
        "format": computed_format,
        "max_buy": effective_max_buy,
        "max_buy_override": max_buy_override,
        "risk_pct": round(risk_nr, 1) if risk_nr is not None else None,
        "volume": ref_data.get("volume", 0),
        "sell_through": ref_data.get("st_pct"),
        "cycle_reason": cycle_reason,
        "confidence": None,  # enriched later
    }


def _collect_targets(
    cache: dict,
    focus: dict | None,
    ignore_cycle: bool,
) -> tuple[list[dict], list[str]]:
    """Collect target entries from cache, filtered by focus when applicable.

    Returns (target_entries, not_in_cache_refs).
    """
    refs = cache.get("references", {})

    if ignore_cycle or focus is None:
        # Full universe; no cycle_reason
        targets = [
            _build_target_entry(key, data, None)
            for key, data in refs.items()
        ]
        return targets, []

    # Focus-filtered: only references in focus targets
    focus_targets = focus.get("targets", [])
    targets = []
    not_in_cache = []

    # Build lookup from focus target reference to focus target dict
    focus_lookup: dict[str, dict] = {}
    for ft in focus_targets:
        if isinstance(ft, dict):
            ref = ft.get("reference", "")
            focus_lookup[ref] = ft
        else:
            focus_lookup[str(ft)] = {"reference": str(ft)}

    for ref, ft in focus_lookup.items():
        if ref in refs:
            targets.append(_build_target_entry(ref, refs[ref], ft))
        else:
            not_in_cache.append(ref)

    return targets, not_in_cache


# ─── Filters ─────────────────────────────────────────────────────────


def _apply_filters(targets: list[dict], filters: dict | None) -> list[dict]:
    """Apply brand, signal, budget, format filters."""
    if not filters:
        return targets

    result = targets
    brand = filters.get("brand")
    if brand:
        brand_upper = brand.upper()
        result = [t for t in result if t["brand"].upper() == brand_upper]

    signal = filters.get("signal")
    if signal:
        result = [t for t in result if t["signal"] == signal]

    budget = filters.get("budget")
    if budget is not None:
        result = [t for t in result if t["max_buy"] <= budget]

    fmt = filters.get("format")
    if fmt:
        result = [t for t in result if t["format"] == fmt]

    return result


# ─── Sorting ─────────────────────────────────────────────────────────


def _sort_results(targets: list[dict], sort_by: str | None) -> list[dict]:
    """Sort targets.

    Default sort: momentum.score desc, volume desc, reference asc.
    Override: sort_by field as primary, same tiebreakers.
    """
    sort_by = sort_by or "momentum"

    def _momentum_score(t: dict) -> int:
        m = t.get("momentum")
        if isinstance(m, dict):
            return m.get("score", 0)
        return 0

    def _signal_rank(t: dict) -> int:
        return _SIGNAL_RANK.get(t.get("signal", "Low data"), 5)

    if sort_by == "momentum":
        return sorted(
            targets,
            key=lambda t: (-_momentum_score(t), -t.get("volume", 0), t.get("reference", "")),
        )
    elif sort_by == "volume":
        return sorted(
            targets,
            key=lambda t: (-t.get("volume", 0), -_momentum_score(t), t.get("reference", "")),
        )
    elif sort_by == "signal":
        return sorted(
            targets,
            key=lambda t: (_signal_rank(t), -t.get("volume", 0), t.get("reference", "")),
        )
    elif sort_by == "max_buy":
        return sorted(
            targets,
            key=lambda t: (t.get("max_buy", 0), -_momentum_score(t), t.get("reference", "")),
        )
    # Unreachable after validation, but defensive
    return targets


# ─── Confidence enrichment ───────────────────────────────────────────


def _enrich_with_confidence(
    targets: list[dict],
    ledger_path: str | None,
    cache_path: str | None,
) -> None:
    """Mutate targets in place: add confidence dict from ledger.

    Same interface as evaluate_deal._enrich_confidence, called per target.
    """
    for t in targets:
        t["confidence"] = read_ledger.reference_confidence(
            ledger_path=ledger_path,
            cache_path=cache_path,
            brand=t["brand"],
            reference=t["reference"],
        )


# ─── Response builder ───────────────────────────────────────────────


def _build_response(
    targets: list[dict],
    cache: dict,
    focus: dict | None,
    ignore_cycle: bool,
    not_in_cache: list[str],
) -> dict:
    """Assemble full response dict."""
    cache_meta = {
        "generated_at": cache.get("generated_at", "unknown"),
        "source_report": cache.get("source_report", "unknown"),
    }
    premium_status = cache.get("premium_status")
    cycle_id = cache.get("cycle_id")

    if ignore_cycle:
        return {
            "status": "ok_override",
            "warning": (
                "Operating outside cycle focus. "
                "Targets not filtered by strategic intent."
            ),
            "cycle_id": cycle_id,
            "target_count": len(targets),
            "targets": targets,
            "premium_status": premium_status,
            "cache_date": cache_meta["generated_at"],
            "cache_report": cache_meta["source_report"],
        }

    return {
        "status": "ok",
        "cycle_id": cycle_id,
        "cycle_focus_set_at": focus.get("set_at", "unknown") if focus else "unknown",
        "target_count": len(targets),
        "targets_not_in_cache": sorted(not_in_cache),
        "targets_not_in_cache_count": len(not_in_cache),
        "targets": targets,
        "premium_status": premium_status,
        "cache_date": cache_meta["generated_at"],
        "cache_report": cache_meta["source_report"],
    }


# ─── Public entry point ─────────────────────────────────────────────


def query_targets(
    cache_path: str | None = None,
    ledger_path: str | None = None,
    cycle_focus_path: str | None = None,
    ignore_cycle: bool = False,
    filters: dict | None = None,
    sort_by: str | None = None,
) -> dict:
    """Query active hunting targets. Returns structured result.

    Enforces cycle discipline unless ignore_cycle is True.
    All paths default to grailzee_common constants.
    Test injection via kwargs.
    """
    cache_path = cache_path or CACHE_PATH
    ledger_path = ledger_path or LEDGER_PATH

    # Merge sort_by into filters for unified validation
    effective_filters = dict(filters) if filters else {}
    if sort_by is not None:
        effective_filters["sort_by"] = sort_by

    with tracer.start_as_current_span("query_targets") as span:
        span.set_attribute("ignore_cycle", ignore_cycle)

        # Step 1: Validate filters
        validation_error = _validate_filters(effective_filters)
        if validation_error is not None:
            span.set_attribute("status", "error")
            return validation_error

        # Step 2: Load cache
        cache, error = _load_cache(cache_path)
        if error is not None:
            span.set_attribute("status", "error")
            return error

        cache_cycle_id = cache.get("cycle_id")
        premium_status = cache.get("premium_status")
        cache_meta = {
            "generated_at": cache.get("generated_at", "unknown"),
            "source_report": cache.get("source_report", "unknown"),
        }

        # Step 3: Cycle gate (skip if ignore_cycle)
        focus = None
        if not ignore_cycle:
            focus, gate = _check_cycle_gate(
                cycle_focus_path, cache_cycle_id,
                premium_status, cache_meta,
            )
            if gate is not None:
                span.set_attribute("status", "gate")
                span.set_attribute("gate_state", gate.get("state", ""))
                return gate

        # Step 4: Collect targets
        targets, not_in_cache = _collect_targets(cache, focus, ignore_cycle)

        # Step 5: Apply filters (override mode honors all filters)
        targets = _apply_filters(targets, filters)

        # Step 6: Sort
        targets = _sort_results(targets, sort_by)

        # Step 7: Enrich with confidence
        _enrich_with_confidence(targets, ledger_path, cache_path)

        # Step 8: Build response
        result = _build_response(
            targets, cache, focus, ignore_cycle, not_in_cache,
        )

        span.set_attribute("status", result["status"])
        span.set_attribute("target_count", result["target_count"])
        return result


# ─── CLI ─────────────────────────────────────────────────────────────


def _parse_cli_filters(args) -> tuple[dict, str | None]:
    """Extract filter dict and sort_by from parsed CLI args.

    Returns (filters_dict, sort_by). Filters dict may be empty.
    """
    filters: dict = {}
    if args.brand:
        filters["brand"] = args.brand
    if args.signal:
        filters["signal"] = args.signal
    if args.budget is not None:
        filters["budget"] = args.budget
    if args.format:
        filters["format"] = args.format
    return filters, args.sort


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Query Grailzee active hunting targets"
    )
    parser.add_argument("--cache", default=None, help="Path to analysis_cache.json")
    parser.add_argument("--ledger", default=None, help="Path to trade_ledger.csv")
    parser.add_argument("--cycle-focus", default=None, help="Path to cycle_focus.json")
    parser.add_argument("--ignore-cycle", action="store_true", default=False,
                        help="Bypass cycle gate; return full universe")
    parser.add_argument("--brand", default=None, help="Filter by brand (case-insensitive)")
    parser.add_argument("--signal", default=None,
                        help="Filter by signal: Strong, Normal, Reserve, Careful, Pass")
    parser.add_argument("--budget", type=float, default=None,
                        help="Only targets with max_buy at or below this amount")
    parser.add_argument("--format", default=None, dest="format",
                        help="Filter by format: NR or Reserve")
    parser.add_argument("--sort", default=None, dest="sort",
                        help="Sort field: momentum (default), volume, signal, max_buy")
    args = parser.parse_args()

    filters, sort_by = _parse_cli_filters(args)

    result = query_targets(
        cache_path=args.cache,
        ledger_path=args.ledger,
        cycle_focus_path=getattr(args, "cycle_focus", None),
        ignore_cycle=args.ignore_cycle,
        filters=filters or None,
        sort_by=sort_by,
    )
    print(json.dumps(result, indent=2, default=str))
