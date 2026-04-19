"""Tests for scripts.read_ledger — ledger read, derived fields, aggregation."""

from datetime import date
from pathlib import Path

import pytest

from scripts.read_ledger import (
    cycle_rollup,
    reference_confidence,
    run,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_LEDGER = str(FIXTURES / "trade_ledger_sample.csv")
SAMPLE_CACHE = str(FIXTURES / "analysis_cache_sample.json")


# ═══════════════════════════════════════════════════════════════════════
# Fixture financial verification (hand-computed in prompt)
#
# Row 1: 79830RB NR 2750->3200: gross=450 fees=149 net=301 roi=10.95%
# Row 2: 91650   NR 1500->1675: gross=175 fees=149 net=26  roi=1.73%
# Row 3: 79230R  NR 2800->3150: gross=350 fees=149 net=201 roi=7.18%
# Row 4: 28600  RES 4200->4750: gross=550 fees=199 net=351 roi=8.36%
# Row 5: 79830RB NR 1900->2100: gross=200 fees=149 net=51  roi=2.68%
# Row 6: A17320  NR 2100->2350: gross=250 fees=149 net=101 roi=4.81%
#
# Total net: 1031.00  Profitable: 6/6  Avg ROI: 5.95%
# ═══════════════════════════════════════════════════════════════════════


class TestRunSummary:
    """run() on the full sample ledger without cache.

    All tests pass an explicit nonexistent cache path so the real
    Drive cache never leaks into test assertions.
    """
    NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"

    def test_total_trades(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        assert result["summary"]["total_trades"] == 6

    def test_total_net_profit(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        assert result["summary"]["total_net_profit"] == 1031.00

    def test_profitable_count(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        assert result["summary"]["profitable"] == 6

    def test_avg_roi(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        assert abs(result["summary"]["avg_roi_pct"] - 5.95) < 0.05

    def test_per_trade_roi_values(self):
        """Verify each trade's ROI matches hand computation."""
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        expected_rois = [10.95, 1.73, 7.18, 8.36, 2.68, 4.81]
        actual_rois = [t["roi_pct"] for t in result["trades"]]
        for exp, act in zip(expected_rois, actual_rois):
            assert abs(act - exp) < 0.01, f"Expected {exp}, got {act}"

    def test_per_trade_net_values(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        expected_nets = [301, 26, 201, 351, 51, 101]
        actual_nets = [t["net_profit"] for t in result["trades"]]
        assert actual_nets == expected_nets

    def test_res_trade_uses_199_fee(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE)
        res_trade = [t for t in result["trades"] if t["account"] == "RES"][0]
        assert res_trade["platform_fees"] == 199


class TestRunFilters:
    NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"

    def test_filter_by_brand(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     brand="Tudor")
        assert result["summary"]["total_trades"] == 5

    def test_filter_by_brand_case_insensitive(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     brand="tudor")
        assert result["summary"]["total_trades"] == 5

    def test_filter_by_reference(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     reference="79830RB")
        assert result["summary"]["total_trades"] == 2

    def test_filter_by_since(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     since=date(2026, 1, 1))
        assert result["summary"]["total_trades"] == 3

    def test_filter_by_cycle_id(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     cycle_id="cycle_2026-01")
        assert result["summary"]["total_trades"] == 1

    def test_empty_result(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
                     brand="Patek")
        assert result["summary"]["total_trades"] == 0
        assert result["summary"]["avg_roi_pct"] == 0


class TestRunWithCache:
    """Derived fields when cache is available."""

    def test_median_at_trade_populated(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=SAMPLE_CACHE,
                     reference="79830RB")
        for trade in result["trades"]:
            assert trade["median_at_trade"] == 3150

    def test_premium_vs_median_computed(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=SAMPLE_CACHE,
                     reference="79830RB")
        # First 79830RB trade: sell=3200, median=3150
        # premium = ((3200 - 3150) / 3150) * 100 = 1.59%
        first = result["trades"][0]
        assert abs(first["premium_vs_median"] - 1.59) < 0.01

    def test_model_correct_true(self):
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=SAMPLE_CACHE,
                     reference="79830RB")
        # First trade: buy=2750, max_buy_nr=2860, net=301>0 => True
        assert result["trades"][0]["model_correct"] is True

    def test_derived_fields_none_without_cache(self, tmp_path):
        """Cache-dependent fields are None when cache doesn't exist."""
        no_cache = str(tmp_path / "nonexistent_cache.json")
        result = run(ledger_path=SAMPLE_LEDGER, cache_path=no_cache,
                     reference="79830RB")
        for trade in result["trades"]:
            assert trade["median_at_trade"] is None
            assert trade["premium_vs_median"] is None
            assert trade["model_correct"] is None


class TestReferenceConfidence:
    NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"

    def test_known_reference(self):
        result = reference_confidence(
            ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
            brand="Tudor", reference="79830RB")
        assert result is not None
        assert result["trades"] == 2
        assert result["profitable"] == 2
        assert result["win_rate"] == 100.0

    def test_unknown_reference_returns_none(self):
        result = reference_confidence(
            ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
            brand="Patek", reference="5711")
        assert result is None

    def test_case_insensitive_brand(self):
        result = reference_confidence(
            ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
            brand="tudor", reference="79830RB")
        assert result is not None
        assert result["trades"] == 2

    def test_single_trade_reference(self):
        result = reference_confidence(
            ledger_path=SAMPLE_LEDGER, cache_path=self.NO_CACHE,
            brand="Breitling", reference="A17320")
        assert result is not None
        assert result["trades"] == 1
        assert result["avg_roi"] == 4.8


class TestCycleRollup:
    NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"

    def test_known_cycle(self):
        result = cycle_rollup("cycle_2026-01", ledger_path=SAMPLE_LEDGER,
                              cache_path=self.NO_CACHE)
        assert result["cycle_id"] == "cycle_2026-01"
        assert result["summary"]["total_trades"] == 1

    def test_empty_cycle_returns_zeros(self):
        result = cycle_rollup("cycle_2026-99", ledger_path=SAMPLE_LEDGER,
                              cache_path=self.NO_CACHE)
        assert result["summary"]["total_trades"] == 0
        assert result["summary"]["avg_roi"] == 0
        assert result["summary"]["total_net"] == 0
        assert result["summary"]["capital_deployed"] == 0
        assert result["summary"]["capital_returned"] == 0

    def test_date_range_present(self):
        result = cycle_rollup("cycle_2026-01", ledger_path=SAMPLE_LEDGER,
                              cache_path=self.NO_CACHE)
        assert "start" in result["date_range"]
        assert "end" in result["date_range"]

    def test_with_cycle_focus(self):
        focus = {
            "cycle_id": "cycle_2026-01",
            "targets": [{"reference": "28600"}, {"reference": "79830RB"}],
        }
        result = cycle_rollup("cycle_2026-01", ledger_path=SAMPLE_LEDGER,
                              cache_path=self.NO_CACHE, cycle_focus=focus)
        assert result["cycle_focus"]["hits"] == ["28600"]
        assert result["cycle_focus"]["misses"] == ["79830RB"]
        assert result["summary"]["in_focus_count"] == 1
