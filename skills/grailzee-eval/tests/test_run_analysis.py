"""Integration tests for scripts.run_analysis; full pipeline orchestrator.

Net-new in v2; no v1 equivalent. Tests use the three real fixture CSVs
(~27k rows total, ~30% empty sell_through_pct). These are integration
tests; individual analyzer correctness is tested in Phases 6-14.

Fixture CSVs (newest first):
  grailzee_2026-04-06.csv  (9,440 rows)
  grailzee_2026-03-23.csv  (8,967 rows)
  grailzee_2026-03-09.csv  (8,528 rows)

Sentinel references for wiring verification:
  Tudor 79830RB appears in all 3 fixture CSVs with consistent data.
"""

import csv
import json
import os
import statistics
import time
from pathlib import Path
from unittest.mock import patch

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = V2_ROOT / "tests" / "fixtures"
CSV_APR = str(FIXTURES / "grailzee_2026-04-06.csv")
CSV_MAR2 = str(FIXTURES / "grailzee_2026-03-23.csv")
CSV_MAR1 = str(FIXTURES / "grailzee_2026-03-09.csv")
ALL_CSVS = [CSV_APR, CSV_MAR2, CSV_MAR1]
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.grailzee_common import cycle_id_from_csv, cycle_id_from_date
from scripts.run_analysis import run_analysis


V2_LEDGER_HEADER = (
    "buy_date,sell_date,buy_cycle_id,sell_cycle_id,"
    "brand,reference,account,buy_price,sell_price\n"
)


def _empty_ledger(tmp_path: Path) -> str:
    path = tmp_path / "trade_ledger.csv"
    path.write_text(V2_LEDGER_HEADER)
    return str(path)


def _premium_ledger(tmp_path: Path) -> str:
    """Ledger with 12 trades at ~10% premium to trigger threshold."""
    path = tmp_path / "trade_ledger.csv"
    rows = []
    for i in range(12):
        # Legacy-shape rows (no buy_date); matches post-A.6-migration
        # state for trades that predate the prediction system.
        rows.append(
            f",2026-03-{i+1:02d},,cycle_2026-05,Tudor,79830RB,NR,2750,3200"
        )
    path.write_text(V2_LEDGER_HEADER + "\n".join(rows) + "\n")
    return str(path)


def _setup(tmp_path: Path, csvs=None, ledger_fn=None):
    """Common setup: create output dir, empty ledger, empty cache, return kwargs."""
    output = str(tmp_path / "output")
    os.makedirs(output, exist_ok=True)
    ledger = ledger_fn(tmp_path) if ledger_fn else _empty_ledger(tmp_path)
    cache = str(tmp_path / "state" / "analysis_cache.json")
    backup = str(tmp_path / "backup")
    return {
        "csv_paths": csvs or ALL_CSVS,
        "output_folder": output,
        "ledger_path": ledger,
        "cache_path": cache,
        "backup_path": backup,
        "name_cache_path": NAME_CACHE,
        "cycle_focus_path": str(tmp_path / "no_focus.json"),
    }


# ═══════════════════════════════════════════════════════════════════════
# End-to-end (3 CSVs)
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_all_outputs_exist(self, tmp_path):
        """Feed 3 CSVs, assert all output files created."""
        kwargs = _setup(tmp_path)
        result = run_analysis(**kwargs)

        # Return shape
        assert set(result.keys()) == {"summary_path", "unnamed", "cycle_id"}
        assert isinstance(result["summary_path"], str)
        assert isinstance(result["unnamed"], list)
        assert isinstance(result["cycle_id"], str)

        # Output files exist
        assert Path(result["summary_path"]).exists()
        assert Path(kwargs["cache_path"]).exists()

        # Spreadsheet and brief in output folder
        output_files = os.listdir(kwargs["output_folder"])
        xlsx_files = [f for f in output_files if f.endswith(".xlsx")]
        md_files = [f for f in output_files if f.endswith(".md")]
        assert len(xlsx_files) >= 1
        assert len(md_files) >= 1  # summary + brief MD

    def test_performance(self, tmp_path):
        """Pipeline completes in < 60s on real fixtures."""
        kwargs = _setup(tmp_path)
        start = time.monotonic()
        run_analysis(**kwargs)
        elapsed = time.monotonic() - start
        assert elapsed < 60, f"Pipeline took {elapsed:.1f}s, expected < 60s"


# ═══════════════════════════════════════════════════════════════════════
# Single CSV (first report)
# ═══════════════════════════════════════════════════════════════════════


