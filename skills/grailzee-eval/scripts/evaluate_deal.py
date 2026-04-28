"""Single deal evaluation for Grailzee v3 (Step 1 / 2026-04-26).

Reads the v3 bucket cache, narrows to a single bucket via 0-3 optional
keying axes (dial_numerals, auction_type, dial_color), applies the
analyzer_config premium scalar uniformly, and returns a yes/no decision
with math visible. Cycle plan context is reported alongside but does not
gate the decision (architecture lock §6: math gates).

The on-demand CSV fallback that lived in v2 is gone: v3 cache is the
source of truth for evaluable references; cache miss returns
match_resolution: reference_not_found with decision: no.

Usage (CLI):
    python3 evaluate_deal.py <brand> <reference> <listing_price>
        [--dial-numerals X] [--auction-type X] [--dial-color X]
        [--cache PATH] [--cycle-focus PATH]

Output: JSON to stdout with shape:
    {
      "decision": "yes" | "no",
      "reference": str,
      "bucket": {dial_numerals, auction_type, dial_color, named_special} | null,
      "math": {listing_price, premium_scalar, adjusted_price, max_buy, margin_pct, headroom_pct} | null,
      "cycle_context": {on_plan: bool, target_match: dict | null},
      "match_resolution": "single_bucket | ambiguous | no_match | override_match | reference_not_found | error",
      "candidates": [bucket, ...]    # only on ambiguous
      "error": str                   # only when match_resolution == error
    }
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import (
    CACHE_PATH,
    CACHE_SCHEMA_VERSION,
    CYCLE_FOCUS_PATH,
    NR_FIXED,
    RES_FIXED,
    get_tracer,
    load_analyzer_config,
    match_reference,
    normalize_ref,
    strip_ref,
)

tracer = get_tracer(__name__)


# ─── Plugin input contract ────────────────────────────────────────────


class _Input(BaseModel):
    """Pydantic model for the registered JSON Schema (§1.2).

    Validates the six schema fields. extra='forbid' ensures unknown fields
    (fields not in the registered schema) are rejected as bad_input, preventing
    silent drift between the plugin's JSON Schema and the Python contract.
    Test hooks (cache_path, cycle_focus_path) are extracted before _Input
    validation and never reach this model.
    """
    model_config = ConfigDict(extra="forbid")

    brand: str
    reference: str
    listing_price: str
    dial_numerals: Optional[Literal["Arabic", "Roman", "Stick", "No Numerals"]] = None
    auction_type: Optional[Literal["NR", "RES"]] = None
    dial_color: Optional[str] = None


# ─── CLI argument parsing ────────────────────────────────────────────


def _parse_price_arg(s: str) -> float:
    """Parse CLI price argument. Strips $ and commas. Raises ValueError on
    empty / non-numeric input."""
    cleaned = s.replace("$", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("empty price")
    return float(cleaned)


# ─── Cache loading ───────────────────────────────────────────────────


def _load_cache(cache_path: str) -> tuple[dict | None, dict | None]:
    """Load and validate analysis_cache.json.

    Returns (cache_dict, None) on success.
    Returns (None, error_response_dict) on missing file or stale schema.
    Error responses use match_resolution="error" with decision="no" so
    the LLM has a uniform shape to read.
    """
    if not os.path.exists(cache_path):
        return None, _error_response(
            "no_cache",
            f"No analysis cache found at {cache_path}.",
        )

    with open(cache_path, "r") as f:
        cache = json.load(f)

    schema_version = cache.get("schema_version", 0)
    if schema_version != CACHE_SCHEMA_VERSION:
        return None, _error_response(
            "stale_schema",
            f"Cache schema_version {schema_version} != required "
            f"{CACHE_SCHEMA_VERSION}.",
        )
    return cache, None


# ─── Reference lookup (preserved from v2) ────────────────────────────


def _find_reference(cache: dict, brand: str, reference: str) -> dict | None:
    """Multi-pass cache lookup for a reference; returns the per-ref dict.

    Pass 1: exact normalized match on cache keys.
    Pass 2: stripped (suffix/M-prefix-aware) match on cache keys.
    Pass 3: brand-filtered + match_reference substring matching.
    Pass 4: dj_configs section via match_reference.

    Returns None if no match in any pass.
    """
    refs = cache.get("references", {})
    norm_ref = normalize_ref(reference)
    stripped = strip_ref(reference)
    brand_upper = brand.strip().upper()

    for key, entry in refs.items():
        if normalize_ref(key) == norm_ref:
            return entry
    for key, entry in refs.items():
        if strip_ref(key) == stripped:
            return entry
    for key, entry in refs.items():
        if entry.get("brand", "").upper() != brand_upper:
            continue
        if match_reference(reference, key):
            return entry
    for entry in cache.get("dj_configs", {}).values():
        if match_reference(reference, entry.get("reference", "")):
            return entry
    return None


# ─── Bucket matcher ──────────────────────────────────────────────────


def _bucket_summary(bucket: dict) -> dict:
    """Compact bucket projection for `bucket` and `candidates` fields.

    Keying axes plus named_special metadata plus signal/volume so the LLM
    has enough to ask one clarifying question on ambiguous matches.
    """
    return {
        "dial_numerals": bucket.get("dial_numerals"),
        "auction_type": bucket.get("auction_type"),
        "dial_color": bucket.get("dial_color"),
        "named_special": bucket.get("named_special"),
        "signal": bucket.get("signal"),
        "volume": bucket.get("volume"),
    }


def _axis_match(bucket_value: str, query: str | None) -> bool:
    """Case-insensitive equality; None on the query side is a wildcard."""
    if query is None:
        return True
    return str(bucket_value).strip().lower() == query.strip().lower()


def _match_buckets(
    ref_entry: dict,
    dial_numerals: str | None = None,
    auction_type: str | None = None,
    dial_color: str | None = None,
) -> tuple[str, dict | None, list[dict]]:
    """Narrow the reference's buckets by 0-3 axes.

    Returns (resolution, picked_bucket, candidates):
      - ("single_bucket", bucket, []) when exactly one bucket survives.
      - ("ambiguous", None, [bucket_summary, ...]) when 2+ survive.
      - ("no_match", None, []) when axes filter all buckets out, or the
        reference has no buckets at all.

    Bucket field axes are case-preserved for dial_numerals/dial_color but
    lowercased for auction_type per analyze_buckets.score_bucket; the
    case-insensitive comparison handles both.
    """
    buckets = ref_entry.get("buckets", {})
    if not buckets:
        return "no_match", None, []

    survivors = [
        b for b in buckets.values()
        if _axis_match(b.get("dial_numerals", ""), dial_numerals)
        and _axis_match(b.get("auction_type", ""), auction_type)
        and _axis_match(b.get("dial_color", ""), dial_color)
    ]
    if not survivors:
        return "no_match", None, []
    if len(survivors) == 1:
        return "single_bucket", survivors[0], []
    return "ambiguous", None, [_bucket_summary(b) for b in survivors]


# ─── Cycle context ──────────────────────────────────────────────────


def _read_cycle_focus(cycle_focus_path: str | None) -> dict | None:
    """Read state/cycle_focus.json. Returns None if missing or unreadable."""
    path = cycle_focus_path or CYCLE_FOCUS_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _cycle_context(reference: str, focus: dict | None) -> dict:
    """Resolve on_plan boolean + matching target metadata.

    Match rule: any cycle_focus.targets entry whose `reference` field
    matches via match_reference (substring-tolerant) flags the deal as
    on_plan. The first matching target is surfaced.
    """
    if focus is None:
        return {"on_plan": False, "target_match": None}
    targets = focus.get("targets", []) or []
    for t in targets:
        if not isinstance(t, dict):
            continue
        if match_reference(reference, t.get("reference", "")):
            return {
                "on_plan": True,
                "target_match": {
                    "reference": t.get("reference"),
                    "brand": t.get("brand"),
                    "model": t.get("model"),
                    "cycle_reason": t.get("cycle_reason"),
                    "max_buy_override": t.get("max_buy_override"),
                },
            }
    return {"on_plan": False, "target_match": None}


# ─── Decision math ──────────────────────────────────────────────────


def _bucket_fees(bucket: dict) -> float:
    """Pick fee bracket from bucket.auction_type. RES → 199; else NR → 149.

    Bucket auction_type is lowercased ("nr" / "res") per
    analyze_buckets.score_bucket. Anything other than "res" routes to
    NR fees, matching the bot's default listing posture.
    """
    auction = str(bucket.get("auction_type", "")).strip().lower()
    return RES_FIXED if auction == "res" else NR_FIXED


def _decision_math(bucket: dict, listing_price: float) -> dict | None:
    """Compute decision math from bucket + listing_price.

    Returns None when the bucket has no median (signal=Low data); caller
    surfaces match_resolution=single_bucket with decision=no in that case.
    """
    median = bucket.get("median")
    if median is None:
        return None

    cfg = load_analyzer_config()
    premium_scalar = cfg["scoring"]["premium_scalar_fraction"]
    target_margin = cfg["margin"]["per_trade_target_margin_fraction"]
    fees = _bucket_fees(bucket)

    adjusted_price = median * (1 + premium_scalar)
    max_buy_unrounded = (adjusted_price - fees) / (1 + target_margin)
    # Floor to the next $10 below so a listing at exactly max_buy clears
    # the 5% margin floor. Architecture lock §1: floor is non-negotiable.
    # Nearest-rounding could let a deal land 1-4 dollars below the floor
    # and still return yes; floor-rounding makes max_buy safe at every
    # dollar at or below the value.
    max_buy = math.floor(max_buy_unrounded / 10) * 10
    margin_dollars = adjusted_price - listing_price - fees
    margin_pct = (margin_dollars / listing_price * 100) if listing_price > 0 else 0.0

    return {
        "listing_price": listing_price,
        "premium_scalar": premium_scalar,
        "adjusted_price": round(adjusted_price, 2),
        "max_buy": max_buy,
        "margin_pct": round(margin_pct, 2),
        "headroom_pct": None,
    }


def _override_math(override_price: float, listing_price: float) -> dict:
    """Compute buy decision from operator override price.

    Pure function. No premium scalar, no median, no fees — the operator's
    override already encodes their strategy and pricing judgment.

    Returns a dict with keys:
        listing_price (float), premium_scalar (None), adjusted_price (None),
        max_buy (float, == override_price), margin_pct (None),
        headroom_pct (float, signed).

    headroom_pct = ((override_price - listing_price) / override_price) * 100.
    Positive when listing is below the ceiling; negative when above.

    Raises ValueError if override_price <= 0.
    """
    if override_price <= 0:
        raise ValueError(
            f"override_price must be positive; got {override_price!r}"
        )
    headroom_pct = ((override_price - listing_price) / override_price) * 100
    return {
        "listing_price": listing_price,
        "premium_scalar": None,
        "adjusted_price": None,
        "max_buy": override_price,
        "margin_pct": None,
        "headroom_pct": round(headroom_pct, 2),
    }


def _decide_yes_no(bucket: dict, math: dict | None) -> str:
    """yes/no rule. Pass signal or no math → no. Math clears (price <=
    max_buy) → yes. Otherwise no."""
    if math is None:
        return "no"
    if bucket.get("signal") == "Pass":
        return "no"
    return "yes" if math["listing_price"] <= math["max_buy"] else "no"


# ─── Label helpers ───────────────────────────────────────────────────


_MATCH_RESOLUTION_LABELS: dict[str, str] = {
    "single_bucket": "Matched single bucket",
    "ambiguous": "Multiple buckets possible. Clarify dial color, auction type, or numerals.",
    "no_match": "No bucket match for this listing",
    "override_match": "On plan; override price applied",
    "reference_not_found": "Reference not in cache",
    "error": "Lookup error",
}


def _match_resolution_label(resolution: str) -> str:
    return _MATCH_RESOLUTION_LABELS.get(resolution, resolution)


def _plan_status_label(on_plan: bool | None) -> str | None:
    if on_plan is None:
        return None
    return "On cycle plan" if on_plan else "Off cycle plan"


def _bucket_label(bucket: dict | None) -> str | None:
    if bucket is None:
        return None
    dial_color = str(bucket.get("dial_color", "")).strip()
    dial_numerals = str(bucket.get("dial_numerals", "")).strip()
    auction_type = str(bucket.get("auction_type", "")).strip()
    color_part = (
        "Dial color unspecified"
        if dial_color.lower() == "unknown"
        else f"{dial_color} dial"
    )
    return f"{color_part}, {dial_numerals} numerals, {auction_type}"


def _candidate_bucket_labels(candidates: list[dict]) -> list[str]:
    labels = []
    for c in candidates:
        lb = _bucket_label(c)
        if lb is not None:
            labels.append(lb)
    return labels


# ─── Response builders ──────────────────────────────────────────────


def _error_response(error: str, message: str) -> dict:
    return {
        "decision": "no",
        "reference": "",
        "bucket": None,
        "math": None,
        "cycle_context": {"on_plan": None, "target_match": None},
        "match_resolution": "error",
        "match_resolution_label": "Lookup error",
        "plan_status_label": "Lookup error",
        "bucket_label": None,
        "error": error,
        "message": message,
    }


def _build_response(
    *,
    reference: str,
    match_resolution: str,
    decision: str,
    bucket: dict | None,
    math: dict | None,
    cycle_context: dict,
    candidates: list[dict] | None = None,
) -> dict:
    out: dict = {
        "decision": decision,
        "reference": reference,
        "bucket": _bucket_summary(bucket) if bucket else None,
        "math": math,
        "cycle_context": cycle_context,
        "match_resolution": match_resolution,
        "match_resolution_label": _match_resolution_label(match_resolution),
        "plan_status_label": _plan_status_label(cycle_context.get("on_plan")),
        "bucket_label": _bucket_label(bucket) if match_resolution == "single_bucket" else None,
    }
    if candidates:
        out["candidates"] = candidates
        out["candidate_bucket_labels"] = _candidate_bucket_labels(candidates)
    return out


# ─── Public entry point ─────────────────────────────────────────────


def evaluate(
    brand: str,
    reference: str,
    listing_price: float,
    *,
    dial_numerals: str | None = None,
    auction_type: str | None = None,
    dial_color: str | None = None,
    cache_path: str | None = None,
    cycle_focus_path: str | None = None,
) -> dict:
    """Evaluate one deal. Returns the v3 / Step 1 response shape."""
    cache_path = cache_path or CACHE_PATH

    with tracer.start_as_current_span("evaluate_deal") as span:
        span.set_attribute("brand", brand)
        span.set_attribute("reference", reference)
        span.set_attribute("listing_price", listing_price)

        cache, error = _load_cache(cache_path)
        if error is not None:
            span.set_attribute("match_resolution", "error")
            return error

        focus = _read_cycle_focus(cycle_focus_path)
        cycle_context = _cycle_context(reference, focus)
        span.set_attribute("on_plan", cycle_context["on_plan"])

        ref_entry = _find_reference(cache, brand, reference)
        if ref_entry is None:
            span.set_attribute("match_resolution", "reference_not_found")
            span.set_attribute("decision", "no")
            return _build_response(
                reference=reference,
                match_resolution="reference_not_found",
                decision="no",
                bucket=None,
                math=None,
                cycle_context=cycle_context,
            )

        resolution, bucket, candidates = _match_buckets(
            ref_entry, dial_numerals, auction_type, dial_color,
        )
        span.set_attribute("match_resolution", resolution)

        if resolution != "single_bucket":
            span.set_attribute("decision", "no")
            return _build_response(
                reference=reference,
                match_resolution=resolution,
                decision="no",
                bucket=None,
                math=None,
                cycle_context=cycle_context,
                candidates=candidates,
            )

        # Single-bucket path: math + decision.
        bucket_key = (
            f"{bucket.get('dial_numerals', '').lower()}"
            f"|{bucket.get('auction_type', '').lower()}"
            f"|{bucket.get('dial_color', '').lower()}"
        )
        span.set_attribute("bucket_key", bucket_key)

        deal_math = _decision_math(bucket, listing_price)
        decision = _decide_yes_no(bucket, deal_math)
        span.set_attribute("decision", decision)

        return _build_response(
            reference=reference,
            match_resolution="single_bucket",
            decision=decision,
            bucket=bucket,
            math=deal_math,
            cycle_context=cycle_context,
        )


# ─── Entry points ────────────────────────────────────────────────────


def _run_from_dict(data: dict) -> int:
    """JSON dispatch. Validates with _Input, calls evaluate(), emits result.

    Test hooks (cache_path, cycle_focus_path) are extracted before _Input
    validation so they never reach the strict model. All error paths emit
    _error_response() (full §1.3 shape) and return 0 per §4.3.
    """
    cache_path = data.get("cache_path")
    cycle_focus_path = data.get("cycle_focus_path")
    schema_data = {
        k: v for k, v in data.items()
        if k not in ("cache_path", "cycle_focus_path")
    }

    try:
        inp = _Input(**schema_data)
    except ValidationError as exc:
        errors = exc.errors()
        if any(e["type"] == "missing" for e in errors):
            missing = ", ".join(
                str(e["loc"][-1]) for e in errors if e["type"] == "missing"
            )
            code, msg = "missing_arg", f"Missing required field: {missing}"
        else:
            code, msg = "bad_input", str(exc)
        print(json.dumps(_error_response(code, msg)))
        return 0

    try:
        price = _parse_price_arg(inp.listing_price)
    except ValueError as exc:
        print(json.dumps(_error_response("bad_price", f"Cannot parse price: {exc}")))
        return 0

    result = evaluate(
        inp.brand, inp.reference, price,
        dial_numerals=inp.dial_numerals,
        auction_type=inp.auction_type,
        dial_color=inp.dial_color,
        cache_path=cache_path,
        cycle_focus_path=cycle_focus_path,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def _run_from_argv() -> int:
    """Plugin spawnArgv entry point: reads sys.argv[1] as JSON string."""
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps(_error_response("bad_input", f"Invalid JSON in argv[1]: {exc}")))
        return 0
    return _run_from_dict(payload)


def _run_legacy() -> int:
    """Argparse entry point for direct CLI testing (python3 evaluate_deal.py brand ref price)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate a single deal against the v3 bucket cache.",
    )
    parser.add_argument("brand", help="Watch brand (e.g. Tudor)")
    parser.add_argument("reference", help="Reference number (e.g. 79830RB)")
    parser.add_argument("listing_price", help="Listing price (e.g. 2750)")
    parser.add_argument("--dial-numerals", default=None,
                        help="Optional keying axis (e.g. Arabic, Roman)")
    parser.add_argument("--auction-type", default=None,
                        help="Optional keying axis (NR, RES)")
    parser.add_argument("--dial-color", default=None,
                        help="Optional keying axis (e.g. Black, Blue)")
    parser.add_argument("--cache", default=None,
                        help="Path to analysis_cache.json (defaults to live)")
    parser.add_argument("--cycle-focus", default=None,
                        help="Path to cycle_focus.json (defaults to live)")
    args = parser.parse_args()

    try:
        price = _parse_price_arg(args.listing_price)
    except ValueError:
        print(json.dumps({
            "decision": "no",
            "reference": args.reference,
            "match_resolution": "error",
            "error": "bad_price",
            "message": f"Cannot parse price: {args.listing_price!r}",
        }))
        return 1

    result = evaluate(
        args.brand, args.reference, price,
        dial_numerals=args.dial_numerals,
        auction_type=args.auction_type,
        dial_color=args.dial_color,
        cache_path=args.cache,
        cycle_focus_path=args.cycle_focus,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    # argv[1] starts with "{" → JSON payload from spawnArgv plugin dispatch.
    if len(sys.argv) > 1 and sys.argv[1].startswith("{"):
        sys.exit(_run_from_argv())
    # No extra argv → stdin path (legacy spawnStdin compat; also used in tests).
    if len(sys.argv) == 1:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(json.dumps(_error_response("bad_input", f"Invalid JSON on stdin: {exc}")))
            sys.exit(0)
        sys.exit(_run_from_dict(payload))
    # argv[1] present but not JSON → argparse path (direct CLI testing).
    sys.exit(_run_legacy())
