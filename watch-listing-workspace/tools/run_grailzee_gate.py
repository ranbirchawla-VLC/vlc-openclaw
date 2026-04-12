#!/usr/bin/env python3
"""
run_grailzee_gate.py — Grailzee eligibility gate.

Reads _draft.json at step 3, calls evaluate_deal.py as a subprocess,
interprets the result, and writes the gate decision back to _draft.json.
Advances pipeline to step 3.5.

Usage:
  python3 run_grailzee_gate.py /path/to/listing_folder
  python3 run_grailzee_gate.py /path/to/listing_folder --dry-run

Inputs consumed from _draft.json:
  inputs.brand            — required
  inputs.reference        — required
  inputs.retail_net       — required (used as purchase_price for evaluation)
  inputs.grailzee_format  — if absent or "skip", gate is bypassed

Outputs written to _draft.json:
  approved.grailzee_gate  — gate decision (status + supporting data)
  pricing.grailzee        — updated format and reserve_price (proceed only)
  step                    — set to 3.5

Gate statuses:
  proceed     — deal approved; pricing.grailzee updated with evaluator recommendation
  adjust      — deal not approved; rationale included; user should review before listing
  manual_check — evaluator unavailable or reference not in cache; pipeline continues
  skip        — grailzee_format is absent or "skip"; gate not run
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import NoReturn


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR   = os.path.dirname(os.path.abspath(__file__))
WORKSPACE   = os.path.dirname(TOOLS_DIR)
REPO_ROOT   = os.path.dirname(WORKSPACE)
SCHEMA_PATH = os.path.join(WORKSPACE, "schema", "draft_schema.json")
DRAFT_SAVE  = os.path.join(TOOLS_DIR, "draft_save.py")
EVAL_SCRIPT = os.path.join(
    REPO_ROOT, "skills", "grailzee-eval", "scripts", "evaluate_deal.py"
)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def fail(msg: str) -> NoReturn:
    """Print error JSON to stdout and exit non-zero."""
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Draft I/O
# ---------------------------------------------------------------------------

def load_draft(folder: str) -> dict:
    """Load and return _draft.json. Fails on missing or corrupt file."""
    path = os.path.join(folder, "_draft.json")
    if not os.path.exists(path):
        fail(f"No _draft.json found in: {folder}")
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            fail(f"_draft.json is not valid JSON: {e}")


def validate_draft(draft: dict) -> None:
    """Validate draft against schema/draft_schema.json. Warns if schema absent."""
    if not os.path.exists(SCHEMA_PATH):
        print("WARNING: Schema not found, skipping validation.", file=sys.stderr)
        return
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=draft, schema=schema)
    except ImportError:
        print("WARNING: jsonschema not installed, skipping schema validation.", file=sys.stderr)
    except jsonschema.ValidationError as e:
        fail(f"_draft.json schema validation failed: {e.message}")


def save_gate(folder: str, patch: dict) -> str:
    """Write patch to _draft.json via draft_save.py. Returns saved path."""
    patch_str = json.dumps(patch)
    result = subprocess.run(
        [sys.executable, DRAFT_SAVE, folder, patch_str],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"draft_save.py exited {result.returncode}: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(f"draft_save.py returned non-JSON: {result.stdout!r}")
    if not data.get("ok"):
        fail(f"draft_save.py failed: {data.get('error', 'unknown error')}")
    return data["path"]


# ---------------------------------------------------------------------------
# Evaluator subprocess
# ---------------------------------------------------------------------------

def call_evaluator(
    brand: str,
    reference: str,
    retail_net: float,
    eval_script: str,
    cache_path: str | None = None,
) -> dict:
    """
    Call evaluate_deal.py and return its parsed JSON.

    On timeout, crash, or non-JSON output, returns a synthetic error dict
    with status="error", error="evaluator_failed" so the caller can treat
    it as a manual_check without special-casing.
    """
    cmd = [sys.executable, eval_script, brand, reference, str(retail_net)]
    if cache_path:
        cmd += ["--cache", cache_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": "evaluator_failed",
            "message": "evaluate_deal.py timed out after 30s",
        }
    except OSError as e:
        return {
            "status": "error",
            "error": "evaluator_failed",
            "message": f"Could not run evaluate_deal.py: {e}",
        }

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        snippet = result.stdout[:200] if result.stdout else "<empty>"
        return {
            "status": "error",
            "error": "evaluator_failed",
            "message": f"Non-JSON output (exit {result.returncode}): {snippet!r}",
        }


# ---------------------------------------------------------------------------
# Outcome interpretation
# ---------------------------------------------------------------------------

def interpret_ok(data: dict) -> dict:
    """
    Map a status=ok evaluate_deal.py response to a gate decision dict.

    Returns dict with: status, grailzee_format, reserve_price, metrics, rationale.
    Adds recommendation key on adjust.
    """
    grailzee     = data.get("grailzee", "")
    fmt          = data.get("format", "")
    reserve_price = data.get("reserve_price")
    metrics      = data.get("metrics", {})
    rationale    = data.get("rationale", "")

    match (grailzee, fmt):
        case ("YES", "NR"):
            return {
                "status":         "proceed",
                "grailzee_format": "NR",
                "reserve_price":  None,
                "metrics":        metrics,
                "rationale":      rationale,
            }
        case ("YES", "Reserve") | ("MAYBE", "Reserve"):
            return {
                "status":         "proceed",
                "grailzee_format": "Reserve",
                "reserve_price":  reserve_price,
                "metrics":        metrics,
                "rationale":      rationale,
            }
        case _:
            # NO (any format), MAYBE+NR, or any unrecognised combination
            return {
                "status":          "adjust",
                "grailzee_format":  fmt,
                "reserve_price":   None,
                "metrics":         metrics,
                "rationale":       rationale,
                "recommendation":  (
                    "Review Grailzee eligibility before listing. "
                    "Consider removing Grailzee or repricing."
                ),
            }


def gate_from_evaluator(data: dict) -> dict:
    """
    Convert any evaluate_deal.py response dict to a gate decision.

    Handles all status values: ok, not_found, error, evaluator_failed.
    """
    match data.get("status"):
        case "ok":
            return interpret_ok(data)
        case "not_found":
            return {
                "status":   "manual_check",
                "reason":   "reference not in Grailzee cache or raw report",
                "metrics":  {},
                "rationale": data.get("rationale", ""),
            }
        case _:
            # "error", "evaluator_failed", or anything unexpected
            return {
                "status":   "manual_check",
                "reason":   data.get("error", "unknown"),
                "metrics":  {},
                "rationale": data.get("message", ""),
            }


# ---------------------------------------------------------------------------
# Summary formatter
# ---------------------------------------------------------------------------

def format_summary(brand: str, reference: str, gate: dict) -> str:
    """Return a human-readable gate summary suitable for Telegram/stdout."""
    header = f"GRAILZEE GATE — {brand} {reference}".strip()
    parts  = [header, "━" * len(header)]

    match gate["status"]:
        case "proceed":
            fmt = gate.get("grailzee_format", "")
            parts.append(f"Status:   PROCEED — {fmt}")
            m = gate.get("metrics", {})
            if m.get("median") is not None:
                parts.append(f"Median:   ${m['median']:,.0f}")
            if m.get("max_buy") is not None:
                parts.append(f"Max Buy:  ${m['max_buy']:,.0f}")
            if m.get("signal"):
                parts.append(f"Signal:   {m['signal']}")
            if m.get("margin_pct") is not None:
                parts.append(f"Margin:   {m['margin_pct']:.1f}%")
            if gate.get("reserve_price") is not None:
                parts.append(f"Reserve:  ${gate['reserve_price']:,.0f}")
            parts.append("")
            parts.append(gate.get("rationale", ""))

        case "adjust":
            parts.append("Status:   ADJUST — deal not approved for Grailzee")
            parts.append("")
            parts.append(gate.get("rationale", ""))
            if gate.get("recommendation"):
                parts.append("")
                parts.append(f"→ {gate['recommendation']}")

        case "manual_check":
            parts.append("Status:   MANUAL CHECK — evaluator unavailable")
            parts.append(f"Reason:   {gate.get('reason', 'unknown')}")

        case "skip":
            parts.append("Status:   SKIP — Grailzee not configured for this listing")

        case _ as s:
            parts.append(f"Status:   {s}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main gate logic
# ---------------------------------------------------------------------------

def run_gate(
    folder: str,
    dry_run: bool = False,
    eval_script: str | None = None,
    cache_path: str | None = None,
) -> dict:
    """
    Run the Grailzee gate for the listing in folder.

    Args:
        folder:      Path to listing folder containing _draft.json.
        dry_run:     If True, print summary but do not write _draft.json.
        eval_script: Path to evaluate_deal.py. Defaults to EVAL_SCRIPT constant.
        cache_path:  Optional --cache override passed to evaluate_deal.py.

    Returns:
        Gate decision dict. Always returns; never raises on evaluator failures.
    """
    _eval_script = eval_script or EVAL_SCRIPT

    draft = load_draft(folder)
    validate_draft(draft)

    step = draft.get("step")
    if step != 3:
        fail(f"Expected step 3, got step {step}. Run the canonical descriptions skill first.")

    inputs        = draft.get("inputs", {})
    brand         = inputs.get("brand", "")
    reference     = inputs.get("reference", "")
    retail_net    = inputs.get("retail_net")
    grailzee_fmt  = inputs.get("grailzee_format")

    if not brand:
        fail("inputs.brand is required")
    if not reference:
        fail("inputs.reference is required")
    if retail_net is None:
        fail("inputs.retail_net is required — run step 2 (pricing) first")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------
    # Skip path: grailzee_format absent or "skip"
    # Unknown values are caught by schema validation; if we reach here with
    # an unrecognised value, fail explicitly rather than silently skipping.
    # ------------------------------------------------------------------
    match grailzee_fmt:
        case None | "skip":
            gate = {"status": "skip"}
            print(format_summary(brand, reference, gate))
            if not dry_run:
                save_gate(folder, {
                    "step":      3.5,
                    "timestamp": timestamp,
                    "approved":  {
                        "grailzee_gate": {
                            "status":    "skip",
                            "timestamp": timestamp,
                        }
                    },
                })
            return gate
        case "NR" | "Reserve":
            pass  # proceed to evaluation below
        case _:
            fail(
                f"Unknown grailzee_format: {grailzee_fmt!r} — "
                f"must be NR, Reserve, or skip"
            )

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    eval_data = call_evaluator(brand, reference, retail_net, _eval_script, cache_path)
    gate      = gate_from_evaluator(eval_data)

    print(format_summary(brand, reference, gate))

    if dry_run:
        print("\n[dry-run: _draft.json not modified]")
        return gate

    # ------------------------------------------------------------------
    # Build patch
    # ------------------------------------------------------------------
    approved_gate: dict = {
        "status":    gate["status"],
        "timestamp": timestamp,
    }

    m = gate.get("metrics", {})
    if m.get("median") is not None:
        approved_gate["median"] = m["median"]
    if m.get("signal"):
        approved_gate["signal"] = m["signal"]
    if gate.get("grailzee_format"):
        approved_gate["grailzee_format"] = gate["grailzee_format"]
    if gate.get("rationale"):
        approved_gate["rationale"] = gate["rationale"]
    if gate.get("recommendation"):
        approved_gate["recommendation"] = gate["recommendation"]
    if gate.get("reason"):
        approved_gate["reason"] = gate["reason"]

    patch: dict = {
        "step":      3.5,
        "timestamp": timestamp,
        "approved":  {"grailzee_gate": approved_gate},
    }

    # On proceed, update pricing.grailzee with the evaluator's recommendation.
    # This may change format (e.g. NR → Reserve) and sets reserve_price.
    match gate["status"]:
        case "proceed":
            patch["pricing"] = {
                "grailzee": {
                    "format":        gate["grailzee_format"],
                    "reserve_price": gate.get("reserve_price"),
                }
            }
        case "adjust" | "manual_check":
            pass  # pricing.grailzee unchanged

    save_gate(folder, patch)
    return gate


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        fail("Usage: run_grailzee_gate.py /path/to/listing_folder [--dry-run]")

    folder  = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not os.path.isdir(folder):
        fail(f"Not a directory: {folder}")

    run_gate(folder, dry_run=dry_run)


if __name__ == "__main__":
    main()