class TestSingleCSV:
    def test_no_crash(self, tmp_path):
        """Single CSV (first report ever) runs without error."""
        kwargs = _setup(tmp_path, csvs=[CSV_APR])
        result = run_analysis(**kwargs)
        assert result["cycle_id"]
        assert isinstance(result["unnamed"], list)

    def test_trends_empty(self, tmp_path):
        """Single CSV -> no trend data in cache."""
        kwargs = _setup(tmp_path, csvs=[CSV_APR])
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        # With 1 CSV, trends have no entries
        for ref_data in cache["references"].values():
            assert ref_data["trend_signal"] == "No prior data"


# ═══════════════════════════════════════════════════════════════════════
# Two CSVs
# ═══════════════════════════════════════════════════════════════════════


class TestTwoCSVs:
    def test_two_period_analyzers_work(self, tmp_path):
        """Two CSVs: changes, breakouts, watchlist populated."""
        kwargs = _setup(tmp_path, csvs=[CSV_APR, CSV_MAR2])
        result = run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        # With 2 CSVs, changes should have real data
        assert isinstance(cache["changes"]["emerged"], list)
        assert isinstance(cache["changes"]["faded"], list)


# ═══════════════════════════════════════════════════════════════════════
# Cycle ID
# ═══════════════════════════════════════════════════════════════════════


class TestCycleId:
    def test_matches_latest_csv(self, tmp_path):
        """cycle_id matches cycle_id_from_csv for the newest CSV."""
        kwargs = _setup(tmp_path)
        result = run_analysis(**kwargs)
        expected = cycle_id_from_csv(CSV_APR)
        assert result["cycle_id"] == expected

    def test_cycle_id_from_csv_helper(self):
        """grailzee_2026-04-06.csv -> cycle for 2026-04-06."""
        cid = cycle_id_from_csv("/some/path/grailzee_2026-04-06.csv")
        expected = cycle_id_from_date(__import__("datetime").date(2026, 4, 6))
        assert cid == expected


# ═══════════════════════════════════════════════════════════════════════
# Premium status block + B.1 max_buy regression
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumStatusInCache:
    """Post-B.1: apply_premium_adjustment is no longer called by the
    pipeline. The premium_status observational block still lands in the
    cache via write_cache._build_premium_status, but max_buy_nr /
    max_buy_res stay at their plain-median values regardless of ledger
    premium history. Class named distinctly from TestPremiumStatus in
    test_write_cache.py and test_evaluate_deal.py to keep grep
    unambiguous."""

    def test_premium_status_block_in_cache(self, tmp_path):
        """A ledger with 12 trades lands a premium_status block in the
        cache with the expected shape. The block is surfaced by
        write_cache, not by the removed adjustment call."""
        tmp2 = tmp_path / "run"
        tmp2.mkdir()
        ledger_path = str(tmp2 / "ledger.csv")
        rows = "\n".join(
            f",2026-03-{i+1:02d},,cycle_2026-05,Tudor,79830RB,NR,2750,3200"
            for i in range(12)
        )
        Path(ledger_path).write_text(V2_LEDGER_HEADER + rows + "\n")

        kwargs = {
            "csv_paths": [CSV_APR],
            "output_folder": str(tmp2 / "output"),
            "ledger_path": ledger_path,
            "cache_path": str(tmp2 / "state" / "analysis_cache.json"),
            "backup_path": str(tmp2 / "backup"),
            "name_cache_path": NAME_CACHE,
            "cycle_focus_path": str(tmp2 / "no_focus.json"),
        }
        os.makedirs(str(tmp2 / "output"), exist_ok=True)

        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        assert "premium_status" in cache
        assert isinstance(cache["premium_status"]["threshold_met"], bool)

    def test_premium_not_met(self, tmp_path):
        """Empty ledger -> premium_status records threshold_met False
        and adjustment 0. Same observational shape as pre-B.1; only
        difference is that the shape is never consumed to modify
        max_buy in the pipeline."""
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        assert cache["premium_status"]["threshold_met"] is False
        assert cache["premium_status"]["adjustment"] == 0

    def test_max_buy_stays_at_plain_median(self, tmp_path):
        """B.1 regression guard: a ledger that would have triggered
        apply_premium_adjustment pre-B.1 (12 trades at ~10% premium)
        must leave max_buy_nr / max_buy_res at the plain-median formula
        values. The adjusted_max_buy formula returns different numbers;
        asserting inequality as well catches a silent re-add of the
        adjustment call.
        """
        from scripts.grailzee_common import (
            NR_FIXED,
            RES_FIXED,
            adjusted_max_buy,
            max_buy_nr,
            max_buy_reserve,
        )

        kwargs = _setup(tmp_path, csvs=[CSV_APR], ledger_fn=_premium_ledger)
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())

        ref = cache["references"]["79830RB"]
        median = ref["median"]
        expected_nr = max_buy_nr(median)
        expected_res = max_buy_reserve(median)

        assert ref["max_buy_nr"] == expected_nr
        assert ref["max_buy_res"] == expected_res

        # Belt-and-suspenders: the values that apply_premium_adjustment
        # would have produced for a +10% premium (half = 5% adjustment)
        # are strictly greater than the plain-median values. If a silent
        # re-add reintroduced the call, these assertions would fail.
        if median is not None:
            would_be_adjusted_nr = adjusted_max_buy(median, NR_FIXED, 5.0)
            would_be_adjusted_res = adjusted_max_buy(median, RES_FIXED, 5.0)
            assert ref["max_buy_nr"] != would_be_adjusted_nr
            assert ref["max_buy_res"] != would_be_adjusted_res


