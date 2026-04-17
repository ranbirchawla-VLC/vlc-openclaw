"""Tests for scripts.analyze_changes; emerged/shifted/faded/unnamed detection.

New in v2 per guide Section 7.2. No v1 equivalent; no v1/v2 equivalence
test. All tests are hand-computed from the guide spec.

Thresholds:
  emerged: in curr, not in prev (score_all_references already filtered 3+)
  shifted: in both, abs(median_pct_change) > 5%
  faded: in prev, not in curr
  unnamed: in curr, not in name_cache
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "analyze_changes.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SALES_CSV = str(FIXTURES / "sales_sample.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_changes import SHIFTED_THRESHOLD_PCT, detect_changes


def _ref(median=3000, brand="Tudor", model="Test", reference="TEST"):
    return {"brand": brand, "model": model, "reference": reference, "median": median}


# ═══════════════════════════════════════════════════════════════════════
# detect_changes
# ═══════════════════════════════════════════════════════════════════════


class TestDetectChanges:
    def test_emerged(self):
        curr = {"NEW_REF": _ref(reference="NEW_REF")}
        prev = {}
        nc = {}
        result = detect_changes(curr, prev, nc)
        assert "NEW_REF" in result["emerged"]

    def test_faded(self):
        curr = {}
        prev = {"OLD_REF": _ref(reference="OLD_REF")}
        nc = {}
        result = detect_changes(curr, prev, nc)
        assert "OLD_REF" in result["faded"]

    def test_shifted_up(self):
        """Median 3000 -> 3200 = +6.67% > 5% threshold."""
        curr = {"79830RB": _ref(median=3200)}
        prev = {"79830RB": _ref(median=3000)}
        result = detect_changes(curr, prev, {})
        assert "79830RB" in result["shifted"]
        assert result["shifted"]["79830RB"]["direction"] == "up"
        assert result["shifted"]["79830RB"]["pct"] == pytest.approx(6.7, abs=0.1)

    def test_shifted_down(self):
        """Median 3000 -> 2800 = -6.67% > 5% threshold."""
        curr = {"79830RB": _ref(median=2800)}
        prev = {"79830RB": _ref(median=3000)}
        result = detect_changes(curr, prev, {})
        assert result["shifted"]["79830RB"]["direction"] == "down"
        assert result["shifted"]["79830RB"]["pct"] == pytest.approx(-6.7, abs=0.1)

    def test_not_shifted_within_threshold(self):
        """Median 3000 -> 3100 = +3.33% <= 5%."""
        curr = {"79830RB": _ref(median=3100)}
        prev = {"79830RB": _ref(median=3000)}
        result = detect_changes(curr, prev, {})
        assert "79830RB" not in result["shifted"]

    def test_unnamed(self):
        curr = {"UNKNOWN": _ref(reference="UNKNOWN")}
        prev = {}
        nc = {"79830RB": {"brand": "Tudor"}}  # UNKNOWN not in cache
        result = detect_changes(curr, prev, nc)
        assert "UNKNOWN" in result["unnamed"]

    def test_named_not_in_unnamed(self):
        curr = {"79830RB": _ref(reference="79830RB")}
        prev = {}
        nc = {"79830RB": {"brand": "Tudor"}}
        result = detect_changes(curr, prev, nc)
        assert "79830RB" not in result["unnamed"]

    def test_all_categories_together(self):
        """Multiple refs across all categories simultaneously."""
        curr = {
            "EMERGED": _ref(median=3000, reference="EMERGED"),
            "STABLE": _ref(median=3050, reference="STABLE"),
            "SHIFTED": _ref(median=3400, reference="SHIFTED"),
        }
        prev = {
            "STABLE": _ref(median=3000, reference="STABLE"),
            "SHIFTED": _ref(median=3000, reference="SHIFTED"),
            "FADED": _ref(median=2500, reference="FADED"),
        }
        nc = {"STABLE": {}, "SHIFTED": {}}  # EMERGED not in cache
        result = detect_changes(curr, prev, nc)
        assert "EMERGED" in result["emerged"]
        assert "FADED" in result["faded"]
        assert "SHIFTED" in result["shifted"]
        assert "STABLE" not in result["shifted"]  # 1.67% < 5%
        assert "EMERGED" in result["unnamed"]


class TestThresholdBoundaries:
    def test_exactly_5_percent_not_shifted(self):
        """Exactly 5.0% is NOT shifted (threshold is >5%, not >=5%)."""
        curr = {"R": _ref(median=3150)}
        prev = {"R": _ref(median=3000)}
        # 150/3000 = 5.0% exactly
        result = detect_changes(curr, prev, {})
        assert "R" not in result["shifted"]

    def test_just_over_5_percent_shifted(self):
        """5.1% is shifted."""
        curr = {"R": _ref(median=3153)}
        prev = {"R": _ref(median=3000)}
        # 153/3000 = 5.1%
        result = detect_changes(curr, prev, {})
        assert "R" in result["shifted"]

    def test_negative_just_over_5_percent_shifted(self):
        """-5.1% is shifted down."""
        curr = {"R": _ref(median=2847)}
        prev = {"R": _ref(median=3000)}
        # -153/3000 = -5.1%
        result = detect_changes(curr, prev, {})
        assert "R" in result["shifted"]
        assert result["shifted"]["R"]["direction"] == "down"

    def test_zero_prev_median_skipped(self):
        """prev_median=0 cannot divide; ref excluded from shifted."""
        curr = {"R": _ref(median=3000)}
        prev = {"R": _ref(median=0)}
        result = detect_changes(curr, prev, {})
        assert "R" not in result["shifted"]


class TestSingleReport:
    def test_no_prev_all_emerged(self):
        """Single report: all current refs are emerged, none faded/shifted."""
        curr = {
            "A": _ref(reference="A"),
            "B": _ref(reference="B"),
        }
        result = detect_changes(curr, {}, {})
        assert sorted(result["emerged"]) == ["A", "B"]
        assert result["shifted"] == {}
        assert result["faded"] == []

    def test_no_prev_unnamed_still_detected(self):
        curr = {"A": _ref(reference="A")}
        nc = {"B": {}}  # A not in cache
        result = detect_changes(curr, {}, nc)
        assert "A" in result["unnamed"]


class TestEmptyInputs:
    def test_both_empty(self):
        result = detect_changes({}, {}, {})
        assert result == {"emerged": [], "shifted": {}, "faded": [], "unnamed": []}

    def test_curr_empty_prev_populated(self):
        prev = {"A": _ref(reference="A")}
        result = detect_changes({}, prev, {})
        assert result["faded"] == ["A"]
        assert result["emerged"] == []


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


class TestCLI:
    def test_single_csv(self):
        r = run_cli(SALES_CSV, "--name-cache", NAME_CACHE)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        # Single report: all scored refs are emerged
        assert len(data["emerged"]) > 0
        assert data["faded"] == []
        assert data["shifted"] == {}

    def test_two_csvs(self, tmp_path):
        """Same CSV as both periods: nothing emerged/faded, nothing shifted."""
        import shutil
        csv2 = tmp_path / "prev.csv"
        shutil.copy(SALES_CSV, csv2)
        r = run_cli(SALES_CSV, str(csv2), "--name-cache", NAME_CACHE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["emerged"] == []
        assert data["faded"] == []
        assert data["shifted"] == {}

    def test_missing_csv_fails(self):
        r = run_cli("/tmp/nonexistent.csv")
        assert r.returncode != 0

    def test_stdout_valid_json(self):
        r = run_cli(SALES_CSV, "--name-cache", NAME_CACHE)
        json.loads(r.stdout)
