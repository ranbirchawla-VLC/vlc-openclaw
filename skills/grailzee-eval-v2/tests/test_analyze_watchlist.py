"""Tests for scripts.analyze_watchlist; watchlist detection per guide Section 7.4.

New in v2; no v1 equivalent (v1 labeled <3-sale refs "Low data" and dropped them).

Qualification:
  current sales: 1 <= count <= 2  (strictly < 3)
  prior period: absent from prev_refs OR prev volume == 0

Hand-computed constants:
  1 sale at 2500 -> avg_price = 2500.0
  2 sales at 2100, 2300 -> avg_price = (2100+2300)/2 = 2200.0
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "analyze_watchlist.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SALES_CSV = str(FIXTURES / "sales_sample.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_watchlist import detect_watch_list


def _sale(price: float, ref: str = "TEST01") -> dict:
    return {
        "price": price,
        "condition": "Very Good",
        "papers": "Yes",
        "reference": ref,
        "make": "Test",
        "title": f"Test Watch {ref}",
    }


def _prev(volume: int = 5) -> dict:
    """Minimal scored reference dict with volume field."""
    return {"median": 3000, "volume": volume, "signal": "Strong"}


# ═══════════════════════════════════════════════════════════════════════
# Qualification: current sales count
# ═══════════════════════════════════════════════════════════════════════


class TestCurrentSalesThreshold:
    def test_1_sale_qualifies(self):
        """1 sale, no prior -> watchlist."""
        grouped = {"R1": [_sale(2500)]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 1
        assert result[0]["reference"] == "R1"
        assert result[0]["current_sales"] == 1
        assert result[0]["avg_price"] == 2500.0

    def test_2_sales_qualifies(self):
        """2 sales, no prior -> watchlist."""
        grouped = {"R1": [_sale(2100), _sale(2300)]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 1
        assert result[0]["current_sales"] == 2
        assert result[0]["avg_price"] == 2200.0

    def test_3_sales_excluded(self):
        """3 sales -> not watchlist (emerged / scoring territory)."""
        grouped = {"R1": [_sale(2000), _sale(2100), _sale(2200)]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 0

    def test_4_sales_excluded(self):
        """4 sales -> not watchlist."""
        grouped = {"R1": [_sale(p) for p in [2000, 2100, 2200, 2300]]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 0

    def test_empty_group_excluded(self):
        """Empty sales list -> not watchlist."""
        grouped = {"R1": []}
        result = detect_watch_list(grouped, {})
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════
# Qualification: prior period status
# ═══════════════════════════════════════════════════════════════════════


class TestPriorPeriod:
    def test_prior_absent_qualifies(self):
        """Reference not in prev_refs -> qualifies."""
        grouped = {"R1": [_sale(2500)]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 1

    def test_prior_volume_zero_qualifies(self):
        """Reference in prev_refs with volume=0 -> qualifies."""
        grouped = {"R1": [_sale(2500)]}
        prev = {"R1": _prev(volume=0)}
        result = detect_watch_list(grouped, prev)
        assert len(result) == 1

    def test_prior_volume_1_excluded(self):
        """Reference in prev_refs with volume=1 -> does NOT qualify."""
        grouped = {"R1": [_sale(2500)]}
        prev = {"R1": _prev(volume=1)}
        result = detect_watch_list(grouped, prev)
        assert len(result) == 0

    def test_prior_volume_3_excluded(self):
        """Reference in prev_refs with volume=3 -> does NOT qualify."""
        grouped = {"R1": [_sale(2500)]}
        prev = {"R1": _prev(volume=3)}
        result = detect_watch_list(grouped, prev)
        assert len(result) == 0

    def test_prior_missing_volume_key_qualifies(self):
        """prev_refs entry with no volume key -> volume defaults to 0 -> qualifies."""
        grouped = {"R1": [_sale(2500)]}
        prev = {"R1": {"median": 3000, "signal": "Low data"}}
        result = detect_watch_list(grouped, prev)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════
# avg_price calculation
# ═══════════════════════════════════════════════════════════════════════


class TestAvgPrice:
    def test_single_sale_avg(self):
        """1 sale at 2500 -> avg_price = 2500.0."""
        grouped = {"R1": [_sale(2500)]}
        result = detect_watch_list(grouped, {})
        assert result[0]["avg_price"] == 2500.0

    def test_two_sale_avg(self):
        """2 sales at 2100, 2300 -> avg_price = 2200.0."""
        grouped = {"R1": [_sale(2100), _sale(2300)]}
        result = detect_watch_list(grouped, {})
        assert result[0]["avg_price"] == 2200.0

    def test_two_sale_uneven_avg(self):
        """2 sales at 1999, 2001 -> avg_price = 2000.0."""
        grouped = {"R1": [_sale(1999), _sale(2001)]}
        result = detect_watch_list(grouped, {})
        assert result[0]["avg_price"] == 2000.0

    def test_extreme_price_no_suppression(self):
        """1 sale at 50000 -> no price floor suppression, avg_price = 50000.0."""
        grouped = {"R1": [_sale(50000)]}
        result = detect_watch_list(grouped, {})
        assert len(result) == 1
        assert result[0]["avg_price"] == 50000.0


# ═══════════════════════════════════════════════════════════════════════
# Mixed references
# ═══════════════════════════════════════════════════════════════════════


class TestMixedReferences:
    def test_mixed_filtering(self):
        """Multiple refs: only 1-2 sale refs with no prior qualify."""
        grouped = {
            "W1": [_sale(2500)],                             # 1 sale, no prior -> YES
            "W2": [_sale(2100), _sale(2300)],                # 2 sales, no prior -> YES
            "S1": [_sale(p) for p in [3000, 3100, 3200]],   # 3 sales -> NO
            "P1": [_sale(1800)],                             # 1 sale, has prior -> NO
        }
        prev = {"P1": _prev(volume=5)}
        result = detect_watch_list(grouped, prev)
        refs = [r["reference"] for r in result]
        assert refs == ["W1", "W2"]  # sorted

    def test_sorted_output(self):
        """Output is sorted by reference."""
        grouped = {
            "ZZZ": [_sale(1000)],
            "AAA": [_sale(2000)],
            "MMM": [_sale(3000)],
        }
        result = detect_watch_list(grouped, {})
        refs = [r["reference"] for r in result]
        assert refs == ["AAA", "MMM", "ZZZ"]


# ═══════════════════════════════════════════════════════════════════════
# Single-report edge case (no prior period)
# ═══════════════════════════════════════════════════════════════════════


class TestSingleReport:
    def test_all_low_count_refs_qualify(self):
        """No prior period -> all 1-2 sale refs are watchlist."""
        grouped = {
            "R1": [_sale(2500)],
            "R2": [_sale(2100), _sale(2300)],
            "R3": [_sale(p) for p in [3000, 3100, 3200]],  # 3 -> excluded
        }
        result = detect_watch_list(grouped, {})
        refs = [r["reference"] for r in result]
        assert refs == ["R1", "R2"]


# ═══════════════════════════════════════════════════════════════════════
# Output shape
# ═══════════════════════════════════════════════════════════════════════


class TestOutputShape:
    def test_output_keys(self):
        """Each watchlist entry has exactly reference, current_sales, avg_price."""
        grouped = {"R1": [_sale(2500)]}
        result = detect_watch_list(grouped, {})
        assert set(result[0].keys()) == {"reference", "current_sales", "avg_price"}

    def test_empty_input(self):
        """No sales -> empty watchlist."""
        result = detect_watch_list({}, {})
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Integration: run() with fixture CSVs
# ═══════════════════════════════════════════════════════════════════════


class TestRunIntegration:
    def test_fixture_single_report(self):
        """sales_sample.csv has 91650 with 2 sales -> watchlist candidate.

        91650 prices: 1500, 1600. avg_price = (1500+1600)/2 = 1550.0.
        79830RB has 5 sales, A17320 has 3, 126300 has 4 -> all excluded.
        """
        from scripts.analyze_watchlist import run

        result = run(SALES_CSV, name_cache_path=NAME_CACHE)
        assert result["count"] == 1
        assert result["watchlist"][0]["reference"] == "91650"
        assert result["watchlist"][0]["current_sales"] == 2
        assert result["watchlist"][0]["avg_price"] == 1550.0

    def test_fixture_with_prior_containing_ref(self, tmp_path):
        """When prior CSV scores 91650 (give it 3+ sales), it should be excluded."""
        from scripts.analyze_watchlist import run

        # Build a prior CSV where 91650 has 3 sales -> gets scored
        prior = tmp_path / "prior.csv"
        lines = [
            "date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct",
            "2026-01-01,Tudor,91650,Tudor 1926 41mm,Very Good,Yes,1400,",
            "2026-01-03,Tudor,91650,Tudor 1926 41mm,Excellent,Yes,1500,",
            "2026-01-05,Tudor,91650,Tudor 1926 41mm,Like New,Yes,1600,",
        ]
        prior.write_text("\n".join(lines) + "\n")

        result = run(SALES_CSV, str(prior), NAME_CACHE)
        refs = [w["reference"] for w in result["watchlist"]]
        assert "91650" not in refs
        assert result["count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:
    def test_json_output(self):
        """CLI produces valid JSON with watchlist and count keys."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), SALES_CSV, "--name-cache", NAME_CACHE],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert "watchlist" in data
        assert "count" in data
        assert isinstance(data["watchlist"], list)

    def test_missing_file_error(self, tmp_path):
        """Missing CSV -> nonzero exit, error on stderr."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path / "nope.csv")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        err = json.loads(proc.stderr)
        assert "error" in err

    def test_missing_prev_file_error(self, tmp_path):
        """Missing prev CSV -> nonzero exit, error on stderr."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), SALES_CSV, str(tmp_path / "nope.csv")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        err = json.loads(proc.stderr)
        assert "error" in err
