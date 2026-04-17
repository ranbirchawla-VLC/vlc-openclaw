"""Tests for scripts.analyze_breakouts; breakout detection per guide Section 7.3.

New in v2; no v1 equivalent. All tests hand-computed from guide spec.

Thresholds:
  median: abs(delta) > 8% (strict, not >=)
  volume: curr > prev * 2 AND prev >= 3 (strict >)
  sell-through: delta > 15pp (strict, not >=)
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "analyze_breakouts.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SALES_CSV = str(FIXTURES / "sales_sample.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_breakouts import detect_breakouts


def _ref(median=3000, volume=10, st_pct=0.50):
    return {"median": median, "volume": volume, "st_pct": st_pct}


# ═══════════════════════════════════════════════════════════════════════
# Individual signals
# ═══════════════════════════════════════════════════════════════════════


class TestMedianSignal:
    def test_median_up_10_pct(self):
        """3000 -> 3300 = +10% > 8% => signal fires."""
        curr = {"R": _ref(median=3300)}
        prev = {"R": _ref(median=3000)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert any("Median" in s for s in result[0]["signals"])

    def test_median_down_10_pct(self):
        """3000 -> 2700 = -10% => signal fires (absolute value)."""
        curr = {"R": _ref(median=2700)}
        prev = {"R": _ref(median=3000)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert any("Median" in s and "-" in s for s in result[0]["signals"])

    def test_median_at_exactly_8_pct_no_signal(self):
        """3000 -> 3240 = exactly 8.0%; >8 is false => no signal."""
        curr = {"R": _ref(median=3240)}
        prev = {"R": _ref(median=3000)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0

    def test_median_just_over_8_pct(self):
        """3000 -> 3243 = 8.1% > 8% => signal fires."""
        curr = {"R": _ref(median=3243)}
        prev = {"R": _ref(median=3000)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1


class TestVolumeSignal:
    def test_volume_surge(self):
        """3 -> 7: 7 > 3*2=6 AND prev=3>=3 => signal fires."""
        curr = {"R": _ref(volume=7)}
        prev = {"R": _ref(volume=3)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert any("Volume surge" in s for s in result[0]["signals"])

    def test_volume_exactly_2x_no_signal(self):
        """3 -> 6: 6 > 6 is false (strict >) => no signal."""
        curr = {"R": _ref(volume=6)}
        prev = {"R": _ref(volume=3)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0

    def test_volume_prev_below_3_suppressed(self):
        """2 -> 5: prev=2 < 3 => volume signal suppressed."""
        curr = {"R": _ref(volume=5)}
        prev = {"R": _ref(volume=2)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0

    def test_volume_prev_exactly_3(self):
        """3 -> 7: prev=3>=3, 7>6 => fires."""
        curr = {"R": _ref(volume=7)}
        prev = {"R": _ref(volume=3)}
        result = detect_breakouts(curr, prev)
        assert any("Volume" in s for s in result[0]["signals"])


class TestSellThroughSignal:
    def test_st_spike_16pp(self):
        """0.50 -> 0.66 = +16pp > 15pp => signal fires."""
        curr = {"R": _ref(st_pct=0.66)}
        prev = {"R": _ref(st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert any("Sell-through" in s for s in result[0]["signals"])

    def test_st_exactly_15pp_no_signal(self):
        """0.50 -> 0.65 = exactly 15pp; >15 is false => no signal."""
        curr = {"R": _ref(st_pct=0.65)}
        prev = {"R": _ref(st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0

    def test_st_decrease_no_signal(self):
        """Sell-through decrease never triggers (only increases)."""
        curr = {"R": _ref(st_pct=0.30)}
        prev = {"R": _ref(st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0

    def test_st_none_no_signal(self):
        """Missing sell-through data => no signal."""
        curr = {"R": _ref(st_pct=None)}
        prev = {"R": _ref(st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════
# Multi-signal and aggregation
# ═══════════════════════════════════════════════════════════════════════


class TestMultiSignal:
    def test_all_three_signals(self):
        """Reference trips median + volume + sell-through simultaneously."""
        curr = {"R": _ref(median=3360, volume=10, st_pct=0.70)}
        prev = {"R": _ref(median=3000, volume=4, st_pct=0.50)}
        # median: +12% > 8% => fires
        # volume: 10 > 4*2=8 and prev=4>=3 => fires
        # st: (0.70-0.50)*100 = 20pp > 15 => fires
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert len(result[0]["signals"]) == 3

    def test_one_signal_suffices(self):
        """Only median fires; reference still qualifies as breakout."""
        curr = {"R": _ref(median=3300, volume=10, st_pct=0.55)}
        prev = {"R": _ref(median=3000, volume=10, st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 1
        assert len(result[0]["signals"]) == 1

    def test_no_signals_excluded(self):
        """No threshold tripped => not a breakout."""
        curr = {"R": _ref(median=3100, volume=10, st_pct=0.55)}
        prev = {"R": _ref(median=3000, volume=10, st_pct=0.50)}
        result = detect_breakouts(curr, prev)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_single_report_no_breakouts(self):
        """No previous period => empty breakout list."""
        curr = {"R": _ref()}
        result = detect_breakouts(curr, {})
        assert result == []

    def test_ref_only_in_curr_skipped(self):
        """Emerged ref not in prev => not compared, not a breakout."""
        curr = {"NEW": _ref(median=5000)}
        prev = {"OLD": _ref(median=3000)}
        result = detect_breakouts(curr, prev)
        assert result == []

    def test_prev_median_zero_skipped(self):
        """prev_median=0 => division guard, no median signal."""
        curr = {"R": _ref(median=3000)}
        prev = {"R": _ref(median=0)}
        result = detect_breakouts(curr, prev)
        # Volume and ST might still fire, but median won't
        median_signals = [s for b in result for s in b["signals"] if "Median" in s]
        assert len(median_signals) == 0

    def test_multiple_refs(self):
        """Two refs; one breaks out, one doesn't."""
        curr = {
            "A": _ref(median=3300),
            "B": _ref(median=3050),
        }
        prev = {
            "A": _ref(median=3000),
            "B": _ref(median=3000),
        }
        result = detect_breakouts(curr, prev)
        refs = [b["reference"] for b in result]
        assert "A" in refs
        assert "B" not in refs

    def test_both_empty(self):
        assert detect_breakouts({}, {}) == []


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


class TestCLI:
    def test_single_csv_no_breakouts(self):
        r = run_cli(SALES_CSV, "--name-cache", NAME_CACHE)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["breakouts"] == []
        assert data["count"] == 0

    def test_two_identical_csvs_no_breakouts(self, tmp_path):
        import shutil
        csv2 = tmp_path / "prev.csv"
        shutil.copy(SALES_CSV, csv2)
        r = run_cli(SALES_CSV, str(csv2), "--name-cache", NAME_CACHE)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["count"] == 0

    def test_missing_csv_fails(self):
        r = run_cli("/tmp/nonexistent.csv")
        assert r.returncode != 0

    def test_stdout_valid_json(self):
        r = run_cli(SALES_CSV, "--name-cache", NAME_CACHE)
        json.loads(r.stdout)