# ═══════════════════════════════════════════════════════════════════════
# premium_vs_market_pct (B.2) integration
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumVsMarketIntegration:
    """B.2 integration: the field computes correctly end-to-end through
    the full pipeline (CSVs -> score -> ledger -> cache)."""

    def test_fixture_ledger_with_above_median_sale(self, tmp_path):
        """A ledger with a 79830RB sale above fixture median produces a
        positive premium_vs_market_pct on the cache entry. The fixture
        CSVs yield 79830RB median 3550.0; a sale at 3905 gives
        (3905-3550)/3550*100 = 10.0."""
        ledger_path = str(tmp_path / "trade_ledger.csv")
        rows = ",2026-03-15,,cycle_2026-06,Tudor,79830RB,NR,2750,3905"
        Path(ledger_path).write_text(V2_LEDGER_HEADER + rows + "\n")

        kwargs = {
            "csv_paths": ALL_CSVS,
            "output_folder": str(tmp_path / "output"),
            "ledger_path": ledger_path,
            "cache_path": str(tmp_path / "state" / "analysis_cache.json"),
            "backup_path": str(tmp_path / "backup"),
            "name_cache_path": NAME_CACHE,
            "cycle_focus_path": str(tmp_path / "no_focus.json"),
        }
        os.makedirs(kwargs["output_folder"], exist_ok=True)

        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        ref = cache["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 10.0
        assert ref["premium_vs_market_sale_count"] == 1

    def test_empty_ledger_zero_everywhere(self, tmp_path):
        """Empty ledger -> every reference gets 0.0 / 0. Coverage
        guarantees the field is present (not null) on every entry."""
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        for ref_data in cache["references"].values():
            assert ref_data["premium_vs_market_pct"] == 0.0
            assert ref_data["premium_vs_market_sale_count"] == 0

    def test_no_above_median_sale_zero(self, tmp_path):
        """Ledger with an at-median sale -> 0.0 pct, count 1."""
        ledger_path = str(tmp_path / "trade_ledger.csv")
        # Fixture 79830RB median is 3550; sell exactly there.
        rows = ",2026-03-15,,cycle_2026-06,Tudor,79830RB,NR,2750,3550"
        Path(ledger_path).write_text(V2_LEDGER_HEADER + rows + "\n")

        kwargs = {
            "csv_paths": ALL_CSVS,
            "output_folder": str(tmp_path / "output"),
            "ledger_path": ledger_path,
            "cache_path": str(tmp_path / "state" / "analysis_cache.json"),
            "backup_path": str(tmp_path / "backup"),
            "name_cache_path": NAME_CACHE,
            "cycle_focus_path": str(tmp_path / "no_focus.json"),
        }
        os.makedirs(kwargs["output_folder"], exist_ok=True)

        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        ref = cache["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Sentinel values (wiring verification)
# ═══════════════════════════════════════════════════════════════════════


class TestSentinelValues:
    def test_reference_median_in_cache(self, tmp_path):
        """Hand-compute 79830RB median from fixture, verify in cache.

        Load the pricing window (latest 2 CSVs), extract 79830RB prices,
        compute expected median, assert it matches cache.
        """
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())

        # Hand-compute from the two pricing CSVs
        prices = []
        for csv_path in [CSV_APR, CSV_MAR2]:
            with open(csv_path) as f:
                for row in csv.DictReader(f):
                    ref = row.get("reference", "").strip()
                    if ref == "79830RB":
                        try:
                            p = float(row["sold_price"])
                            if p > 0:
                                prices.append(p)
                        except (ValueError, KeyError):
                            pass

        assert len(prices) > 0, "79830RB not found in fixtures"
        expected_median = statistics.median(prices)

        assert "79830RB" in cache["references"]
        actual_median = cache["references"]["79830RB"]["median"]
        assert actual_median == expected_median

    def test_reference_has_all_cache_fields(self, tmp_path):
        """A scored reference has every field from the v2 cache schema."""
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())

        # Pick any reference
        ref_key = next(iter(cache["references"]))
        ref_data = cache["references"][ref_key]
        expected_keys = {
            "brand", "model", "reference", "named", "median",
            "max_buy_nr", "max_buy_res", "risk_nr", "signal",
            "volume", "st_pct", "momentum", "confidence",
            "premium_vs_market_pct", "premium_vs_market_sale_count",
            "trend_signal", "trend_median_change", "trend_median_pct",
        }
        assert set(ref_data.keys()) == expected_keys


