"""Tests for scripts.analyze_trends; period comparison and momentum scoring.

Hand-computed constants:
  median 3000->3200: mc=200, mp=6.67% => no signal (Stable)
  median 3000->2800: mc=-200, mp=-6.67% => Cooling
  median 3000->3400: mc=400, mp=13.33% => Momentum
  st 0.60->0.75: stc=15pp => Demand Up
  st 0.70->0.55: stc=-15pp => Demand Down
  risk 15->25: Now Reserve (prev<=20, curr>20)
  risk 25->15: Now NR (prev>20, curr<=20)
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "analyze_trends.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SALES_CSV = str(FIXTURES / "sales_sample.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_trends import (
    MOMENTUM_LABELS,
    analyze_trends,
    compare_periods,
    momentum_score,
)


def _ref(median=3000, st_pct=0.6, risk_nr=10.0, volume=10, floor=2800,
         brand="Tudor", model="BB GMT", reference="79830RB"):
    """Build a scored-reference dict matching score_all_references shape."""
    return {
        "brand": brand, "model": model, "reference": reference,
        "median": median, "st_pct": st_pct, "risk_nr": risk_nr,
        "volume": volume, "floor": floor,
    }


# ═══════════════════════════════════════════════════════════════════════
# compare_periods
# ═══════════════════════════════════════════════════════════════════════


class TestComparePeriods:
    def test_stable_no_signal(self):
        """6.67% median increase; between -5 and +10 => Stable."""
        prev = {"79830RB": _ref(median=3000)}
        curr = {"79830RB": _ref(median=3200)}
        trends = compare_periods(curr, prev)
        assert len(trends) == 1
        t = trends[0]
        assert t["med_change"] == 200
        assert t["med_pct"] == pytest.approx(6.67, abs=0.01)
        assert t["signal_str"] == "Stable"

    def test_cooling_signal(self):
        """Median down 6.67% => Cooling (mp <= -5)."""
        prev = {"79830RB": _ref(median=3000)}
        curr = {"79830RB": _ref(median=2800)}
        t = compare_periods(curr, prev)[0]
        assert t["med_change"] == -200
        assert t["med_pct"] == pytest.approx(-6.67, abs=0.01)
        assert "Cooling" in t["signals"]

    def test_momentum_signal(self):
        """Median up 13.33% => Momentum (mp >= 10)."""
        prev = {"79830RB": _ref(median=3000)}
        curr = {"79830RB": _ref(median=3400)}
        t = compare_periods(curr, prev)[0]
        assert t["med_pct"] == pytest.approx(13.33, abs=0.01)
        assert "Momentum" in t["signals"]

    def test_demand_up(self):
        """Sell-through up 15pp => Demand Up."""
        prev = {"79830RB": _ref(st_pct=0.60)}
        curr = {"79830RB": _ref(st_pct=0.75)}
        t = compare_periods(curr, prev)[0]
        assert t["st_change"] == pytest.approx(15.0, abs=0.1)
        assert "Demand Up" in t["signals"]

    def test_demand_down(self):
        """Sell-through down 15pp => Demand Down."""
        prev = {"79830RB": _ref(st_pct=0.70)}
        curr = {"79830RB": _ref(st_pct=0.55)}
        t = compare_periods(curr, prev)[0]
        assert t["st_change"] == pytest.approx(-15.0, abs=0.1)
        assert "Demand Down" in t["signals"]

    def test_now_reserve(self):
        """Risk crosses 20% upward => Now Reserve."""
        prev = {"79830RB": _ref(risk_nr=15)}
        curr = {"79830RB": _ref(risk_nr=25)}
        t = compare_periods(curr, prev)[0]
        assert "Now Reserve" in t["signals"]

    def test_now_nr(self):
        """Risk crosses 20% downward => Now NR."""
        prev = {"79830RB": _ref(risk_nr=25)}
        curr = {"79830RB": _ref(risk_nr=15)}
        t = compare_periods(curr, prev)[0]
        assert "Now NR" in t["signals"]

    def test_ref_only_in_curr_excluded(self):
        """Reference present only in current period; no comparison possible."""
        prev = {}
        curr = {"79830RB": _ref()}
        trends = compare_periods(curr, prev)
        assert len(trends) == 0

    def test_ref_only_in_prev_excluded(self):
        prev = {"79830RB": _ref()}
        curr = {}
        trends = compare_periods(curr, prev)
        assert len(trends) == 0

    def test_st_none_both_sides(self):
        """Both st_pct None => st_change is None."""
        prev = {"79830RB": _ref(st_pct=None)}
        curr = {"79830RB": _ref(st_pct=None)}
        t = compare_periods(curr, prev)[0]
        assert t["st_change"] is None

    def test_floor_change(self):
        prev = {"79830RB": _ref(floor=2800)}
        curr = {"79830RB": _ref(floor=2900)}
        t = compare_periods(curr, prev)[0]
        assert t["floor_change"] == 100

    def test_volume_fields(self):
        prev = {"79830RB": _ref(volume=8)}
        curr = {"79830RB": _ref(volume=12)}
        t = compare_periods(curr, prev)[0]
        assert t["prev_vol"] == 8
        assert t["curr_vol"] == 12


# ═══════════════════════════════════════════════════════════════════════
# momentum_score
# ═══════════════════════════════════════════════════════════════════════


class TestMomentumScore:
    def test_empty_returns_stable(self):
        assert momentum_score([]) == {"score": 0, "label": "Stable"}

    def test_all_labels_exist(self):
        """Every score -3 to +3 has a label."""
        for s in range(-3, 4):
            assert s in MOMENTUM_LABELS

    def test_clamped_at_positive_3(self):
        """Many upward signals clamp to +3."""
        data = [
            {"med_pct": 5, "curr_vol": 15, "prev_vol": 10},
            {"med_pct": 5, "curr_vol": 15, "prev_vol": 10},
            {"med_pct": 5, "curr_vol": 15, "prev_vol": 10},
            {"med_pct": 5, "curr_vol": 15, "prev_vol": 10},
            {"med_pct": 5, "curr_vol": 15, "prev_vol": 10},
        ]
        result = momentum_score(data)
        assert result["score"] == 3
        assert result["label"] == "Hot"

    def test_clamped_at_negative_3(self):
        """Many downward signals clamp to -3."""
        data = [
            {"med_pct": -5, "curr_vol": 5, "prev_vol": 10},
            {"med_pct": -5, "curr_vol": 5, "prev_vol": 10},
            {"med_pct": -5, "curr_vol": 5, "prev_vol": 10},
            {"med_pct": -5, "curr_vol": 5, "prev_vol": 10},
            {"med_pct": -5, "curr_vol": 5, "prev_vol": 10},
        ]
        result = momentum_score(data)
        assert result["score"] == -3
        assert result["label"] == "Cooling Fast"

    def test_single_period_rising(self):
        """One period with +3% median and rising volume."""
        data = [{"med_pct": 3, "curr_vol": 12, "prev_vol": 10}]
        result = momentum_score(data)
        # med_pct > 2 => +1, vol_trend +1 => total 2
        assert result["score"] == 2
        assert result["label"] == "Heating Up"

    def test_single_period_flat(self):
        """One period with 1% change and flat volume."""
        data = [{"med_pct": 1, "curr_vol": 10, "prev_vol": 10}]
        result = momentum_score(data)
        # 1% not > 2 => 0, vol flat => 0
        assert result["score"] == 0
        assert result["label"] == "Stable"

    def test_mixed_signals(self):
        """Median up but volume down; partially cancel."""
        data = [
            {"med_pct": 5, "curr_vol": 8, "prev_vol": 10},   # med +1, vol will net -
            {"med_pct": 3, "curr_vol": 7, "prev_vol": 8},    # med +1, vol will net -
        ]
        result = momentum_score(data)
        # 2 median +1s = +2, vol_trend = -2 (both negative) => -1, total = +2-1 = +1
        assert result["score"] == 1
        assert result["label"] == "Warming"

    @pytest.mark.parametrize("score,label", list(MOMENTUM_LABELS.items()))
    def test_label_mapping(self, score, label):
        assert MOMENTUM_LABELS[score] == label


# ═══════════════════════════════════════════════════════════════════════
# analyze_trends
# ═══════════════════════════════════════════════════════════════════════


class TestAnalyzeTrends:
    def test_single_report_no_trends(self):
        result = analyze_trends([{"references": {"79830RB": _ref()}}])
        assert result["trends"] == []
        assert result["momentum"] == {}
        assert result["period_count"] == 1
        assert "no trend" in result["note"].lower()

    def test_zero_reports(self):
        result = analyze_trends([])
        assert result["trends"] == []
        assert result["period_count"] == 0

    def test_two_periods(self):
        p1 = {"references": {"79830RB": _ref(median=3200, volume=12)}}
        p0 = {"references": {"79830RB": _ref(median=3000, volume=10)}}
        result = analyze_trends([p1, p0])  # newest first
        assert len(result["trends"]) == 1
        assert result["trends"][0]["med_change"] == 200
        assert "79830RB" in result["momentum"]

    def test_three_periods_momentum(self):
        """3 periods of rising median => momentum score > 0."""
        p2 = {"references": {"79830RB": _ref(median=3400, volume=14)}}
        p1 = {"references": {"79830RB": _ref(median=3200, volume=12)}}
        p0 = {"references": {"79830RB": _ref(median=3000, volume=10)}}
        result = analyze_trends([p2, p1, p0])
        assert result["period_count"] == 3
        m = result["momentum"]["79830RB"]
        assert m["score"] > 0

    def test_latest_trends_use_newest_pair(self):
        """trends list comes from periods[0] vs periods[1] only."""
        p2 = {"references": {"79830RB": _ref(median=3400)}}
        p1 = {"references": {"79830RB": _ref(median=3200)}}
        p0 = {"references": {"79830RB": _ref(median=3000)}}
        result = analyze_trends([p2, p1, p0])
        # Latest pair is p2 vs p1
        assert result["trends"][0]["prev_median"] == 3200
        assert result["trends"][0]["curr_median"] == 3400


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


class TestCLI:
    def test_single_csv_no_trends(self):
        r = run_cli(SALES_CSV, "--name-cache", NAME_CACHE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["trends"] == []
        assert "no trend" in (data.get("note") or "").lower()

    def test_two_csvs_produce_trends(self, tmp_path):
        """Same CSV twice simulates two periods with identical data."""
        import shutil
        csv2 = tmp_path / "period2.csv"
        shutil.copy(SALES_CSV, csv2)
        r = run_cli(SALES_CSV, str(csv2), "--name-cache", NAME_CACHE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["period_count"] == 2
        # Same data both periods => all trends are Stable
        for t in data["trends"]:
            assert t["signal_str"] == "Stable"

    def test_missing_csv_fails(self):
        r = run_cli("/tmp/nonexistent.csv")
        assert r.returncode != 0
