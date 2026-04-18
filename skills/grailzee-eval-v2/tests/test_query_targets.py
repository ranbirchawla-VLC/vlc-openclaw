"""Tests for scripts.query_targets; active hunting list with cycle discipline (Phase 17).

Hand-computed constants throughout. Every numeric assertion includes the
calculation derivation in a comment.

Fixture layout:
  - _make_cache(): builds a minimal v2 cache dict (shared with Phase 16 pattern)
  - _make_ref(): builds one per-reference cache entry
  - Cycle focus and ledger fixtures written inline to tmp_path

Test categories map to Phase 17 prompt Section 6:
  A. Cycle gate behavior (4 tests)
  B. Filtered list / gate passes (6 tests)
  C. Override mode (5 tests)
  D. Filters + validation (5 tests)
  E. Premium status (2 tests)
  F. Error paths (2 tests)
  G. Path isolation (1 test)
  H. CLI (2 tests)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.grailzee_common import CACHE_SCHEMA_VERSION
from scripts.query_targets import (
    query_targets,
    _check_cycle_gate,
    _sort_results,
    _validate_filters,
    _parse_cli_filters,
)


# ─── Fixture helpers ─────────────────────────────────────────────────


def _make_ref(
    brand="Tudor", model="BB GMT Pepsi", reference="79830RB",
    median=3200, max_buy_nr=2910, max_buy_res=2860,
    risk_nr=8.5, signal="Strong", volume=12, st_pct=0.78,
    named=True, momentum=None,
    trend_signal="Stable", trend_median_change=0, trend_median_pct=0,
):
    """Build one per-reference cache entry.

    Default values hand-computed for Tudor 79830RB at median $3,200:
      max_buy_nr = round((3200 - 149) / 1.05, -1) = 2910
      max_buy_res = round((3200 - 199) / 1.05, -1) = 2860
    """
    return {
        "brand": brand, "model": model, "reference": reference,
        "named": named, "median": median,
        "max_buy_nr": max_buy_nr, "max_buy_res": max_buy_res,
        "risk_nr": risk_nr, "signal": signal,
        "volume": volume, "st_pct": st_pct,
        "momentum": momentum,
        "confidence": None,
        "trend_signal": trend_signal,
        "trend_median_change": trend_median_change,
        "trend_median_pct": trend_median_pct,
    }


def _make_cache(
    refs=None, premium_status=None,
    cycle_id="cycle_2026-15",
    generated_at="2026-04-15T10:30:00",
    source_report="grailzee_2026-04-12.csv",
):
    """Build a minimal v2 analysis cache dict."""
    ps = premium_status or {
        "avg_premium": 0, "trade_count": 0,
        "threshold_met": False, "adjustment": 0,
        "trades_to_threshold": 10,
    }
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_report": source_report,
        "cycle_id": cycle_id,
        "premium_status": ps,
        "references": refs or {},
        "dj_configs": {},
    }


def _write_cache(tmp_path, cache_dict):
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(cache_dict, indent=2))
    return str(p)


def _write_ledger(tmp_path, rows):
    p = tmp_path / "trade_ledger.csv"
    header = "date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n"
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['date_closed']},{r['cycle_id']},{r['brand']},"
            f"{r['reference']},{r['account']},{r['buy_price']},"
            f"{r['sell_price']}\n"
        )
    p.write_text("".join(lines))
    return str(p)


def _write_cycle_focus(tmp_path, focus_dict):
    p = tmp_path / "cycle_focus.json"
    p.write_text(json.dumps(focus_dict, indent=2))
    return str(p)


# ─── Standard fixtures ───────────────────────────────────────────────

# 5 references: diverse brands, signals, momentum scores, volumes
FIVE_REFS = {
    "79830RB": _make_ref(
        brand="Tudor", model="BB GMT Pepsi", reference="79830RB",
        signal="Strong", risk_nr=8.5, volume=12,
        momentum={"score": 2, "label": "Heating Up"},
    ),
    "A17320": _make_ref(
        brand="Breitling", model="Superocean Heritage", reference="A17320",
        median=2400,
        # max_buy_nr = round((2400-149)/1.05, -1) = round(2143.81, -1) = 2140
        max_buy_nr=2140,
        # max_buy_res = round((2400-199)/1.05, -1) = round(2095.24, -1) = 2100
        max_buy_res=2100,
        signal="Normal", risk_nr=18.0, volume=8,
        momentum={"score": 1, "label": "Warming"},
    ),
    "WSSA0030": _make_ref(
        brand="Cartier", model="Santos 40mm", reference="WSSA0030",
        median=4800,
        # max_buy_nr = round((4800-149)/1.05, -1) = round(4429.52, -1) = 4430
        max_buy_nr=4430,
        max_buy_res=4390,
        signal="Strong", risk_nr=5.0, volume=11,
        momentum={"score": 2, "label": "Heating Up"},
    ),
    "CAREFUL1": _make_ref(
        brand="TestBrand", model="Careful Watch", reference="CAREFUL1",
        median=2000, max_buy_nr=1760, max_buy_res=1720,
        # risk_nr=45 > RISK_RESERVE_THRESHOLD*100=40 -> Reserve
        signal="Careful", risk_nr=45.0, volume=5,
        momentum={"score": -1, "label": "Softening"},
    ),
    "LOW1": _make_ref(
        brand="TestBrand", model="Low Data Watch", reference="LOW1",
        median=1500, max_buy_nr=1290, max_buy_res=1240,
        signal="Low data", risk_nr=None, volume=3,
        momentum={"score": 0, "label": "Stable"},
    ),
}


@pytest.fixture
def five_ref_cache():
    return _make_cache(refs=FIVE_REFS)


@pytest.fixture
def current_focus():
    """Focus targeting 2 of the 5 refs, cycle matches cache."""
    return {
        "cycle_id": "cycle_2026-15",
        "set_at": "2026-04-14T10:30:00",
        "targets": [
            {
                "reference": "79830RB",
                "brand": "Tudor",
                "model": "BB GMT Pepsi",
                "cycle_reason": "Core Grailzee performer, data shows momentum",
                "max_buy_override": None,
            },
            {
                "reference": "A17320",
                "brand": "Breitling",
                "model": "Superocean Heritage",
                "cycle_reason": "New lane, testing Breitling market",
                "max_buy_override": None,
            },
        ],
        "capital_target": 15000,
        "volume_target": 5,
    }


# ═══════════════════════════════════════════════════════════════════════
# A. Cycle gate behavior
# ═══════════════════════════════════════════════════════════════════════


class TestCycleGate:

    def test_gate_no_focus(self, tmp_path, five_ref_cache):
        """A1: cycle_focus.json absent -> gate, no_focus."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "nonexistent_focus.json"),
        )
        assert result["status"] == "gate"
        assert result["state"] == "no_focus"
        assert result["cycle_id_current"] == "cycle_2026-15"
        assert result["cycle_id_focus"] is None

    def test_gate_stale_focus(self, tmp_path, five_ref_cache):
        """A2: focus cycle_id != cache cycle_id -> gate, stale_focus."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, {
            "cycle_id": "cycle_2026-13",
            "targets": [{"reference": "79830RB"}],
        })
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        assert result["status"] == "gate"
        assert result["state"] == "stale_focus"
        assert result["cycle_id_current"] == "cycle_2026-15"
        assert result["cycle_id_focus"] == "cycle_2026-13"

    def test_gate_malformed_focus(self, tmp_path, five_ref_cache):
        """A3: corrupted JSON -> gate, error, parse note."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = tmp_path / "cycle_focus.json"
        focus_path.write_text("{invalid json!!!")
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(focus_path),
        )
        assert result["status"] == "gate"
        assert result["state"] == "error"
        assert "parse error" in result["message"].lower()

    def test_gate_message_text(self, tmp_path, five_ref_cache):
        """A4: gate response includes Section 10.3 message text."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "nonexistent_focus.json"),
        )
        assert "Strategy session required" in result["message"]
        assert "grailzee-strategy" in result["message"]


# ═══════════════════════════════════════════════════════════════════════
# B. Filtered list (gate passes)
# ═══════════════════════════════════════════════════════════════════════


class TestFilteredList:

    def test_focus_targets_only(self, tmp_path, five_ref_cache, current_focus):
        """B5: Cache has 5 refs, focus has 2 -> response has exactly 2."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        assert result["status"] == "ok"
        assert result["target_count"] == 2
        refs_returned = {t["reference"] for t in result["targets"]}
        assert refs_returned == {"79830RB", "A17320"}

    def test_includes_cycle_reason(self, tmp_path, five_ref_cache, current_focus):
        """B6: Each target has cycle_reason from focus."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        for t in result["targets"]:
            assert t["cycle_reason"] is not None
        # 79830RB should have its specific reason
        tudor = [t for t in result["targets"] if t["reference"] == "79830RB"][0]
        assert "Core Grailzee performer" in tudor["cycle_reason"]

    def test_sorted_momentum_desc(self, tmp_path, five_ref_cache, current_focus):
        """B7: Primary sort is momentum score descending.

        79830RB: momentum=2, A17320: momentum=1
        -> 79830RB first, A17320 second
        """
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        refs = [t["reference"] for t in result["targets"]]
        assert refs == ["79830RB", "A17320"]

    def test_tie_breaker(self, tmp_path):
        """B8: Same momentum -> volume desc, then ref asc.

        REF_A: momentum=2, volume=5
        REF_B: momentum=2, volume=10
        REF_C: momentum=2, volume=10
        Sort: REF_B before REF_C (both volume=10, "REF_B" < "REF_C"),
              then REF_A (volume=5).
        """
        cache = _make_cache(refs={
            "REF_A": _make_ref(reference="REF_A", volume=5,
                               momentum={"score": 2, "label": "Heating Up"}),
            "REF_B": _make_ref(reference="REF_B", volume=10,
                               momentum={"score": 2, "label": "Heating Up"}),
            "REF_C": _make_ref(reference="REF_C", volume=10,
                               momentum={"score": 2, "label": "Heating Up"}),
        })
        focus = {
            "cycle_id": "cycle_2026-15",
            "targets": [
                {"reference": "REF_A", "cycle_reason": "test"},
                {"reference": "REF_B", "cycle_reason": "test"},
                {"reference": "REF_C", "cycle_reason": "test"},
            ],
        }
        cache_path = _write_cache(tmp_path, cache)
        focus_path = _write_cycle_focus(tmp_path, focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        refs = [t["reference"] for t in result["targets"]]
        assert refs == ["REF_B", "REF_C", "REF_A"]

    def test_confidence_enrichment(self, tmp_path, five_ref_cache, current_focus):
        """B9: Ref with ledger trades gets confidence; without gets null.

        Ledger has 2 trades for Tudor 79830RB, none for Breitling A17320.
        Both NR (fees=149):
          buy=2800, sell=3200 -> net=251 (profitable)
          buy=2750, sell=3100 -> net=201 (profitable)
        """
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        ledger_path = _write_ledger(tmp_path, [
            {"date_closed": "2026-01-15", "cycle_id": "cycle_2026-01",
             "brand": "Tudor", "reference": "79830RB", "account": "NR",
             "buy_price": 2800, "sell_price": 3200},
            {"date_closed": "2026-02-15", "cycle_id": "cycle_2026-04",
             "brand": "Tudor", "reference": "79830RB", "account": "NR",
             "buy_price": 2750, "sell_price": 3100},
        ])
        result = query_targets(
            cache_path=cache_path,
            ledger_path=ledger_path,
            cycle_focus_path=focus_path,
        )
        tudor = [t for t in result["targets"] if t["reference"] == "79830RB"][0]
        assert tudor["confidence"] is not None
        assert tudor["confidence"]["trades"] == 2
        breitling = [t for t in result["targets"] if t["reference"] == "A17320"][0]
        assert breitling["confidence"] is None

    def test_max_buy_override_honored(self, tmp_path, five_ref_cache):
        """B10: max_buy_override from focus overrides computed max_buy.

        79830RB: computed max_buy_nr=2910 (NR, risk=8.5 < 40)
        Focus sets max_buy_override=3100 -> effective max_buy=3100
        """
        focus = {
            "cycle_id": "cycle_2026-15",
            "targets": [{
                "reference": "79830RB",
                "cycle_reason": "Override test",
                "max_buy_override": 3100,
            }],
        }
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        tudor = result["targets"][0]
        assert tudor["max_buy"] == 3100
        assert tudor["max_buy_override"] == 3100


# ═══════════════════════════════════════════════════════════════════════
# C. Override mode
# ═══════════════════════════════════════════════════════════════════════


class TestOverrideMode:

    def test_override_full_universe(self, tmp_path, five_ref_cache, current_focus):
        """C10: ignore_cycle returns all 5 cache refs, not just focus 2."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            ignore_cycle=True,
        )
        assert result["target_count"] == 5

    def test_override_includes_warning(self, tmp_path, five_ref_cache):
        """C11: Override response has status=ok_override and warning."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
        )
        assert result["status"] == "ok_override"
        assert "not filtered by strategic intent" in result["warning"].lower()

    def test_override_no_cycle_reason(self, tmp_path, five_ref_cache):
        """C12: Override targets have cycle_reason=None."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
        )
        for t in result["targets"]:
            assert t["cycle_reason"] is None

    def test_override_works_without_focus(self, tmp_path, five_ref_cache):
        """C13: Override works even when focus file absent."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "nonexistent_focus.json"),
            ignore_cycle=True,
        )
        assert result["status"] == "ok_override"
        assert result["target_count"] == 5

    def test_override_with_filters(self, tmp_path, five_ref_cache):
        """C14: Override + filters narrows the full universe.

        5 refs total, 1 Tudor -> --ignore-cycle --brand Tudor -> 1 result.
        Override warning preserved.
        """
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
            filters={"brand": "Tudor"},
        )
        assert result["status"] == "ok_override"
        assert result["target_count"] == 1
        assert result["targets"][0]["reference"] == "79830RB"
        assert "not filtered by strategic intent" in result["warning"].lower()


# ═══════════════════════════════════════════════════════════════════════
# D. Filters + validation
# ═══════════════════════════════════════════════════════════════════════


class TestFilters:

    def test_brand_filter(self, tmp_path, five_ref_cache, current_focus):
        """D14: brand='Tudor' narrows to Tudor only."""
        # Focus has both Tudor and Breitling
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            filters={"brand": "Tudor"},
        )
        assert result["status"] == "ok"
        assert result["target_count"] == 1
        assert result["targets"][0]["brand"] == "Tudor"

    def test_signal_filter(self, tmp_path, five_ref_cache):
        """D15: signal='Strong' narrows to Strong only (2 of 5 in override)."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
            filters={"signal": "Strong"},
        )
        # 79830RB and WSSA0030 are both Strong
        assert result["target_count"] == 2
        for t in result["targets"]:
            assert t["signal"] == "Strong"

    def test_filter_no_results(self, tmp_path, five_ref_cache, current_focus):
        """D16: Filters narrow to zero -> empty targets, not error."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            filters={"brand": "NonexistentBrand"},
        )
        assert result["status"] == "ok"
        assert result["target_count"] == 0
        assert result["targets"] == []

    def test_budget_filter(self, tmp_path, five_ref_cache):
        """D17: budget=3000 excludes refs with max_buy > 3000.

        In override mode with full universe:
        79830RB: NR, max_buy=2910 (<= 3000) -> included
        A17320: NR, max_buy=2140 (<= 3000) -> included
        WSSA0030: NR, max_buy=4430 (> 3000) -> excluded
        CAREFUL1: Reserve (risk=45>40), max_buy=1720 (<= 3000) -> included
        LOW1: NR, max_buy=1290 (<= 3000) -> included
        Total: 4 targets
        """
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
            filters={"budget": 3000},
        )
        assert result["target_count"] == 4
        refs = {t["reference"] for t in result["targets"]}
        assert "WSSA0030" not in refs

    def test_bad_sort_value(self, tmp_path, five_ref_cache):
        """D18: Invalid --sort value -> error/bad_filter with accepted values."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
            sort_by="invalid_field",
        )
        assert result["status"] == "error"
        assert result["error"] == "bad_filter"
        assert "invalid_field" in result["message"].lower()
        assert "momentum" in result["message"]

    def test_bad_format_value(self, tmp_path, five_ref_cache):
        """D19: Invalid --format value -> error/bad_filter."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            ignore_cycle=True,
            filters={"format": "INVALID"},
        )
        assert result["status"] == "error"
        assert result["error"] == "bad_filter"
        assert "INVALID" in result["message"]


# ═══════════════════════════════════════════════════════════════════════
# E. Premium status surfacing
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumStatus:

    def test_premium_in_ok_response(self, tmp_path, current_focus):
        """E18: Premium status surfaced in ok response."""
        ps = {
            "avg_premium": 12.0, "trade_count": 8,
            "threshold_met": False, "adjustment": 0,
            "trades_to_threshold": 2,
        }
        cache = _make_cache(
            refs={"79830RB": _make_ref()},
            premium_status=ps,
        )
        # Focus only has 79830RB
        focus = {
            "cycle_id": "cycle_2026-15",
            "targets": [{"reference": "79830RB", "cycle_reason": "test"}],
        }
        cache_path = _write_cache(tmp_path, cache)
        focus_path = _write_cycle_focus(tmp_path, focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        assert result["premium_status"]["trade_count"] == 8
        assert result["premium_status"]["trades_to_threshold"] == 2

    def test_premium_in_gate_response(self, tmp_path):
        """E19: Premium status surfaced even in gate response."""
        ps = {
            "avg_premium": 14.0, "trade_count": 10,
            "threshold_met": True, "adjustment": 7.0,
            "trades_to_threshold": 0,
        }
        cache = _make_cache(
            refs={"79830RB": _make_ref()},
            premium_status=ps,
        )
        cache_path = _write_cache(tmp_path, cache)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
        )
        assert result["status"] == "gate"
        assert result["premium_status"]["threshold_met"] is True
        assert result["premium_status"]["adjustment"] == 7.0


# ═══════════════════════════════════════════════════════════════════════
# F. Error paths
# ═══════════════════════════════════════════════════════════════════════


class TestErrorPaths:

    def test_missing_cache(self, tmp_path):
        """F20: Cache doesn't exist -> error/no_cache. No premium_status."""
        result = query_targets(
            cache_path=str(tmp_path / "nonexistent_cache.json"),
        )
        assert result["status"] == "error"
        assert result["error"] == "no_cache"
        assert "premium_status" not in result

    def test_stale_schema(self, tmp_path):
        """F21: schema_version < CACHE_SCHEMA_VERSION -> error/stale_schema."""
        stale = _make_cache()
        stale["schema_version"] = 1
        cache_path = _write_cache(tmp_path, stale)
        result = query_targets(cache_path=cache_path)
        assert result["status"] == "error"
        assert result["error"] == "stale_schema"
        assert "premium_status" not in result


