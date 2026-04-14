#!/usr/bin/env python3
"""Tests for run_grailzee_gate.py."""

import json
import os
import sys

import pytest

TOOLS_DIR    = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(TOOLS_DIR, "fixtures", "grailzee")
EVAL_SHIM    = os.path.join(FIXTURES_DIR, "eval_shim.py")

sys.path.insert(0, TOOLS_DIR)
import run_grailzee_gate as gate_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_draft(folder, draft: dict) -> None:
    path = os.path.join(str(folder), "_draft.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2)


def read_draft(folder) -> dict:
    path = os.path.join(str(folder), "_draft.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fixture_path(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


# ---------------------------------------------------------------------------
# Test draft fixture — Tudor BB GMT at step 3
# ---------------------------------------------------------------------------

TUDOR_DRAFT: dict = {
    "step": 3,
    "timestamp": "2026-04-11T12:00:00Z",
    "inputs": {
        "brand": "Tudor",
        "model": "Black Bay GMT",
        "reference": "79830RB",
        "retail_net": 3800,
        "buffer": 5,
        "grailzee_format": "NR",
    },
    "pricing": {
        "ebay":               {"list_price": 4349, "auto_accept": 4150, "auto_decline": 3700},
        "chrono24":           {"list_price": 4325},
        "facebook_retail":    {"list_price": 4150},
        "facebook_wholesale": None,
        "wta":                None,
        "reddit":             None,
        "grailzee":           {"format": "NR", "reserve_price": None},
    },
}


# ---------------------------------------------------------------------------
# Section 1 — call_evaluator
# ---------------------------------------------------------------------------

class TestCallEvaluator:
    def test_returns_parsed_json_on_success(self, monkeypatch):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        result = gate_mod.call_evaluator("Tudor", "79830RB", 3800, EVAL_SHIM)
        assert result["status"] == "ok"
        assert result["grailzee"] == "YES"
        assert result["format"] == "NR"
        assert "metrics" in result

    def test_returns_error_on_nonexistent_script(self):
        result = gate_mod.call_evaluator(
            "Tudor", "79830RB", 3800,
            "/nonexistent/path/evaluate_deal.py",
        )
        assert result["status"] == "error"
        assert result["error"] == "evaluator_failed"
        assert "message" in result

    def test_returns_error_on_non_json_output(self, monkeypatch, tmp_path):
        # Create a script that outputs garbage
        garbage_script = tmp_path / "garbage.py"
        garbage_script.write_text("print('not json at all')\n")
        result = gate_mod.call_evaluator("Tudor", "79830RB", 3800, str(garbage_script))
        assert result["status"] == "error"
        assert result["error"] == "evaluator_failed"
        assert "Non-JSON" in result["message"]

    def test_propagates_cache_path_arg(self, monkeypatch, tmp_path):
        # Shim ignores args but must not crash when --cache is passed.
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        result = gate_mod.call_evaluator(
            "Tudor", "79830RB", 3800, EVAL_SHIM,
            cache_path=str(tmp_path / "dummy_cache.json"),
        )
        # Shim still returns the fixture regardless of cache arg
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Section 2 — interpret_ok
# ---------------------------------------------------------------------------

class TestInterpretOk:
    def _ok(self, grailzee, fmt, reserve_price=None) -> dict:
        return {
            "grailzee": grailzee,
            "format": fmt,
            "reserve_price": reserve_price,
            "rationale": "test rationale",
            "metrics": {"median": 4500, "max_buy": 4144, "signal": "Strong", "margin_pct": 14.5},
        }

    def test_yes_nr_is_proceed(self):
        gate = gate_mod.interpret_ok(self._ok("YES", "NR"))
        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "NR"
        assert gate["reserve_price"] is None

    def test_yes_reserve_is_proceed(self):
        gate = gate_mod.interpret_ok(self._ok("YES", "Reserve", reserve_price=4010))
        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "Reserve"
        assert gate["reserve_price"] == 4010

    def test_maybe_reserve_is_proceed(self):
        gate = gate_mod.interpret_ok(self._ok("MAYBE", "Reserve", reserve_price=3970))
        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "Reserve"
        assert gate["reserve_price"] == 3970

    def test_no_is_adjust(self):
        gate = gate_mod.interpret_ok(self._ok("NO", "NR"))
        assert gate["status"] == "adjust"
        assert "recommendation" in gate

    def test_maybe_nr_is_adjust(self):
        # MAYBE+NR requires YES conviction for NR; route to adjust
        gate = gate_mod.interpret_ok(self._ok("MAYBE", "NR"))
        assert gate["status"] == "adjust"

    def test_rationale_preserved(self):
        data = self._ok("YES", "NR")
        data["rationale"] = "specific rationale text"
        gate = gate_mod.interpret_ok(data)
        assert gate["rationale"] == "specific rationale text"

    def test_metrics_preserved(self):
        data = self._ok("YES", "NR")
        gate = gate_mod.interpret_ok(data)
        assert gate["metrics"]["median"] == 4500
        assert gate["metrics"]["signal"] == "Strong"


# ---------------------------------------------------------------------------
# Section 3 — gate_from_evaluator
# ---------------------------------------------------------------------------

class TestGateFromEvaluator:
    def test_ok_routes_to_interpret_ok(self):
        data = {
            "status": "ok",
            "grailzee": "YES",
            "format": "NR",
            "reserve_price": None,
            "rationale": "Strong buy.",
            "metrics": {"median": 4500, "max_buy": 4144, "signal": "Strong", "margin_pct": 14.5},
        }
        gate = gate_mod.gate_from_evaluator(data)
        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "NR"

    def test_not_found_is_manual_check(self):
        data = {"status": "not_found", "brand": "Tudor", "reference": "79830RB"}
        gate = gate_mod.gate_from_evaluator(data)
        assert gate["status"] == "manual_check"
        assert "reference not in" in gate["reason"]

    def test_error_no_cache_is_manual_check(self):
        data = {"status": "error", "error": "no_cache", "message": "Cache missing."}
        gate = gate_mod.gate_from_evaluator(data)
        assert gate["status"] == "manual_check"
        assert gate["reason"] == "no_cache"

    def test_evaluator_failed_is_manual_check(self):
        data = {
            "status": "error",
            "error": "evaluator_failed",
            "message": "Non-JSON output",
        }
        gate = gate_mod.gate_from_evaluator(data)
        assert gate["status"] == "manual_check"
        assert gate["reason"] == "evaluator_failed"

    def test_stale_schema_is_manual_check(self):
        data = {"status": "error", "error": "stale_schema", "message": "Outdated format."}
        gate = gate_mod.gate_from_evaluator(data)
        assert gate["status"] == "manual_check"
        assert gate["reason"] == "stale_schema"


# ---------------------------------------------------------------------------
# Section 4 — run_gate: proceed paths
# ---------------------------------------------------------------------------

class TestRunGateProceed:
    def test_yes_nr_writes_proceed_to_draft(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "NR"

        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5
        assert draft["approved"]["grailzee_gate"]["status"] == "proceed"
        assert draft["pricing"]["grailzee"]["format"] == "NR"
        assert draft["pricing"]["grailzee"]["reserve_price"] is None

    def test_yes_reserve_updates_format_and_reserve_price(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_reserve.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "Reserve"
        assert gate["reserve_price"] == 4010

        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5
        assert draft["approved"]["grailzee_gate"]["status"] == "proceed"
        assert draft["pricing"]["grailzee"]["format"] == "Reserve"
        assert draft["pricing"]["grailzee"]["reserve_price"] == 4010

    def test_maybe_reserve_is_proceed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_maybe_reserve.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "proceed"
        assert gate["grailzee_format"] == "Reserve"
        assert gate["reserve_price"] == 3970

        draft = read_draft(tmp_path)
        assert draft["pricing"]["grailzee"]["format"] == "Reserve"
        assert draft["pricing"]["grailzee"]["reserve_price"] == 3970

    def test_proceed_preserves_other_pricing_keys(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        write_draft(tmp_path, TUDOR_DRAFT)
        gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        draft = read_draft(tmp_path)
        # Other pricing keys must survive the grailzee update
        assert draft["pricing"]["ebay"]["list_price"] == 4349
        assert draft["pricing"]["chrono24"]["list_price"] == 4325
        assert draft["pricing"]["facebook_retail"]["list_price"] == 4150

    def test_proceed_writes_median_and_format_to_approved_gate(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        write_draft(tmp_path, TUDOR_DRAFT)
        gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        draft = read_draft(tmp_path)
        assert draft["approved"]["grailzee_gate"]["median"] == 4500
        assert draft["approved"]["grailzee_gate"]["signal"] == "Strong"
        assert draft["approved"]["grailzee_gate"]["grailzee_format"] == "NR"


# ---------------------------------------------------------------------------
# Section 5 — run_gate: adjust and manual_check paths
# ---------------------------------------------------------------------------

class TestRunGateNegative:
    def test_no_is_adjust(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_no.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "adjust"
        assert "recommendation" in gate

        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5
        assert draft["approved"]["grailzee_gate"]["status"] == "adjust"
        # pricing.grailzee must NOT be updated on adjust
        assert draft["pricing"]["grailzee"]["format"] == "NR"

    def test_adjust_does_not_overwrite_pricing_grailzee(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_no.json"))
        write_draft(tmp_path, TUDOR_DRAFT)
        gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        draft = read_draft(tmp_path)
        # pricing.grailzee stays as run_pricing.py set it
        assert "grailzee" in draft["pricing"]
        assert draft["pricing"]["grailzee"]["format"] == "NR"

    def test_not_found_is_manual_check(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("not_found.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "manual_check"

        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5
        assert draft["approved"]["grailzee_gate"]["status"] == "manual_check"
        assert "reason" in draft["approved"]["grailzee_gate"]

    def test_error_no_cache_is_manual_check(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("error_no_cache.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "manual_check"
        assert gate["reason"] == "no_cache"

        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5
        assert draft["approved"]["grailzee_gate"]["status"] == "manual_check"

    def test_evaluator_crash_is_manual_check(self, monkeypatch, tmp_path):
        """A script that crashes (exit 1, no output) should produce manual_check."""
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        crash_script = tmp_path / "crash.py"
        crash_script.write_text("import sys; sys.exit(1)\n")

        gate = gate_mod.run_gate(str(tmp_path), eval_script=str(crash_script))

        assert gate["status"] == "manual_check"
        draft = read_draft(tmp_path)
        assert draft["step"] == 3.5

    def test_manual_check_does_not_overwrite_pricing_grailzee(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("error_no_cache.json"))
        write_draft(tmp_path, TUDOR_DRAFT)
        gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        draft = read_draft(tmp_path)
        assert draft["pricing"]["grailzee"]["format"] == "NR"


# ---------------------------------------------------------------------------
# Section 6 — run_gate: skip path
# ---------------------------------------------------------------------------

class TestRunGateSkip:
    def test_skip_format_bypasses_evaluator(self, tmp_path):
        draft = {**TUDOR_DRAFT, "inputs": {**TUDOR_DRAFT["inputs"], "grailzee_format": "skip"}}
        write_draft(tmp_path, draft)

        # EVAL_SHIM would fail without GRAILZEE_FIXTURE; evaluator must not be called
        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "skip"
        saved = read_draft(tmp_path)
        assert saved["step"] == 3.5
        assert saved["approved"]["grailzee_gate"]["status"] == "skip"

    def test_absent_grailzee_format_bypasses_evaluator(self, tmp_path):
        inputs = {k: v for k, v in TUDOR_DRAFT["inputs"].items() if k != "grailzee_format"}
        draft = {**TUDOR_DRAFT, "inputs": inputs}
        write_draft(tmp_path, draft)

        gate = gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        assert gate["status"] == "skip"
        saved = read_draft(tmp_path)
        assert saved["step"] == 3.5

    def test_skip_does_not_modify_pricing_grailzee(self, tmp_path):
        draft = {**TUDOR_DRAFT, "inputs": {**TUDOR_DRAFT["inputs"], "grailzee_format": "skip"}}
        write_draft(tmp_path, draft)
        gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

        saved = read_draft(tmp_path)
        # pricing.grailzee was set to {"format": "NR", ...} by run_pricing; must not change
        assert saved["pricing"]["grailzee"]["format"] == "NR"

    def test_unknown_grailzee_format_fails(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        draft = {**TUDOR_DRAFT, "inputs": {**TUDOR_DRAFT["inputs"], "grailzee_format": "typo"}}
        write_draft(tmp_path, draft)

        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)


# ---------------------------------------------------------------------------
# Section 7 — run_gate: validation / pre-conditions
# ---------------------------------------------------------------------------

class TestRunGateValidation:
    def test_fails_if_step_not_3(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        draft = {**TUDOR_DRAFT, "step": 2}
        write_draft(tmp_path, draft)

        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

    def test_fails_if_brand_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        inputs = {k: v for k, v in TUDOR_DRAFT["inputs"].items() if k != "brand"}
        draft = {**TUDOR_DRAFT, "inputs": inputs}
        write_draft(tmp_path, draft)

        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

    def test_fails_if_reference_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        inputs = {k: v for k, v in TUDOR_DRAFT["inputs"].items() if k != "reference"}
        draft = {**TUDOR_DRAFT, "inputs": inputs}
        write_draft(tmp_path, draft)

        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

    def test_fails_if_retail_net_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        inputs = {k: v for k, v in TUDOR_DRAFT["inputs"].items() if k != "retail_net"}
        draft = {**TUDOR_DRAFT, "inputs": inputs}
        write_draft(tmp_path, draft)

        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)

    def test_fails_if_no_draft_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        with pytest.raises(SystemExit):
            gate_mod.run_gate(str(tmp_path), eval_script=EVAL_SHIM)


# ---------------------------------------------------------------------------
# Section 8 — dry-run
# ---------------------------------------------------------------------------

class TestRunGateDryRun:
    def test_dry_run_does_not_write_draft(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_nr.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), dry_run=True, eval_script=EVAL_SHIM)

        assert gate["status"] == "proceed"
        draft = read_draft(tmp_path)
        # Draft must still be at step 3 — dry-run never writes
        assert draft["step"] == 3
        assert "approved" not in draft

    def test_dry_run_skip_does_not_write(self, tmp_path):
        draft = {**TUDOR_DRAFT, "inputs": {**TUDOR_DRAFT["inputs"], "grailzee_format": "skip"}}
        write_draft(tmp_path, draft)

        gate = gate_mod.run_gate(str(tmp_path), dry_run=True, eval_script=EVAL_SHIM)

        assert gate["status"] == "skip"
        saved = read_draft(tmp_path)
        assert saved["step"] == 3

    def test_dry_run_adjust_does_not_write(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_FIXTURE", fixture_path("ok_no.json"))
        write_draft(tmp_path, TUDOR_DRAFT)

        gate = gate_mod.run_gate(str(tmp_path), dry_run=True, eval_script=EVAL_SHIM)

        assert gate["status"] == "adjust"
        saved = read_draft(tmp_path)
        assert saved["step"] == 3
        assert "approved" not in saved


# ---------------------------------------------------------------------------
# Section 9 — format_summary
# ---------------------------------------------------------------------------

class TestFormatSummary:
    def test_proceed_nr_contains_status_and_format(self):
        gate = {
            "status": "proceed",
            "grailzee_format": "NR",
            "reserve_price": None,
            "metrics": {"median": 4500, "max_buy": 4144, "signal": "Strong", "margin_pct": 14.5},
            "rationale": "Strong buy.",
        }
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "PROCEED" in text
        assert "NR" in text
        assert "$4,500" in text
        assert "Strong" in text

    def test_proceed_reserve_shows_reserve_price(self):
        gate = {
            "status": "proceed",
            "grailzee_format": "Reserve",
            "reserve_price": 4010,
            "metrics": {"median": 4300, "max_buy": 3991, "signal": "Normal", "margin_pct": 7.9},
            "rationale": "Buy works.",
        }
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "Reserve" in text
        assert "$4,010" in text

    def test_adjust_contains_adjust_and_recommendation(self):
        gate = {
            "status": "adjust",
            "grailzee_format": "NR",
            "reserve_price": None,
            "metrics": {},
            "rationale": "Price over MAX BUY.",
            "recommendation": "Consider repricing.",
        }
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "ADJUST" in text
        assert "Consider repricing" in text

    def test_manual_check_contains_reason(self):
        gate = {
            "status": "manual_check",
            "reason": "no_cache",
            "metrics": {},
            "rationale": "",
        }
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "MANUAL CHECK" in text
        assert "no_cache" in text

    def test_skip_contains_skip(self):
        gate = {"status": "skip"}
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "SKIP" in text

    def test_header_contains_brand_and_reference(self):
        gate = {"status": "skip"}
        text = gate_mod.format_summary("Tudor", "79830RB", gate)
        assert "Tudor" in text
        assert "79830RB" in text
