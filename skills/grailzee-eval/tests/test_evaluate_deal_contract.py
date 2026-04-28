"""evaluate_deal contract tests for Shape K 1c / 1c.5.

Tests the script's API contract per Grailzee_Plugin_API_Spec_v1.md §1.

Two invocation helpers:
- _call_via_stdin: stdin JSON dispatch (len(sys.argv)==1 path). Preserved
  for backward compat; used by the original 1c tests.
- _call_via_argv: argv[1] JSON dispatch (spawnArgv plugin path). The primary
  plugin path after 1c.5; all tests in TestArgvDispatch use this.

Exit code invariant per §4.3: all shaped business errors exit 0. Non-zero
exit is reserved for framework-level failure (import error, OOM, etc.).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.grailzee_common import CACHE_SCHEMA_VERSION
from scripts.evaluate_deal import _run_from_argv

_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py"
)


# ─── Fixture helpers ─────────────────────────────────────────────────


def _make_bucket(
    *,
    dial_numerals: str = "Arabic",
    auction_type: str = "nr",
    dial_color: str = "Black",
    named_special: str | None = None,
    signal: str = "Strong",
    median: float = 3200.0,
    max_buy_nr: float = 2910.0,
    max_buy_res: float = 2860.0,
    risk_nr: float = 8.5,
    volume: int = 12,
    st_pct: float = 0.78,
) -> dict:
    return {
        "dial_numerals": dial_numerals,
        "auction_type": auction_type,
        "dial_color": dial_color,
        "named_special": named_special,
        "signal": signal,
        "median": median,
        "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res,
        "risk_nr": risk_nr,
        "volume": volume,
        "st_pct": st_pct,
        "condition_mix": '{"very good":0.5,"like new":0.5}',
        "capital_required_nr": None,
        "capital_required_res": None,
        "expected_net_at_median_nr": None,
        "expected_net_at_median_res": None,
    }


def _make_v3_cache(
    refs: dict | None = None,
    *,
    cycle_id: str = "cycle_2026-15",
) -> dict:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": "2026-04-15T10:30:00",
        "source_report": "grailzee_2026-04-12.csv",
        "cycle_id": cycle_id,
        "premium_status": {
            "avg_premium": 0,
            "trade_count": 0,
            "threshold_met": False,
            "adjustment": 0,
            "trades_to_threshold": 10,
        },
        "references": refs or {},
        "dj_configs": {},
    }


def _make_ref(
    *,
    brand: str = "Tudor",
    model: str = "Black Bay GMT",
    reference: str = "79830RB",
    buckets: list[dict] | None = None,
) -> dict:
    bucket_dict: dict = {}
    for b in (buckets or []):
        key = (
            f"{b['dial_numerals'].lower()}"
            f"|{b['auction_type'].lower()}"
            f"|{b['dial_color'].lower()}"
        )
        bucket_dict[key] = b
    return {
        "brand": brand,
        "model": model,
        "reference": reference,
        "named": True,
        "trend_signal": None,
        "trend_median_change": None,
        "trend_median_pct": None,
        "momentum": None,
        "confidence": None,
        "buckets": bucket_dict,
    }


def _call_via_stdin(
    payload: dict,
    cache_path: str,
    cycle_focus_path: str | None = None,
) -> tuple[int, dict]:
    """Invoke via stdin JSON (len(sys.argv)==1 path; preserved for compat)."""
    full_payload = {**payload, "cache_path": cache_path}
    if cycle_focus_path:
        full_payload["cycle_focus_path"] = cycle_focus_path
    proc = subprocess.run(
        [sys.executable, _SCRIPT],
        input=json.dumps(full_payload),
        capture_output=True,
        text=True,
        timeout=15,
    )
    result = json.loads(proc.stdout)
    return proc.returncode, result


def _call_via_argv(
    payload: dict,
    cache_path: str,
    cycle_focus_path: str | None = None,
) -> tuple[int, dict]:
    """Invoke via argv[1] JSON (spawnArgv plugin path)."""
    full_payload = {**payload, "cache_path": cache_path}
    if cycle_focus_path:
        full_payload["cycle_focus_path"] = cycle_focus_path
    proc = subprocess.run(
        [sys.executable, _SCRIPT, json.dumps(full_payload)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    result = json.loads(proc.stdout)
    return proc.returncode, result


def _write_cache(tmp_path, cache_dict) -> str:
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(cache_dict, indent=2))
    return str(p)


# ─── Happy path ───────────────────────────────────────────────────────


class TestHappyPath:
    def test_yes_decision_full_envelope(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["decision"] in ("yes", "no")
        assert result["match_resolution"] == "single_bucket"
        assert "match_resolution_label" in result
        assert "plan_status_label" in result
        assert "bucket_label" in result
        assert result["bucket"] is not None
        assert "signal" in result["bucket"]
        assert "volume" in result["bucket"]
        assert result["math"] is not None
        math = result["math"]
        assert "listing_price" in math
        assert "premium_scalar" in math
        assert math["premium_scalar"] < 1.0, (
            "premium_scalar must be a fraction (e.g. 0.10), not a percentage (10)"
        )
        assert "adjusted_price" in math
        assert "max_buy" in math
        assert "margin_pct" in math
        assert math["headroom_pct"] is None, (
            "headroom_pct must be null on single_bucket path"
        )
        assert "cycle_context" in result
        cc = result["cycle_context"]
        assert "on_plan" in cc
        assert "target_match" in cc

    def test_strong_yes_math_correct(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["decision"] == "yes"
        assert result["match_resolution"] == "single_bucket"

    def test_no_decision_above_max_buy(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "3500"},
            cache_path,
        )
        assert rc == 0
        assert result["decision"] == "no"
        assert result["match_resolution"] == "single_bucket"

    def test_optional_axes_narrow_bucket(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[
                _make_bucket(dial_color="Black"),
                _make_bucket(dial_color="Blue"),
            ])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor",
                "reference": "79830RB",
                "listing_price": "2000",
                "dial_color": "Blue",
            },
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "single_bucket"
        assert result["bucket"]["dial_color"] == "Blue"

    def test_ambiguous_returns_candidates_and_labels(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[
                _make_bucket(dial_color="Black"),
                _make_bucket(dial_color="Blue"),
            ])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "ambiguous"
        assert "candidates" in result
        assert isinstance(result["candidates"], list)
        assert len(result["candidates"]) == 2
        assert "candidate_bucket_labels" in result
        assert len(result["candidate_bucket_labels"]) == len(result["candidates"])

    def test_reference_not_found_returns_shaped_no(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "DOESNOTEXIST", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["decision"] == "no"
        assert result["match_resolution"] == "reference_not_found"

    def test_no_match_returns_full_envelope(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[
                _make_bucket(dial_color="Black"),
                _make_bucket(dial_color="Blue"),
            ])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor",
                "reference": "79830RB",
                "listing_price": "2000",
                "dial_color": "Purple",
            },
            cache_path,
        )
        assert rc == 0
        assert result["decision"] == "no"
        assert result["match_resolution"] == "no_match"
        assert "match_resolution_label" in result
        assert "plan_status_label" in result
        assert result["bucket"] is None
        assert result["math"] is None

    def test_price_formats_dollar_comma(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "$2,000"},
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "single_bucket"


# ─── Error paths ──────────────────────────────────────────────────────


class TestErrorPaths:
    def _assert_error_envelope(self, rc: int, result: dict, expected_error: str) -> None:
        """Assert §1.3 failure shape: exit 0, full envelope, correct code."""
        assert rc == 0, f"shaped error must exit 0, got {rc}"
        assert result["decision"] == "no"
        assert result["match_resolution"] == "error"
        assert result["match_resolution_label"] == "Lookup error"
        assert result["error"] == expected_error
        assert "message" in result
        assert "plan_status_label" in result, "error envelope must include plan_status_label"
        assert "bucket_label" in result, "error envelope must include bucket_label"

    def test_no_cache_error(self, tmp_path):
        missing_cache = str(tmp_path / "nonexistent.json")
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            missing_cache,
        )
        self._assert_error_envelope(rc, result, "no_cache")

    def test_stale_schema_error(self, tmp_path):
        stale = _make_v3_cache()
        stale["schema_version"] = 9999
        cache_path = _write_cache(tmp_path, stale)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        self._assert_error_envelope(rc, result, "stale_schema")

    def test_missing_arg_brand(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {"reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        self._assert_error_envelope(rc, result, "missing_arg")

    def test_missing_arg_reference(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "listing_price": "2000"},
            cache_path,
        )
        self._assert_error_envelope(rc, result, "missing_arg")

    def test_bad_price_error(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "notanumber"},
            cache_path,
        )
        self._assert_error_envelope(rc, result, "bad_price")

    def test_bad_input_invalid_json_stdin(self):
        proc = subprocess.run(
            [sys.executable, _SCRIPT],
            input="this is not json",
            capture_output=True,
            text=True,
            timeout=15,
        )
        result = json.loads(proc.stdout)
        assert proc.returncode == 0, f"bad_input must exit 0, got {proc.returncode}"
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"
        assert result.get("match_resolution_label") == "Lookup error"


# ─── Schema parity ────────────────────────────────────────────────────


class TestSchemaParity:
    """Verify _Input accepts the 6 registered JSON Schema fields and rejects unknowns."""

    def test_all_three_required_fields_accepted(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket()])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert result["match_resolution"] != "error", (
            "All three required fields must produce a non-error response"
        )

    def test_dial_numerals_optional_field_accepted(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(dial_numerals="Arabic")])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor", "reference": "79830RB", "listing_price": "2000",
                "dial_numerals": "Arabic",
            },
            cache_path,
        )
        assert result["match_resolution"] != "error"

    def test_auction_type_optional_field_accepted(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(auction_type="nr")])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor", "reference": "79830RB", "listing_price": "2000",
                "auction_type": "NR",
            },
            cache_path,
        )
        assert result["match_resolution"] != "error"

    def test_dial_color_optional_field_accepted(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(dial_color="Black")])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor", "reference": "79830RB", "listing_price": "2000",
                "dial_color": "Black",
            },
            cache_path,
        )
        assert result["match_resolution"] != "error"

    def test_all_six_fields_together(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[
                _make_bucket(dial_numerals="Arabic", auction_type="nr", dial_color="Black")
            ])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor",
                "reference": "79830RB",
                "listing_price": "2000",
                "dial_numerals": "Arabic",
                "auction_type": "NR",
                "dial_color": "Black",
            },
            cache_path,
        )
        assert result["match_resolution"] == "single_bucket"

    def test_unknown_field_rejected_bad_input(self, tmp_path):
        """_Input must reject unknown fields per §4.2 (extra='forbid')."""
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {
                "brand": "Tudor",
                "reference": "79830RB",
                "listing_price": "2000",
                "unexpected_field": "should_fail",
            },
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"

    def test_premium_scalar_is_fraction_not_percentage(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert result["match_resolution"] == "single_bucket"
        ps = result["math"]["premium_scalar"]
        assert isinstance(ps, (int, float))
        assert ps < 1.0, (
            f"premium_scalar must be a fraction (e.g. 0.10), not percentage. Got {ps}"
        )

    def test_headroom_pct_null_on_bucket_path(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_stdin(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert result["match_resolution"] == "single_bucket"
        assert result["math"]["headroom_pct"] is None


# ─── Argv dispatch path (spawnArgv / plugin primary path) ─────────────


class TestArgvDispatch:
    """Verify the argv[1] JSON dispatch path — the plugin's actual call path."""

    def test_argv_happy_path(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        rc, result = _call_via_argv(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "single_bucket"
        assert result["decision"] == "yes"

    def test_argv_error_bad_input(self):
        proc = subprocess.run(
            [sys.executable, _SCRIPT, "{not valid json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        result = json.loads(proc.stdout)
        assert proc.returncode == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"

    def test_argv_missing_arg(self, tmp_path):
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_argv(
            {"reference": "79830RB", "listing_price": "2000"},
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "missing_arg"

    def test_argv_error_envelope_full_shape(self, tmp_path):
        missing_cache = str(tmp_path / "nonexistent.json")
        rc, result = _call_via_argv(
            {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"},
            missing_cache,
        )
        assert rc == 0
        assert result["decision"] == "no"
        assert result["match_resolution"] == "error"
        assert result["match_resolution_label"] == "Lookup error"
        assert result["error"] == "no_cache"

    def _call_run_from_argv_with(self, argv1: str, capsys) -> tuple[int, dict]:
        """Call _run_from_argv() directly with a patched sys.argv[1]."""
        with patch.object(sys, "argv", ["evaluate_deal.py", argv1]):
            rc = _run_from_argv()
        captured = capsys.readouterr()
        return rc, json.loads(captured.out)

    def test_argv_non_object_json_integer(self, capsys):
        """argv[1] that is valid JSON but not an object must return bad_input at rc 0."""
        rc, result = self._call_run_from_argv_with("42", capsys)
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"

    def test_argv_non_object_json_string(self, capsys):
        rc, result = self._call_run_from_argv_with('"hello"', capsys)
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"

    def test_argv_non_object_json_list(self, capsys):
        rc, result = self._call_run_from_argv_with("[1, 2, 3]", capsys)
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "bad_input"


# ─── Pydantic validation behavior pins ───────────────────────────────


class TestValidationBehaviorPins:
    """Pin edge-case Pydantic validation behavior so upgrades don't silently flip it."""

    def test_missing_field_takes_precedence_over_extra_field(self, tmp_path):
        """When payload omits a required field AND includes an unknown field,
        missing_arg is returned (not bad_input). This pins the Pydantic v2
        behavior documented in _run_from_dict: missing errors sort before
        extra_forbidden errors in the ValidationError list."""
        cache_path = _write_cache(tmp_path, _make_v3_cache())
        rc, result = _call_via_stdin(
            {
                "reference": "79830RB",
                "listing_price": "2000",
                "unexpected_extra_field": "should_also_be_rejected",
            },
            cache_path,
        )
        assert rc == 0
        assert result["match_resolution"] == "error"
        assert result["error"] == "missing_arg", (
            "missing_arg must take precedence over bad_input when both "
            "a required field is absent and an unknown field is present"
        )


# ─── Idempotency ─────────────────────────────────────────────────────


class TestIdempotency:
    def test_two_identical_calls_same_output(self, tmp_path):
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        payload = {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"}
        _, r1 = _call_via_stdin(payload, cache_path)
        _, r2 = _call_via_stdin(payload, cache_path)
        assert r1["decision"] == r2["decision"]
        assert r1["match_resolution"] == r2["match_resolution"]
        assert r1["math"]["max_buy"] == r2["math"]["max_buy"]
        assert r1["math"]["margin_pct"] == r2["math"]["margin_pct"]

    def test_argv_stdin_same_output(self, tmp_path):
        """argv[1] and stdin paths produce identical output for the same payload."""
        cache = _make_v3_cache(refs={
            "79830RB": _make_ref(buckets=[_make_bucket(median=3200.0)])
        })
        cache_path = _write_cache(tmp_path, cache)
        payload = {"brand": "Tudor", "reference": "79830RB", "listing_price": "2000"}
        _, r_stdin = _call_via_stdin(payload, cache_path)
        _, r_argv = _call_via_argv(payload, cache_path)
        assert r_stdin["decision"] == r_argv["decision"]
        assert r_stdin["match_resolution"] == r_argv["match_resolution"]
        assert r_stdin["math"]["max_buy"] == r_argv["math"]["max_buy"]
