"""Tests for scripts.analyze_brands; brand-level rollups per guide Section 7.5.

New in v2; no v1 equivalent. All tests hand-computed from guide spec.

Qualification: brand needs 2+ scored references to produce a rollup.
Warming: count of refs with momentum score > 0.
Cooling: count of refs with momentum score < 0.
Score == 0: neutral (neither warming nor cooling).
Signal:
  "Brand heating"  if warming > cooling * 2
  "Brand cooling"  if cooling > warming * 2
  "Mixed"          otherwise

Hand-computed constants table:
─────────────────────────────────────────────────────────────────────────
  Test case               Scores          W  C  W>C*2  C>W*2  Signal         avg_momentum
  ─────────────────────────────────────────────────────────────────────
  heating_5w_2c           [2,1,1,1,1,-1,-1]  5  2  5>4 T  2>10 F  Brand heating  0.6 (=4/7≈0.571→0.6)
  heating_boundary_miss   [1,1,1,1,-1,-1]    4  2  4>4 F  2>8 F   Mixed          0.3 (=2/6≈0.333→0.3)
  cooling_1w_3c           [1,-1,-1,-1]       1  3  1>6 F  3>2 T   Brand cooling -0.5 (=-2/4=-0.5)
  cooling_boundary_miss   [-1,-1,-1,1,1]     2  3  2>6 F  3>4 F   Mixed         -0.2 (=-1/5=-0.2)
  mixed_equal             [1,1,-1,-1]        2  2  2>4 F  2>4 F   Mixed          0.0
  all_zero                [0,0,0]            0  0  0>0 F  0>0 F   Mixed          0.0
  heating_zero_cooling    [2,1]              2  0  2>0 T  0>4 F   Brand heating  1.5
  four_scores             [2,-1,1,0]         2  1  2>2 F  1>4 F   Mixed          0.5
  three_scores_rounding   [1,1,-1]           2  1  2>2 F  1>4 F   Mixed          0.3 (=1/3≈0.333→0.3)
─────────────────────────────────────────────────────────────────────────
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "analyze_brands.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SALES_CSV = str(FIXTURES / "sales_sample.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_brands import brand_momentum


def _ref(brand: str, ref: str = "R") -> dict:
    """Minimal scored reference dict."""
    return {"brand": brand, "reference": ref, "median": 3000, "volume": 5, "signal": "Strong"}


def _momentum(score: int) -> dict:
    return {"score": score, "label": "test"}


# ═══════════════════════════════════════════════════════════════════════
# Qualification: minimum reference count
# ═══════════════════════════════════════════════════════════════════════


class TestMinRefCount:
    def test_1_ref_excluded(self):
        """Brand with 1 reference -> not in rollup."""
        refs = {"R1": _ref("Tudor")}
        result = brand_momentum(refs, {"R1": _momentum(2)})
        assert result == {}

    def test_2_refs_qualifies(self):
        """Brand with exactly 2 references -> in rollup."""
        refs = {"R1": _ref("Tudor"), "R2": _ref("Tudor")}
        momentum = {"R1": _momentum(1), "R2": _momentum(-1)}
        result = brand_momentum(refs, momentum)
        assert "Tudor" in result
        assert result["Tudor"]["reference_count"] == 2

    def test_3_refs_qualifies(self):
        """Brand with 3 references -> in rollup."""
        refs = {f"R{i}": _ref("Tudor") for i in range(3)}
        momentum = {f"R{i}": _momentum(0) for i in range(3)}
        result = brand_momentum(refs, momentum)
        assert result["Tudor"]["reference_count"] == 3


# ═══════════════════════════════════════════════════════════════════════
# Signal thresholds
# ═══════════════════════════════════════════════════════════════════════


class TestSignalThresholds:
    def test_heating_5w_2c(self):
        """5 warming, 2 cooling: 5 > 2*2=4 -> Brand heating. avg=4/7≈0.6."""
        refs = {f"R{i}": _ref("B") for i in range(7)}
        scores = [2, 1, 1, 1, 1, -1, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Brand heating"
        assert result["B"]["warming"] == 5
        assert result["B"]["cooling"] == 2
        assert result["B"]["avg_momentum"] == 0.6

    def test_heating_boundary_miss_4w_2c(self):
        """4 warming, 2 cooling: 4 > 2*2=4 is false -> Mixed. avg=2/6≈0.3."""
        refs = {f"R{i}": _ref("B") for i in range(6)}
        scores = [1, 1, 1, 1, -1, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Mixed"
        assert result["B"]["warming"] == 4
        assert result["B"]["cooling"] == 2
        assert result["B"]["avg_momentum"] == 0.3

    def test_cooling_1w_3c(self):
        """1 warming, 3 cooling: 3 > 1*2=2 -> Brand cooling. avg=-2/4=-0.5."""
        refs = {f"R{i}": _ref("B") for i in range(4)}
        scores = [1, -1, -1, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Brand cooling"
        assert result["B"]["warming"] == 1
        assert result["B"]["cooling"] == 3
        assert result["B"]["avg_momentum"] == -0.5

    def test_cooling_boundary_miss_2w_3c(self):
        """2 warming, 3 cooling: 3 > 2*2=4 is false -> Mixed. avg=-1/5=-0.2."""
        refs = {f"R{i}": _ref("B") for i in range(5)}
        scores = [-1, -1, -1, 1, 1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Mixed"
        assert result["B"]["warming"] == 2
        assert result["B"]["cooling"] == 3
        assert result["B"]["avg_momentum"] == -0.2

    def test_mixed_equal(self):
        """2 warming, 2 cooling -> Mixed. avg=0.0."""
        refs = {f"R{i}": _ref("B") for i in range(4)}
        scores = [1, 1, -1, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Mixed"
        assert result["B"]["warming"] == 2
        assert result["B"]["cooling"] == 2
        assert result["B"]["avg_momentum"] == 0.0

    def test_all_zero_neutral(self):
        """3 refs all score 0 -> 0 warming, 0 cooling, Mixed. avg=0.0."""
        refs = {f"R{i}": _ref("B") for i in range(3)}
        momentum = {f"R{i}": _momentum(0) for i in range(3)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Mixed"
        assert result["B"]["warming"] == 0
        assert result["B"]["cooling"] == 0
        assert result["B"]["avg_momentum"] == 0.0

    def test_heating_zero_cooling(self):
        """2 warming, 0 cooling: 2 > 0*2=0 -> Brand heating. avg=3/2=1.5."""
        refs = {"R0": _ref("B"), "R1": _ref("B")}
        momentum = {"R0": _momentum(2), "R1": _momentum(1)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["signal"] == "Brand heating"
        assert result["B"]["warming"] == 2
        assert result["B"]["cooling"] == 0
        assert result["B"]["avg_momentum"] == 1.5


# ═══════════════════════════════════════════════════════════════════════
# Aggregation correctness
# ═══════════════════════════════════════════════════════════════════════


class TestAggregation:
    def test_avg_momentum_four_scores(self):
        """Scores [2, -1, 1, 0] -> mean = 2/4 = 0.5."""
        refs = {f"R{i}": _ref("B") for i in range(4)}
        scores = [2, -1, 1, 0]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["avg_momentum"] == 0.5
        assert result["B"]["warming"] == 2
        assert result["B"]["cooling"] == 1

    def test_avg_momentum_rounding(self):
        """Scores [1, 1, -1] -> mean = 1/3 ≈ 0.333 -> rounds to 0.3."""
        refs = {f"R{i}": _ref("B") for i in range(3)}
        scores = [1, 1, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["avg_momentum"] == 0.3

    def test_score_zero_counts_as_neither(self):
        """Score 0 is not warming and not cooling."""
        refs = {f"R{i}": _ref("B") for i in range(4)}
        scores = [1, 0, 0, -1]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert result["B"]["warming"] == 1
        assert result["B"]["cooling"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Missing momentum / defaults
# ═══════════════════════════════════════════════════════════════════════


class TestMissingMomentum:
    def test_no_momentum_dict(self):
        """momentum=None -> all scores default to 0."""
        refs = {"R0": _ref("B"), "R1": _ref("B")}
        result = brand_momentum(refs, None)
        assert result["B"]["avg_momentum"] == 0.0
        assert result["B"]["warming"] == 0
        assert result["B"]["cooling"] == 0

    def test_partial_momentum(self):
        """Ref missing from momentum dict -> score 0. [2, 0] -> avg 1.0, 1 warming."""
        refs = {"R0": _ref("B"), "R1": _ref("B")}
        momentum = {"R0": _momentum(2)}  # R1 missing
        result = brand_momentum(refs, momentum)
        assert result["B"]["avg_momentum"] == 1.0
        assert result["B"]["warming"] == 1
        assert result["B"]["cooling"] == 0

    def test_momentum_entry_missing_score_key(self):
        """Momentum entry with no 'score' key -> defaults to 0."""
        refs = {"R0": _ref("B"), "R1": _ref("B")}
        momentum = {"R0": _momentum(1), "R1": {"label": "oops"}}
        result = brand_momentum(refs, momentum)
        assert result["B"]["avg_momentum"] == 0.5
        assert result["B"]["warming"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_refs(self):
        """Empty references -> empty rollup."""
        result = brand_momentum({}, {})
        assert result == {}

    def test_multiple_brands(self):
        """Two brands with different signals."""
        refs = {
            "T1": _ref("Tudor"), "T2": _ref("Tudor"), "T3": _ref("Tudor"),
            "B1": _ref("Breitling"), "B2": _ref("Breitling"),
        }
        momentum = {
            "T1": _momentum(2), "T2": _momentum(1), "T3": _momentum(-1),
            "B1": _momentum(-2), "B2": _momentum(-1),
        }
        result = brand_momentum(refs, momentum)
        # Tudor: 2w, 1c -> 2 > 2 false -> Mixed. avg = 2/3 ≈ 0.7
        assert result["Tudor"]["signal"] == "Mixed"
        assert result["Tudor"]["avg_momentum"] == 0.7
        # Breitling: 0w, 2c -> 2 > 0 true -> Brand cooling. avg = -3/2 = -1.5
        assert result["Breitling"]["signal"] == "Brand cooling"
        assert result["Breitling"]["avg_momentum"] == -1.5

    def test_all_refs_single_brand(self):
        """All references in one brand."""
        refs = {f"R{i}": _ref("Omega") for i in range(5)}
        scores = [3, 2, 1, -1, -2]
        momentum = {f"R{i}": _momentum(s) for i, s in enumerate(scores)}
        result = brand_momentum(refs, momentum)
        assert len(result) == 1
        assert "Omega" in result
        # 3w, 2c -> 3 > 4 false -> Mixed. avg = 3/5 = 0.6
        assert result["Omega"]["signal"] == "Mixed"
        assert result["Omega"]["avg_momentum"] == 0.6

    def test_sorted_output(self):
        """Brands are sorted alphabetically."""
        refs = {
            "Z1": _ref("Zenith"), "Z2": _ref("Zenith"),
            "A1": _ref("Audemars"), "A2": _ref("Audemars"),
        }
        result = brand_momentum(refs, {})
        assert list(result.keys()) == ["Audemars", "Zenith"]


# ═══════════════════════════════════════════════════════════════════════
# Output shape
# ═══════════════════════════════════════════════════════════════════════


class TestOutputShape:
    def test_keys(self):
        """Each brand entry has exactly the 5 specified keys."""
        refs = {"R0": _ref("B"), "R1": _ref("B")}
        result = brand_momentum(refs, {})
        assert set(result["B"].keys()) == {
            "reference_count", "avg_momentum", "warming", "cooling", "signal",
        }


# ═══════════════════════════════════════════════════════════════════════
# run() integration
# ═══════════════════════════════════════════════════════════════════════


class TestRunIntegration:
    def test_run_extracts_refs_and_momentum(self):
        """run() unwraps all_results and trends correctly."""
        from scripts.analyze_brands import run

        all_results = {"references": {
            "R0": _ref("Tudor"), "R1": _ref("Tudor"),
        }}
        trends = {"momentum": {
            "R0": _momentum(2), "R1": _momentum(1),
        }}
        result = run(all_results, trends)
        assert result["count"] == 1
        assert result["brands"]["Tudor"]["signal"] == "Brand heating"

    def test_run_no_trends(self):
        """run() with trends=None -> all momentum 0."""
        from scripts.analyze_brands import run

        all_results = {"references": {
            "R0": _ref("Tudor"), "R1": _ref("Tudor"),
        }}
        result = run(all_results, None)
        assert result["brands"]["Tudor"]["avg_momentum"] == 0.0


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:
    def test_json_output(self):
        """CLI produces valid JSON with brands and count keys."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), SALES_CSV, "--name-cache", NAME_CACHE],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert "brands" in data
        assert "count" in data
        assert isinstance(data["brands"], dict)

    def test_missing_file_error(self, tmp_path):
        """Missing CSV -> nonzero exit, error on stderr."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path / "nope.csv")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        err = json.loads(proc.stderr)
        assert "error" in err