# ═══════════════════════════════════════════════════════════════════════
# G. Path isolation
# ═══════════════════════════════════════════════════════════════════════


class TestPathIsolation:

    def test_all_paths_injected(self, tmp_path, five_ref_cache, current_focus):
        """G22: No production path leakage."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        assert "/GrailzeeData/" not in json.dumps(result)


# ═══════════════════════════════════════════════════════════════════════
# H. CLI
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:

    def test_parse_filters(self):
        """H23: _parse_cli_filters extracts filter dict correctly."""
        import argparse
        args = argparse.Namespace(
            brand="Tudor", signal="Strong", budget=3000.0,
            format="NR", sort="volume",
        )
        filters, sort_by = _parse_cli_filters(args)
        assert filters == {"brand": "Tudor", "signal": "Strong",
                           "budget": 3000.0, "format": "NR"}
        assert sort_by == "volume"

    def test_parse_filters_empty(self):
        """H23b: Empty args produce empty filters."""
        import argparse
        args = argparse.Namespace(
            brand=None, signal=None, budget=None,
            format=None, sort=None,
        )
        filters, sort_by = _parse_cli_filters(args)
        assert filters == {}
        assert sort_by is None

    def test_cli_smoke(self, tmp_path, five_ref_cache, current_focus):
        """H24: CLI invocation returns valid JSON."""
        cache_path = _write_cache(tmp_path, five_ref_cache)
        focus_path = _write_cycle_focus(tmp_path, current_focus)
        script = str(Path(__file__).resolve().parent.parent / "scripts" / "query_targets.py")

        proc = subprocess.run(
            [
                sys.executable, script,
                "--cache", cache_path,
                "--ledger", str(tmp_path / "no_ledger.csv"),
                "--cycle-focus", focus_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["status"] == "ok"
        assert result["target_count"] == 2


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


class TestSortResults:

    def test_sort_by_volume(self):
        """Volume sort: descending, tiebreak by momentum then ref."""
        targets = [
            {"reference": "A", "volume": 5, "momentum": {"score": 2}},
            {"reference": "B", "volume": 10, "momentum": {"score": 1}},
            {"reference": "C", "volume": 10, "momentum": {"score": 2}},
        ]
        result = _sort_results(targets, "volume")
        refs = [t["reference"] for t in result]
        # B and C tied on volume=10; C has higher momentum -> C first
        assert refs == ["C", "B", "A"]

    def test_sort_by_signal(self):
        """Signal sort: Strong < Normal < Reserve < Careful < Pass."""
        targets = [
            {"reference": "A", "signal": "Careful", "volume": 5},
            {"reference": "B", "signal": "Strong", "volume": 5},
            {"reference": "C", "signal": "Normal", "volume": 5},
        ]
        result = _sort_results(targets, "signal")
        refs = [t["reference"] for t in result]
        assert refs == ["B", "C", "A"]

    def test_sort_by_max_buy(self):
        """Max buy sort: ascending (cheapest first)."""
        targets = [
            {"reference": "A", "max_buy": 3000, "momentum": {"score": 0}},
            {"reference": "B", "max_buy": 1500, "momentum": {"score": 0}},
            {"reference": "C", "max_buy": 2200, "momentum": {"score": 0}},
        ]
        result = _sort_results(targets, "max_buy")
        refs = [t["reference"] for t in result]
        assert refs == ["B", "C", "A"]


class TestTargetsNotInCache:

    def test_focus_ref_not_in_cache(self, tmp_path):
        """Focus target MISSING1 not in cache -> listed in targets_not_in_cache."""
        cache = _make_cache(refs={
            "79830RB": _make_ref(),
        })
        focus = {
            "cycle_id": "cycle_2026-15",
            "targets": [
                {"reference": "79830RB", "cycle_reason": "found"},
                {"reference": "MISSING1", "cycle_reason": "not in cache"},
            ],
        }
        cache_path = _write_cache(tmp_path, cache)
        focus_path = _write_cycle_focus(tmp_path, focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        assert result["status"] == "ok"
        assert result["target_count"] == 1
        assert result["targets_not_in_cache"] == ["MISSING1"]
        assert result["targets_not_in_cache_count"] == 1

    def test_reserve_format_from_risk(self, tmp_path):
        """Cache entry with risk_nr=45 (>40) -> format='Reserve', max_buy from max_buy_res.

        CAREFUL1: risk_nr=45, max_buy_res=1720
        """
        cache = _make_cache(refs={"CAREFUL1": FIVE_REFS["CAREFUL1"]})
        focus = {
            "cycle_id": "cycle_2026-15",
            "targets": [{"reference": "CAREFUL1", "cycle_reason": "test"}],
        }
        cache_path = _write_cache(tmp_path, cache)
        focus_path = _write_cycle_focus(tmp_path, focus)
        result = query_targets(
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
        )
        t = result["targets"][0]
        assert t["format"] == "Reserve"
        assert t["max_buy"] == 1720
        assert t["risk_pct"] == 45.0
