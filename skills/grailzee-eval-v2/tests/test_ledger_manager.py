"""Tests for scripts.ledger_manager — CLI contract tests via subprocess."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "ledger_manager.py"
FIXTURES = V2_ROOT / "tests" / "fixtures"
SAMPLE_LEDGER = str(FIXTURES / "trade_ledger_sample.csv")
SAMPLE_CACHE = str(FIXTURES / "analysis_cache_sample.json")
NO_CACHE = "/tmp/_grailzee_test_no_such_cache.json"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


class TestLogCommand:
    def test_log_creates_trade(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("--ledger", ledger, "--cache", NO_CACHE,
                     "log", "Tudor", "79830RB", "NR", "2750", "3200",
                     "--date", "2026-04-16")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["status"] == "ok"
        assert data["trade"]["brand"] == "Tudor"
        assert data["trade"]["cycle_id"].startswith("cycle_2026-")

    def test_log_invalid_account_exits_2(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("--ledger", ledger, "log", "Tudor", "79830RB",
                     "INVALID", "2750", "3200")
        assert r.returncode == 2

    def test_log_invalid_price_exits_2(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("--ledger", ledger, "log", "Tudor", "79830RB",
                     "NR", "abc", "3200")
        assert r.returncode == 2

    def test_log_preserves_existing_rows(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        # Log two trades
        run_cli("--ledger", ledger, "--cache", NO_CACHE,
                "log", "Tudor", "79830RB", "NR", "2750", "3200",
                "--date", "2026-04-01")
        run_cli("--ledger", ledger, "--cache", NO_CACHE,
                "log", "Omega", "21030422003001", "NR", "3000", "3500",
                "--date", "2026-04-02")
        # Summary should show 2
        r = run_cli("--ledger", ledger, "--cache", NO_CACHE, "summary")
        data = json.loads(r.stdout)
        assert data["summary"]["total_trades"] == 2

    def test_log_negative_price_exits_2(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("--ledger", ledger, "log", "Tudor", "79830RB",
                     "NR", "-100", "3200")
        assert r.returncode == 2

    def test_log_invalid_date_exits_2(self, tmp_path):
        ledger = str(tmp_path / "ledger.csv")
        r = run_cli("--ledger", ledger, "log", "Tudor", "79830RB",
                     "NR", "2750", "3200", "--date", "not-a-date")
        assert r.returncode == 2


class TestSummaryCommand:
    def test_summary_returns_json(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE, "summary")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_trades"] == 6

    def test_summary_with_brand_filter(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "summary", "--brand", "Tudor")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_trades"] == 5

    def test_summary_with_reference_filter(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "summary", "--reference", "79830RB")
        data = json.loads(r.stdout)
        assert data["summary"]["total_trades"] == 2

    def test_summary_with_cache(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", SAMPLE_CACHE,
                     "summary", "--reference", "79830RB")
        data = json.loads(r.stdout)
        # With cache, median_at_trade should be populated
        assert data["trades"][0]["median_at_trade"] == 3150

    def test_summary_stdout_is_valid_json(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE, "summary")
        json.loads(r.stdout)  # should not raise


class TestPremiumCommand:
    def test_premium_returns_json(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE, "premium")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "threshold_met" in data
        assert "trade_count" in data
        assert "adjustment" in data

    def test_premium_with_cache(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", SAMPLE_CACHE,
                     "premium")
        data = json.loads(r.stdout)
        # Only 2 refs in cache; some trades will have premium data
        assert data["trade_count"] >= 0


class TestCycleRollupCommand:
    def test_cycle_rollup_returns_json(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "cycle_rollup", "cycle_2026-01")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["cycle_id"] == "cycle_2026-01"
        assert data["summary"]["total_trades"] == 1

    def test_cycle_rollup_empty_cycle(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "cycle_rollup", "cycle_2099-01")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_trades"] == 0

    def test_cycle_rollup_with_focus(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus_path.write_text(json.dumps({
            "cycle_id": "cycle_2026-01",
            "targets": [{"reference": "28600"}],
        }))
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "cycle_rollup", "cycle_2026-01",
                     "--focus", str(focus_path))
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["cycle_focus"]["hits"] == ["28600"]

    def test_cycle_rollup_stdout_valid_json(self):
        r = run_cli("--ledger", SAMPLE_LEDGER, "--cache", NO_CACHE,
                     "cycle_rollup", "cycle_2026-01")
        json.loads(r.stdout)


class TestNoCommandExits2:
    def test_no_args(self):
        r = run_cli()
        assert r.returncode == 2
