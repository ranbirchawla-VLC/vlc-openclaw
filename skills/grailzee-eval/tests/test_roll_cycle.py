"""Tests for scripts.roll_cycle; cycle outcome production per guide Section 5.7.

New in v2; no v1 equivalent (v1 has no cycle concept). All tests hand-computed.

Cycle used in tests: cycle_2026-02
  First Monday 2026 = Jan 5
  start = Jan 5 + 1*14 = Jan 19
  end   = Jan 19 + 13  = Feb 1

Hand-computed trade constants (cycle_2026-02):
─────────────────────────────────────────────────────────────────────────
  Trade  date        brand    ref                    acct  buy   sell  fees  net   roi_pct
  ─────────────────────────────────────────────────────────────────────
  T1     2026-01-19  Tudor    79830RB                NR    2750  3200  149   301   10.95
  T2     2026-01-25  Omega    210.30.42.20.03.001    NR    3000  3100  149   -49   -1.63
  T3     2026-02-01  Tudor    91650                  RES   1800  2100  199   101    5.61
─────────────────────────────────────────────────────────────────────────

  net:  sell - buy - fees
  roi:  round((net / buy) * 100, 2)
    T1: (3200-2750-149) = 301;  (301/2750)*100 = 10.9454... -> 10.95
    T2: (3100-3000-149) = -49;  (-49/3000)*100 = -1.6333... -> -1.63
    T3: (2100-1800-199) = 101;  (101/1800)*100 = 5.6111... -> 5.61

Focus: targets = [79830RB, 210.30.42.20.03.001, A17320]
  hits          = [210.30.42.20.03.001, 79830RB]  (sorted; focus refs with trades)
  misses        = [A17320]                         (focus refs without trades)
  off_cycle     = [91650]                          (trades not in focus)
  in_focus_count  = 2
  off_cycle_count = 1

Summary:
  total_trades    = 3
  profitable      = 2  (T1, T3 have net > 0)
  avg_roi         = round(mean([10.95, -1.63, 5.61]), 1) = round(4.9766, 1) = 5.0
  total_net       = round(301 + (-49) + 101, 2) = 353.0
  capital_deployed = 2750 + 3000 + 1800 = 7550.0
  capital_returned = 7550 + 353 = 7903.0

Cycle ID rollover:
  prev_cycle("cycle_2026-01"):
    First Monday 2025 = Jan 6 (2025-01-01 is Wednesday; +5 = Jan 6)
    cycle_id_from_date(2025-12-31): delta = 359 days; 1 + 359//14 = 26
    Result: "cycle_2025-26"
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "roll_cycle.py"

from scripts.grailzee_common import prev_cycle
from scripts.roll_cycle import run


LEDGER_HEADER = "date_closed,cycle_id,brand,reference,account,buy_price,sell_price"


def _write_ledger(tmp_path: Path, rows: list[str]) -> str:
    path = tmp_path / "trade_ledger.csv"
    path.write_text(LEDGER_HEADER + "\n" + "\n".join(rows) + "\n")
    return str(path)


def _write_focus(tmp_path: Path, cycle_id: str, targets: list[str]) -> str:
    path = tmp_path / "cycle_focus.json"
    focus = {
        "cycle_id": cycle_id,
        "targets": [{"reference": r} for r in targets],
    }
    path.write_text(json.dumps(focus))
    return str(path)


def _empty_cache(tmp_path: Path) -> str:
    path = tmp_path / "analysis_cache.json"
    path.write_text("{}")
    return str(path)


# ═══════════════════════════════════════════════════════════════════════
# Hits / misses / off-cycle
# ═══════════════════════════════════════════════════════════════════════


class TestHitsMissesOffCycle:
    def test_focus_categorization(self, tmp_path):
        """Focus has 3 refs; 2 had trades, 1 didn't; 1 trade outside focus."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
            "2026-01-25,cycle_2026-02,Omega,210.30.42.20.03.001,NR,3000,3100",
            "2026-02-01,cycle_2026-02,Tudor,91650,RES,1800,2100",
        ])
        focus = _write_focus(tmp_path, "cycle_2026-02",
                             ["79830RB", "210.30.42.20.03.001", "A17320"])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, focus, out)
        cf = result["cycle_focus"]

        assert sorted(cf["targeted_references"]) == ["210.30.42.20.03.001", "79830RB", "A17320"]
        assert cf["hits"] == ["210.30.42.20.03.001", "79830RB"]
        assert cf["misses"] == ["A17320"]
        assert cf["off_cycle_trades"] == ["91650"]

    def test_in_focus_flags_on_trades(self, tmp_path):
        """Trades matching focus have in_focus=True; off-cycle has False."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
            "2026-02-01,cycle_2026-02,Tudor,91650,RES,1800,2100",
        ])
        focus = _write_focus(tmp_path, "cycle_2026-02", ["79830RB"])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, focus, out)
        trades = result["trades"]

        focus_trade = next(t for t in trades if t["reference"] == "79830RB")
        off_trade = next(t for t in trades if t["reference"] == "91650")
        assert focus_trade["in_focus"] is True
        assert off_trade["in_focus"] is False
        assert result["summary"]["in_focus_count"] == 1
        assert result["summary"]["off_cycle_count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Summary arithmetic
# ═══════════════════════════════════════════════════════════════════════


class TestSummaryArithmetic:
    def test_all_summary_fields(self, tmp_path):
        """Verify every summary field against hand-computed constants."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
            "2026-01-25,cycle_2026-02,Omega,210.30.42.20.03.001,NR,3000,3100",
            "2026-02-01,cycle_2026-02,Tudor,91650,RES,1800,2100",
        ])
        focus = _write_focus(tmp_path, "cycle_2026-02",
                             ["79830RB", "210.30.42.20.03.001", "A17320"])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, focus, out)
        s = result["summary"]

        assert s["total_trades"] == 3
        assert s["profitable"] == 2
        assert s["in_focus_count"] == 2
        assert s["off_cycle_count"] == 1
        assert s["avg_roi"] == 5.0
        assert s["total_net"] == 353.0
        assert s["capital_deployed"] == 7550.0
        assert s["capital_returned"] == 7903.0

    def test_per_trade_net_and_roi(self, tmp_path):
        """Verify individual trade net and roi against hand-computed values."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
            "2026-01-25,cycle_2026-02,Omega,210.30.42.20.03.001,NR,3000,3100",
            "2026-02-01,cycle_2026-02,Tudor,91650,RES,1800,2100",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        trades = {t["reference"]: t for t in result["trades"]}

        assert trades["79830RB"]["net"] == 301
        assert trades["79830RB"]["roi"] == 10.95
        assert trades["210.30.42.20.03.001"]["net"] == -49
        assert trades["210.30.42.20.03.001"]["roi"] == -1.63
        assert trades["91650"]["net"] == 101
        assert trades["91650"]["roi"] == 5.61


# ═══════════════════════════════════════════════════════════════════════
# Missing focus file
# ═══════════════════════════════════════════════════════════════════════


class TestMissingFocus:
    def test_no_focus_file(self, tmp_path):
        """No cycle_focus.json -> cycle_focus={} in output, all in_focus=False."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")
        missing_focus = str(tmp_path / "no_such_focus.json")

        result = run("cycle_2026-02", ledger, cache, missing_focus, out)
        assert result["cycle_focus"] == {}
        assert result["trades"][0]["in_focus"] is False

    def test_focus_for_wrong_cycle(self, tmp_path):
        """Focus exists but cycle_id doesn't match -> treated as no focus."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
        ])
        focus = _write_focus(tmp_path, "cycle_2026-99", ["79830RB"])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, focus, out)
        assert result["cycle_focus"] == {}


# ═══════════════════════════════════════════════════════════════════════
# Empty cycle (zero trades)
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyCycle:
    def test_zero_trades(self, tmp_path):
        """No trades in the cycle -> valid JSON with empty trades and zero summary."""
        ledger = _write_ledger(tmp_path, [
            "2026-03-15,cycle_2026-05,Tudor,79830RB,NR,2750,3200",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result["trades"] == []
        s = result["summary"]
        assert s["total_trades"] == 0
        assert s["profitable"] == 0
        assert s["avg_roi"] == 0
        assert s["total_net"] == 0
        assert s["capital_deployed"] == 0
        assert s["capital_returned"] == 0

    def test_empty_ledger(self, tmp_path):
        """Ledger exists but has no rows -> same as zero trades."""
        ledger = _write_ledger(tmp_path, [])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result["trades"] == []
        assert result["summary"]["total_trades"] == 0


# ═══════════════════════════════════════════════════════════════════════
# File write
# ═══════════════════════════════════════════════════════════════════════


class TestFileWrite:
    def test_writes_json(self, tmp_path):
        """run() writes cycle_outcome.json to output_path."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        run("cycle_2026-02", ledger, cache, output_path=out)
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert data["cycle_id"] == "cycle_2026-02"

    def test_overwrites_on_rerun(self, tmp_path):
        """Multiple runs overwrite the same file (idempotent)."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result1 = run("cycle_2026-02", ledger, cache, output_path=out)
        result2 = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result1 == result2


# ═══════════════════════════════════════════════════════════════════════
# Date range and cycle ID
# ═══════════════════════════════════════════════════════════════════════


class TestDateRangeAndCycleId:
    def test_cycle_id_passthrough(self, tmp_path):
        """cycle_id in output matches the input."""
        ledger = _write_ledger(tmp_path, [])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result["cycle_id"] == "cycle_2026-02"

    def test_date_range_matches_cycle(self, tmp_path):
        """date_range start/end match cycle_date_range() for cycle_2026-02.

        First Monday 2026 = Jan 5. Cycle 02: start = Jan 19, end = Feb 1.
        """
        ledger = _write_ledger(tmp_path, [])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result["date_range"]["start"] == "2026-01-19"
        assert result["date_range"]["end"] == "2026-02-01"

    def test_boundary_day_trades_included(self, tmp_path):
        """Trades on first and last day of cycle are included (cycle_id match)."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
            "2026-02-01,cycle_2026-02,Tudor,91650,NR,1800,2100",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        result = run("cycle_2026-02", ledger, cache, output_path=out)
        assert result["summary"]["total_trades"] == 2
        dates = [t["date"] for t in result["trades"]]
        assert "2026-01-19" in dates
        assert "2026-02-01" in dates