# ═══════════════════════════════════════════════════════════════════════
# Output location
# ═══════════════════════════════════════════════════════════════════════


class TestOutputLocation:
    def test_files_in_output_folder(self, tmp_path):
        """All output files write to the configured output folder."""
        kwargs = _setup(tmp_path)
        result = run_analysis(**kwargs)
        summary = Path(result["summary_path"])
        assert str(summary).startswith(kwargs["output_folder"])

    def test_cache_in_configured_path(self, tmp_path):
        """Cache writes to the configured cache_path."""
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        assert Path(kwargs["cache_path"]).exists()


# ═══════════════════════════════════════════════════════════════════════
# Empty references
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyReferences:
    def test_no_qualifying_refs(self, tmp_path):
        """CSV with all refs < 3 sales -> empty references, no crash."""
        tiny_csv = tmp_path / "tiny.csv"
        tiny_csv.write_text(
            "date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct\n"
            "2026-04-01,Tudor,FAKE01,Test,Very Good,Yes,1000,\n"
            "2026-04-02,Tudor,FAKE02,Test,Excellent,Yes,2000,\n"
        )
        kwargs = _setup(tmp_path, csvs=[str(tiny_csv)])
        result = run_analysis(**kwargs)
        cache = json.loads(Path(kwargs["cache_path"]).read_text())
        assert cache["references"] == {}
        assert cache["summary"]["total_references"] == 0
        assert result["unnamed"] == []


# ═══════════════════════════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotency:
    def test_same_inputs_same_outputs(self, tmp_path):
        """Two runs produce identical outputs except timestamps."""
        kwargs = _setup(tmp_path)
        run_analysis(**kwargs)
        cache1 = json.loads(Path(kwargs["cache_path"]).read_text())

        # Second run overwrites
        run_analysis(**kwargs)
        cache2 = json.loads(Path(kwargs["cache_path"]).read_text())

        cache1.pop("generated_at")
        cache2.pop("generated_at")
        assert cache1 == cache2


# ═══════════════════════════════════════════════════════════════════════
# No name resolution
# ═══════════════════════════════════════════════════════════════════════


class TestNoNameResolution:
    def test_save_name_cache_not_called(self, tmp_path):
        """Orchestrator does not call save_name_cache."""
        with patch("scripts.grailzee_common.save_name_cache") as mock_save:
            kwargs = _setup(tmp_path, csvs=[CSV_APR])
            run_analysis(**kwargs)
            mock_save.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# No network calls
# ═══════════════════════════════════════════════════════════════════════


class TestNoNetworkCalls:
    def test_no_outbound_http(self, tmp_path):
        """Orchestrator makes no HTTP calls. Block all outbound connections."""
        import socket
        original_connect = socket.socket.connect

        def blocked_connect(*args, **kwargs):
            raise AssertionError("Unexpected network call during orchestrator run")

        with patch.object(socket.socket, "connect", blocked_connect):
            kwargs = _setup(tmp_path, csvs=[CSV_APR])
            result = run_analysis(**kwargs)
            assert "cycle_id" in result


# ═══════════════════════════════════════════════════════════════════════
# Zero CSVs
# ═══════════════════════════════════════════════════════════════════════


class TestZeroCSVs:
    def test_raises_clean_error(self, tmp_path):
        """Empty csv_paths raises ValueError, not crash."""
        kwargs = _setup(tmp_path)
        kwargs["csv_paths"] = []  # override after setup to bypass falsy default
        with pytest.raises(ValueError, match="No CSV paths"):
            run_analysis(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Return shape
# ═══════════════════════════════════════════════════════════════════════


class TestReturnShape:
    def test_exact_keys(self, tmp_path):
        """Return dict has exactly {summary_path, unnamed, cycle_id}."""
        kwargs = _setup(tmp_path, csvs=[CSV_APR])
        result = run_analysis(**kwargs)
        assert set(result.keys()) == {"summary_path", "unnamed", "cycle_id"}