# ═══════════════════════════════════════════════════════════════════════
# Cycle ID arithmetic (year rollover)
# ═══════════════════════════════════════════════════════════════════════


class TestCycleIdRollover:
    def test_prev_cycle_mid_year(self):
        """prev_cycle("cycle_2026-07") -> "cycle_2026-06"."""
        assert prev_cycle("cycle_2026-07") == "cycle_2026-06"

    def test_prev_cycle_year_boundary(self):
        """prev_cycle("cycle_2026-01") -> "cycle_2025-26".

        2025 Jan 1 = Wednesday -> first Monday = Jan 6.
        Dec 31, 2025: delta = 359 days from Jan 6. 1 + 359//14 = 26.
        """
        assert prev_cycle("cycle_2026-01") == "cycle_2025-26"

    def test_prev_cycle_02(self):
        """prev_cycle("cycle_2026-02") -> "cycle_2026-01"."""
        assert prev_cycle("cycle_2026-02") == "cycle_2026-01"


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:
    def test_json_output(self, tmp_path):
        """CLI produces valid JSON with cycle_id, trades, summary keys."""
        ledger = _write_ledger(tmp_path, [
            "2026-01-19,cycle_2026-02,Tudor,79830RB,NR,2750,3200",
        ])
        cache = _empty_cache(tmp_path)
        out = str(tmp_path / "outcome.json")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "cycle_2026-02",
             "--ledger", ledger, "--cache", cache, "--output", out],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert "cycle_id" in data
        assert "trades" in data
        assert "summary" in data
