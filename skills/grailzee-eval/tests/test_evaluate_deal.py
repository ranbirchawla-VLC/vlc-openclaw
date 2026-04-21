"""Tests for scripts.evaluate_deal; single deal evaluation (Phase 16).

Hand-computed constants throughout. Every numeric assertion includes the
calculation derivation in a comment so the test itself documents the math.

Fixture layout:
  - _make_cache(): builds a minimal v2 cache dict
  - _make_ref(): builds one per-reference cache entry
  - Ledger and CSV fixtures are written inline to tmp_path

Test categories map to Phase 16 prompt Section 6:
  A. Cache hit happy paths (6 branches)
  B. On-demand CSV fallback
  C. Not found (comp_search_hint)
  D. Cycle focus alignment (4 states)
  E. Confidence enrichment
  F. Premium adjustment surfacing
  G. Error paths
  H. Path injection / test isolation
  + CLI tests
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.grailzee_common import CACHE_SCHEMA_VERSION
from scripts.evaluate_deal import (
    evaluate,
    _find_reference,
    _load_cache,
    _on_demand_analysis,
    _check_cycle_alignment,
    _score_decision,
    _parse_price_arg,
)


# ─── Fixture helpers ─────────────────────────────────────────────────


def _make_ref(
    brand="Tudor", model="BB GMT Pepsi", reference="79830RB",
    median=3200, max_buy_nr=2910, max_buy_res=2860,
    risk_nr=8.5, signal="Strong", volume=12, st_pct=0.78,
    named=True, momentum=None, confidence=None,
    trend_signal="Stable", trend_median_change=0, trend_median_pct=0,
    floor=None,
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
        "momentum": momentum, "confidence": confidence,
        "trend_signal": trend_signal,
        "trend_median_change": trend_median_change,
        "trend_median_pct": trend_median_pct,
        "floor": floor,
    }


def _make_cache(
    refs=None, dj_configs=None, premium_status=None,
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
        "dj_configs": dj_configs or {},
    }


def _write_cache(tmp_path, cache_dict):
    """Write cache dict to a temp file; return path string."""
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(cache_dict, indent=2))
    return str(p)


def _write_ledger(tmp_path, rows):
    """Write trade_ledger.csv (v2 shape) from list of dicts; return path.

    Row dicts use v2 keys (``sell_date``, ``sell_cycle_id``); buy_date
    and buy_cycle_id are left blank in the emitted CSV (legacy-row
    convention per schema v1 §4 S6).
    """
    p = tmp_path / "trade_ledger.csv"
    header = (
        "buy_date,sell_date,buy_cycle_id,sell_cycle_id,"
        "brand,reference,account,buy_price,sell_price\n"
    )
    lines = [header]
    for r in rows:
        lines.append(
            f",{r['sell_date']},,{r['sell_cycle_id']},{r['brand']},"
            f"{r['reference']},{r['account']},{r['buy_price']},"
            f"{r['sell_price']}\n"
        )
    p.write_text("".join(lines))
    return str(p)


def _write_cycle_focus(tmp_path, focus_dict):
    """Write cycle_focus.json; return path string."""
    p = tmp_path / "cycle_focus.json"
    p.write_text(json.dumps(focus_dict, indent=2))
    return str(p)


def _write_csv(tmp_path, rows, filename="grailzee_2026-04-12.csv"):
    """Write a normalized sales CSV; return directory path string."""
    csv_dir = tmp_path / "reports_csv"
    csv_dir.mkdir(exist_ok=True)
    header = "date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct\n"
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['date_sold']},{r['make']},{r['reference']},"
            f"{r['title']},{r['condition']},{r['papers']},"
            f"{r['sold_price']},{r.get('sell_through_pct', '')}\n"
        )
    (csv_dir / filename).write_text("".join(lines))
    return str(csv_dir)


# ─── Standard cache fixture ─────────────────────────────────────────
# Shared across A-tests: four references covering all signal types.


@pytest.fixture
def standard_cache():
    """Cache with four references spanning all decision branches."""
    return _make_cache(refs={
        # Strong signal, low risk; used by A2, A5, A6
        "79830RB": _make_ref(),
        # Pass signal, high risk; used by A1
        "PASSREF": _make_ref(
            brand="TestBrand", model="Pass Watch", reference="PASSREF",
            median=2000,
            # max_buy_nr = round((2000-149)/1.05, -1) = round(1762.86, -1) = 1760
            max_buy_nr=1760,
            # max_buy_res = round((2000-199)/1.05, -1) = round(1715.24, -1) = 1720
            max_buy_res=1720,
            risk_nr=55.0, signal="Pass", volume=8, st_pct=0.40,
        ),
        # Normal signal, moderate risk; used by A3
        "NORMALREF": _make_ref(
            brand="TestBrand", model="Normal Watch", reference="NORMALREF",
            median=3200, max_buy_nr=2910, max_buy_res=2860,
            risk_nr=15.0, signal="Normal", volume=10, st_pct=0.65,
        ),
        # Careful signal, risk in 30-40% band; used by A4
        "CAREFULREF": _make_ref(
            brand="TestBrand", model="Careful Watch", reference="CAREFULREF",
            median=3200, max_buy_nr=2910, max_buy_res=2860,
            risk_nr=35.0, signal="Careful", volume=6, st_pct=0.50,
        ),
    })


# ═══════════════════════════════════════════════════════════════════════
# A. Cache hit happy paths
# ═══════════════════════════════════════════════════════════════════════


class TestCacheHitDecisions:
    """One test per decision branch; hand-computed margins."""

    def test_signal_pass_no(self, tmp_path, standard_cache):
        """A1: Signal=Pass, risk=55% -> NO regardless of price."""
        cache_path = _write_cache(tmp_path, standard_cache)
        # Price well below max_buy, doesn't matter; Pass overrides
        result = evaluate(
            "TestBrand", "PASSREF", 1500,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "NO"
        assert "Risk is too high" in result["rationale"]
        assert "55%" in result["rationale"]

    def test_over_max_buy_no(self, tmp_path, standard_cache):
        """A2: Price $3,000 > MAX BUY NR $2,910 -> NO.

        margin_dollars = 3200 - 3000 - 149 = 51
        margin_pct = 51 / 3000 * 100 = 1.7%
        """
        cache_path = _write_cache(tmp_path, standard_cache)
        result = evaluate(
            "Tudor", "79830RB", 3000,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "NO"
        assert result["metrics"]["margin_pct"] == 1.7
        # over_by = 3000 - 2910 = 90
        assert result["metrics"]["vs_max_buy"] == 90
        assert "over MAX BUY" in result["rationale"]

    def test_near_ceiling_maybe(self, tmp_path, standard_cache):
        """A3: Price at 99% of MAX BUY, signal=Normal -> MAYBE.

        NORMALREF: max_buy_nr=2910, signal=Normal
        0.98 * 2910 = 2851.8; price 2870 > 2851.8 and <= 2910
        margin_dollars = 3200 - 2870 - 149 = 181
        margin_pct = 181 / 2870 * 100 = 6.3% (round to 1)
        """
        cache_path = _write_cache(tmp_path, standard_cache)
        result = evaluate(
            "TestBrand", "NORMALREF", 2870,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "MAYBE"
        assert result["metrics"]["margin_pct"] == 6.3
        assert "near the MAX BUY ceiling" in result["rationale"]

    def test_careful_route_reserve_maybe(self, tmp_path, standard_cache):
        """A4: Signal=Careful, risk=35% (20-40% band) -> MAYBE, Reserve.

        CAREFULREF: risk_nr=35, RISK_RESERVE_THRESHOLD*100=40
        recommend_reserve = 35 > 40 = False -> starts NR
        Branch fires: signal Careful + not recommend_reserve
        Switches to Reserve format:
          margin_dollars = 3200 - 2700 - 199 = 301
          margin_pct = 301 / 2700 * 100 = 11.1% (round to 1)
          reserve_price = round(2700 + 199 + 2700*0.02, -1) = round(2953, -1) = 2950
        """
        cache_path = _write_cache(tmp_path, standard_cache)
        result = evaluate(
            "TestBrand", "CAREFULREF", 2700,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "MAYBE"
        assert result["format"] == "Reserve"
        assert result["metrics"]["margin_pct"] == 11.1
        assert result["reserve_price"] == 2950
        assert "route to Reserve" in result["rationale"]

    def test_strong_buy_yes(self, tmp_path, standard_cache):
        """A5: Price $2,500 <= 90% of MAX BUY $2,910 -> YES, strong buy.

        0.90 * 2910 = 2619; 2500 <= 2619 -> strong buy
        margin_dollars = 3200 - 2500 - 149 = 551
        margin_pct = 551 / 2500 * 100 = 22.0%
        """
        cache_path = _write_cache(tmp_path, standard_cache)
        result = evaluate(
            "Tudor", "79830RB", 2500,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "YES"
        assert result["format"] == "NR"
        assert result["metrics"]["margin_pct"] == 22.0
        # margin_dollars = 551
        assert result["metrics"]["margin_dollars"] == 551
        assert "Strong buy" in result["rationale"]

    def test_within_max_yes(self, tmp_path, standard_cache):
        """A6: Price $2,750 between 90% and 98% of MAX BUY -> YES.

        0.90*2910=2619 < 2750 < 2851.8=0.98*2910
        margin_dollars = 3200 - 2750 - 149 = 301
        margin_pct = 301 / 2750 * 100 = 10.9% (round to 1)
        vs_max_buy = 2750 - 2910 = -160
        """
        cache_path = _write_cache(tmp_path, standard_cache)
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        assert result["grailzee"] == "YES"
        assert result["format"] == "NR"
        assert result["metrics"]["margin_pct"] == 10.9
        assert result["metrics"]["margin_dollars"] == 301
        assert result["metrics"]["vs_max_buy"] == -160
        assert "Buy works" in result["rationale"]


# ═══════════════════════════════════════════════════════════════════════
# B. On-demand CSV fallback
# ═══════════════════════════════════════════════════════════════════════


class TestOnDemandFallback:
    """Reference not in cache; found (or not) in raw CSV."""

    @pytest.fixture
    def csv_sales(self):
        """Five sales for OD100 and one sale for RARE1.

        OD100 prices: [2000, 2100, 1900, 2050, 1950]
        sorted: [1900, 1950, 2000, 2050, 2100], median=2000
        All VG+/LN/EX/New with papers=yes -> all quality
        max_buy_nr = round((2000-149)/1.05, -1) = 1760
        breakeven_nr = 1760 + 149 = 1909
        risk: 1 of 5 quality prices (1900) < 1909 = 20%
        signal: 20 <= 20 -> Normal
        """
        return [
            {"date_sold": "2026-04-01", "make": "TestBrand", "reference": "OD100",
             "title": "Test OD100", "condition": "very good", "papers": "yes",
             "sold_price": "2000", "sell_through_pct": "0.60"},
            {"date_sold": "2026-04-02", "make": "TestBrand", "reference": "OD100",
             "title": "Test OD100", "condition": "like new", "papers": "yes",
             "sold_price": "2100", "sell_through_pct": "0.60"},
            {"date_sold": "2026-04-03", "make": "TestBrand", "reference": "OD100",
             "title": "Test OD100", "condition": "excellent", "papers": "yes",
             "sold_price": "1900", "sell_through_pct": "0.60"},
            {"date_sold": "2026-04-04", "make": "TestBrand", "reference": "OD100",
             "title": "Test OD100", "condition": "very good", "papers": "yes",
             "sold_price": "2050", "sell_through_pct": "0.60"},
            {"date_sold": "2026-04-05", "make": "TestBrand", "reference": "OD100",
             "title": "Test OD100", "condition": "new", "papers": "yes",
             "sold_price": "1950", "sell_through_pct": "0.60"},
            # Only 1 sale for RARE1 (insufficient)
            {"date_sold": "2026-04-06", "make": "TestBrand", "reference": "RARE1",
             "title": "Test RARE1", "condition": "very good", "papers": "yes",
             "sold_price": "3000", "sell_through_pct": "0.50"},
        ]

    def test_on_demand_found_in_csv(self, tmp_path, csv_sales):
        """B7: OD100 found in CSV with 5 sales -> on_demand, YES.

        purchase_price=1700 < max_buy_nr=1760
        Decision: not Pass, not over max, not near ceiling, not Careful/Reserve
        1700 > 0.90*1760=1584 -> "Buy works"
        margin_dollars = 2000 - 1700 - 149 = 151
        margin_pct = 151 / 1700 * 100 = 8.9% (round to 1: 8.882...)
        """
        # Cache without OD100
        cache_path = _write_cache(tmp_path, _make_cache(refs={
            "OTHER": _make_ref(reference="OTHER"),
        }))
        csv_dir = _write_csv(tmp_path, csv_sales)

        result = evaluate(
            "TestBrand", "OD100", 1700,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=csv_dir,
        )
        assert result["status"] == "ok"
        assert result["data_source"] == "on_demand"
        assert result["grailzee"] == "YES"
        assert result["metrics"]["median"] == 2000
        assert result["metrics"]["margin_pct"] == 8.9
        assert result["metrics"]["margin_dollars"] == 151
        assert "NOTE: This reference is not in the core program" in result["rationale"]

    def test_on_demand_insufficient_sales(self, tmp_path, csv_sales):
        """B8: RARE1 in CSV with 1 sale -> not_found."""
        cache_path = _write_cache(tmp_path, _make_cache(refs={
            "OTHER": _make_ref(reference="OTHER"),
        }))
        csv_dir = _write_csv(tmp_path, csv_sales)

        result = evaluate(
            "TestBrand", "RARE1", 2500,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=csv_dir,
        )
        assert result["status"] == "not_found"
        assert result["grailzee"] == "NEEDS_RESEARCH"


# ═══════════════════════════════════════════════════════════════════════
# C. Not found (comp_search_hint)
# ═══════════════════════════════════════════════════════════════════════


class TestNotFound:

    def test_not_found_returns_comp_search_hint(self, tmp_path):
        """C9: Reference in neither cache nor CSV -> not_found with hints."""
        cache_path = _write_cache(tmp_path, _make_cache(refs={}))

        result = evaluate(
            "Breitling", "UNKNOWN999", 3000,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "not_found"
        assert result["grailzee"] == "NEEDS_RESEARCH"
        assert result["brand"] == "Breitling"
        assert result["reference"] == "UNKNOWN999"
        assert result["purchase_price"] == 3000

        # comp_search_hint structure
        hint = result["comp_search_hint"]
        assert hint["brand"] == "Breitling"
        assert hint["reference"] == "UNKNOWN999"
        assert len(hint["search_queries"]) == 3
        assert "chrono24.com" in hint["search_queries"][0]
        assert "ebay.com" in hint["search_queries"][1]
        assert "formula_reminder" in hint
        assert "149" in hint["formula_reminder"]

        # Confidence skipped on not_found (Fix #2)
        assert result["confidence"] is None

        # premium_status present (cache loaded successfully)
        assert result["premium_status"] is not None

        # cache metadata present
        assert "cache_date" in result
        assert "cache_report" in result


# ═══════════════════════════════════════════════════════════════════════
# D. Cycle focus alignment
# ═══════════════════════════════════════════════════════════════════════


class TestCycleFocusAlignment:

    @pytest.fixture
    def cache_with_ref(self, tmp_path):
        """Cache with 79830RB, cycle_id=cycle_2026-15."""
        return _write_cache(tmp_path, _make_cache(refs={
            "79830RB": _make_ref(),
        }))

    def test_in_cycle(self, tmp_path, cache_with_ref):
        """D10: Focus current, ref in targets -> in_cycle."""
        focus_path = _write_cycle_focus(tmp_path, {
            "cycle_id": "cycle_2026-15",
            "targets": [
                {"reference": "79830RB", "brand": "Tudor", "model": "BB GMT"},
                {"reference": "OTHER", "brand": "Other", "model": "Other"},
            ],
        })
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_with_ref,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        cf = result["cycle_focus"]
        assert cf["state"] == "in_cycle"
        assert cf["cycle_id_current"] == "cycle_2026-15"
        assert cf["cycle_id_focus"] == "cycle_2026-15"
        assert cf["in_targets"] is True

    def test_off_cycle(self, tmp_path, cache_with_ref):
        """D11: Focus current, ref NOT in targets -> off_cycle."""
        focus_path = _write_cycle_focus(tmp_path, {
            "cycle_id": "cycle_2026-15",
            "targets": [
                {"reference": "OTHER", "brand": "Other", "model": "Other"},
            ],
        })
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_with_ref,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        cf = result["cycle_focus"]
        assert cf["state"] == "off_cycle"
        assert cf["in_targets"] is False
        assert "not in current hunting list" in cf["note"].lower()

    def test_no_focus(self, tmp_path, cache_with_ref):
        """D12: cycle_focus.json absent -> no_focus."""
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_with_ref,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "nonexistent_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        cf = result["cycle_focus"]
        assert cf["state"] == "no_focus"
        assert cf["cycle_id_focus"] is None
        assert cf["in_targets"] is False

    def test_stale_focus(self, tmp_path, cache_with_ref):
        """D13: Focus cycle_id != cache cycle_id -> stale_focus."""
        focus_path = _write_cycle_focus(tmp_path, {
            "cycle_id": "cycle_2026-13",  # stale: cache is cycle_2026-15
            "targets": [
                {"reference": "79830RB", "brand": "Tudor"},
            ],
        })
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_with_ref,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=focus_path,
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        cf = result["cycle_focus"]
        assert cf["state"] == "stale_focus"
        assert cf["cycle_id_current"] == "cycle_2026-15"
        assert cf["cycle_id_focus"] == "cycle_2026-13"
        assert cf["in_targets"] is False


# ═══════════════════════════════════════════════════════════════════════
# E. Confidence enrichment
# ═══════════════════════════════════════════════════════════════════════


class TestConfidenceEnrichment:

    def test_confidence_with_history(self, tmp_path):
        """E14: Ledger has 3 trades for Tudor 79830RB -> confidence populated.

        All NR (fees=149):
          buy=2800, sell=3200 -> net=251 (profitable)
          buy=2700, sell=3520 -> net=671 (profitable)
          buy=2750, sell=3360 -> net=461 (profitable)
        trades=3, profitable=3, win_rate=100.0
        """
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        ledger_path = _write_ledger(tmp_path, [
            {"sell_date": "2026-01-15", "sell_cycle_id": "cycle_2026-01",
             "brand": "Tudor", "reference": "79830RB", "account": "NR",
             "buy_price": 2800, "sell_price": 3200},
            {"sell_date": "2026-02-15", "sell_cycle_id": "cycle_2026-04",
             "brand": "Tudor", "reference": "79830RB", "account": "NR",
             "buy_price": 2700, "sell_price": 3520},
            {"sell_date": "2026-03-15", "sell_cycle_id": "cycle_2026-06",
             "brand": "Tudor", "reference": "79830RB", "account": "NR",
             "buy_price": 2750, "sell_price": 3360},
        ])
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=ledger_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["confidence"] is not None
        c = result["confidence"]
        assert c["trades"] == 3
        assert c["profitable"] == 3
        assert c["win_rate"] == 100.0

    def test_confidence_no_history(self, tmp_path):
        """E15: Ledger has no trades for ref -> confidence=null."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        # Ledger with trades for a DIFFERENT reference
        ledger_path = _write_ledger(tmp_path, [
            {"sell_date": "2026-01-15", "sell_cycle_id": "cycle_2026-01",
             "brand": "Tudor", "reference": "91650", "account": "NR",
             "buy_price": 1500, "sell_price": 1700},
        ])
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=ledger_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["confidence"] is None

    def test_confidence_mixed_outcomes(self, tmp_path):
        """E16: 5 trades, 3 profitable -> win_rate=60.0%.

        All NR (fees=149), all buy=1000:
          sell=1200 -> net=51 (profitable)
          sell=1100 -> net=-49 (NOT profitable)
          sell=1300 -> net=151 (profitable)
          sell=1050 -> net=-99 (NOT profitable)
          sell=1250 -> net=101 (profitable)
        profitable=3, total=5
        win_rate = round(3/5*100, 1) = 60.0

        ROIs: [5.1, -4.9, 15.1, -9.9, 10.1]
        avg_roi = round(15.5/5, 1) = 3.1
        """
        # MIX123 in cache with median=1200 so confidence can compute premium
        cache = _make_cache(refs={"MIX123": _make_ref(
            brand="Tudor", model="Mix Watch", reference="MIX123",
            median=1200,
            # max_buy_nr = round((1200-149)/1.05, -1) = round(1000.95, -1) = 1000
            max_buy_nr=1000,
            # max_buy_res = round((1200-199)/1.05, -1) = round(953.33, -1) = 950
            max_buy_res=950,
            risk_nr=15.0, signal="Normal",
        )})
        cache_path = _write_cache(tmp_path, cache)
        ledger_path = _write_ledger(tmp_path, [
            {"sell_date": "2026-01-15", "sell_cycle_id": "cycle_2026-01",
             "brand": "Tudor", "reference": "MIX123", "account": "NR",
             "buy_price": 1000, "sell_price": 1200},
            {"sell_date": "2026-02-15", "sell_cycle_id": "cycle_2026-04",
             "brand": "Tudor", "reference": "MIX123", "account": "NR",
             "buy_price": 1000, "sell_price": 1100},
            {"sell_date": "2026-03-15", "sell_cycle_id": "cycle_2026-06",
             "brand": "Tudor", "reference": "MIX123", "account": "NR",
             "buy_price": 1000, "sell_price": 1300},
            {"sell_date": "2026-04-01", "sell_cycle_id": "cycle_2026-07",
             "brand": "Tudor", "reference": "MIX123", "account": "NR",
             "buy_price": 1000, "sell_price": 1050},
            {"sell_date": "2026-04-10", "sell_cycle_id": "cycle_2026-07",
             "brand": "Tudor", "reference": "MIX123", "account": "NR",
             "buy_price": 1000, "sell_price": 1250},
        ])
        result = evaluate(
            "Tudor", "MIX123", 900,
            cache_path=cache_path,
            ledger_path=ledger_path,
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        c = result["confidence"]
        assert c is not None
        assert c["trades"] == 5
        assert c["profitable"] == 3
        assert c["win_rate"] == 60.0
        assert c["avg_roi"] == 3.1


# ═══════════════════════════════════════════════════════════════════════
# F. Premium adjustment surfacing
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumStatus:

    def test_premium_not_met(self, tmp_path):
        """F17: threshold_met=False -> premium_status surfaced, max_buy unadjusted.

        Cache max_buy_nr=2910 (standard for median=3200, no adjustment).
        """
        cache = _make_cache(
            refs={"79830RB": _make_ref()},
            premium_status={
                "avg_premium": 6.0, "trade_count": 5,
                "threshold_met": False, "adjustment": 0,
                "trades_to_threshold": 5,
            },
        )
        cache_path = _write_cache(tmp_path, cache)
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["premium_status"]["threshold_met"] is False
        assert result["premium_status"]["trades_to_threshold"] == 5
        assert result["metrics"]["max_buy"] == 2910

    def test_premium_met(self, tmp_path):
        """F18: threshold_met=True -> adjusted max_buy already in cache.

        With 5% adjustment on median=3200:
          adjusted_median = 3200 * 1.05 = 3360
          adjusted_max_buy_nr = round((3360-149)/1.05, -1) = round(3058.10, -1) = 3060
        Cache stores max_buy_nr=3060 (pre-adjusted by orchestrator).
        """
        cache = _make_cache(
            refs={"79830RB": _make_ref(max_buy_nr=3060, max_buy_res=2960)},
            premium_status={
                "avg_premium": 16.0, "trade_count": 12,
                "threshold_met": True, "adjustment": 5.0,
                "trades_to_threshold": 0,
            },
        )
        cache_path = _write_cache(tmp_path, cache)
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["premium_status"]["threshold_met"] is True
        assert result["premium_status"]["adjustment"] == 5.0
        # max_buy reflects the pre-adjusted value from cache
        assert result["metrics"]["max_buy"] == 3060


# ═══════════════════════════════════════════════════════════════════════
# G. Error paths
# ═══════════════════════════════════════════════════════════════════════


class TestErrorPaths:

    def test_missing_cache_file(self, tmp_path):
        """G19: Cache doesn't exist -> error/no_cache. No premium_status."""
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=str(tmp_path / "nonexistent_cache.json"),
        )
        assert result["status"] == "error"
        assert result["error"] == "no_cache"
        assert "premium_status" not in result

    def test_stale_schema_version(self, tmp_path):
        """G20: schema_version < CACHE_SCHEMA_VERSION -> error/stale_schema."""
        stale_cache = _make_cache()
        stale_cache["schema_version"] = 1  # below required v2
        cache_path = _write_cache(tmp_path, stale_cache)
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
        )
        assert result["status"] == "error"
        assert result["error"] == "stale_schema"
        assert "premium_status" not in result

    def test_bad_price_arg(self):
        """G21: Non-numeric price -> ValueError from _parse_price_arg."""
        with pytest.raises(ValueError):
            _parse_price_arg("abc")
        with pytest.raises(ValueError):
            _parse_price_arg("")

    def test_parse_price_strips_formatting(self):
        """G21b: Valid formatted prices parse correctly."""
        assert _parse_price_arg("$2,750") == 2750.0
        assert _parse_price_arg("3000") == 3000.0
        assert _parse_price_arg("$1,234.56") == 1234.56

    def test_bad_cycle_focus_json(self, tmp_path):
        """G22: Malformed cycle_focus.json -> state='error' with parse note.

        Per Fix #3: no silent fallback. Return error state so LLM
        surfaces the issue. Deal evaluation still completes.
        """
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        focus_path = tmp_path / "cycle_focus.json"
        focus_path.write_text("{not valid json!!!")

        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(focus_path),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        # Deal evaluation still succeeds
        assert result["status"] == "ok"
        assert result["grailzee"] in ("YES", "NO", "MAYBE")
        # Cycle focus reports error state
        cf = result["cycle_focus"]
        assert cf["state"] == "error"
        assert "parse error" in cf["note"].lower()

    def test_cycle_focus_missing_cycle_id(self, tmp_path):
        """G22b: cycle_focus.json valid JSON but missing cycle_id key."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        focus_path = _write_cycle_focus(tmp_path, {"targets": []})

        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(focus_path),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["status"] == "ok"
        cf = result["cycle_focus"]
        assert cf["state"] == "error"
        assert "missing cycle_id" in cf["note"].lower()


# ═══════════════════════════════════════════════════════════════════════
# H. Path injection / test isolation
# ═══════════════════════════════════════════════════════════════════════


class TestPathIsolation:

    def test_all_paths_injected(self, tmp_path):
        """H23: Verify no test reads from production GrailzeeData."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        ledger_path = str(tmp_path / "no_ledger.csv")
        focus_path = str(tmp_path / "no_focus.json")
        csv_dir = str(tmp_path / "no_csv")

        # All paths point to tmp_path; none to production
        result = evaluate(
            "Tudor", "79830RB", 2750,
            cache_path=cache_path,
            ledger_path=ledger_path,
            cycle_focus_path=focus_path,
            reports_csv_dir=csv_dir,
        )
        assert result["status"] == "ok"
        # Verify paths in result don't leak production paths
        assert "/GrailzeeData/" not in json.dumps(result)


# ═══════════════════════════════════════════════════════════════════════
# CLI integration tests
# ═══════════════════════════════════════════════════════════════════════


class TestCLI:
    """Subprocess tests for CLI entry point."""

    def test_cli_smoke(self, tmp_path):
        """CLI24: Basic CLI invocation returns valid JSON."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        cache_path = _write_cache(tmp_path, cache)
        script = str(Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py")

        proc = subprocess.run(
            [
                sys.executable, script,
                "Tudor", "79830RB", "2750",
                "--cache", cache_path,
                "--ledger", str(tmp_path / "no_ledger.csv"),
                "--cycle-focus", str(tmp_path / "no_focus.json"),
                "--reports-csv-dir", str(tmp_path / "no_csv"),
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["status"] == "ok"
        assert result["grailzee"] in ("YES", "NO", "MAYBE")

    def test_cli_bad_price(self, tmp_path):
        """CLI24b: Bad price argument -> error JSON, exit 1."""
        cache = _make_cache(refs={})
        cache_path = _write_cache(tmp_path, cache)
        script = str(Path(__file__).resolve().parent.parent / "scripts" / "evaluate_deal.py")

        proc = subprocess.run(
            [
                sys.executable, script,
                "Tudor", "79830RB", "notanumber",
                "--cache", cache_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 1
        result = json.loads(proc.stdout)
        assert result["status"] == "error"
        assert result["error"] == "bad_price"


# ═══════════════════════════════════════════════════════════════════════
# Internal helper tests
# ═══════════════════════════════════════════════════════════════════════


class TestFindReference:
    """Unit tests for the 4-pass cache lookup."""

    def test_exact_match(self):
        cache = _make_cache(refs={"79830RB": _make_ref()})
        key, entry = _find_reference(cache, "Tudor", "79830RB")
        assert key == "79830RB"
        assert entry["brand"] == "Tudor"

    def test_normalized_match(self):
        """Excel artifact: input has trailing .0"""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        key, entry = _find_reference(cache, "Tudor", "79830RB.0")
        assert key == "79830RB"

    def test_stripped_match_m_prefix(self):
        """Tudor M-prefix: M79830RB matches 79830RB via strip_ref."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        key, entry = _find_reference(cache, "Tudor", "M79830RB")
        assert key == "79830RB"

    def test_stripped_match_suffix(self):
        """Trailing -0001 suffix stripped: M79830RB-0001 matches 79830RB."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        key, entry = _find_reference(cache, "Tudor", "M79830RB-0001")
        assert key == "79830RB"

    def test_brand_filtered_substring(self):
        """Pass 3: brand match + substring."""
        cache = _make_cache(refs={"79830RB": _make_ref()})
        # Partial reference with correct brand
        key, entry = _find_reference(cache, "Tudor", "79830")
        assert key == "79830RB"

    def test_dj_config_match(self):
        """Pass 4: DJ config section lookup."""
        cache = _make_cache(
            refs={},
            dj_configs={"Black/Oyster": _make_ref(
                brand="Rolex", model="DJ 41 Black/Oyster",
                reference="126300",
            )},
        )
        key, entry = _find_reference(cache, "Rolex", "126300")
        assert key == "Black/Oyster"
        assert entry["model"] == "DJ 41 Black/Oyster"

    def test_not_found(self):
        cache = _make_cache(refs={"79830RB": _make_ref()})
        key, entry = _find_reference(cache, "Tudor", "ZZZZZ")
        assert key is None
        assert entry is None


class TestScoreDecision:
    """Direct unit tests for _score_decision with hand-computed values."""

    def test_reserve_signal_in_band(self):
        """Reserve signal (risk=25%, 20-40% band) -> MAYBE, Reserve format.

        risk=25 < 40 -> recommend_reserve=False -> MAYBE branch fires
        Switches to Reserve: fixed_cost=199
        margin_dollars = 3200 - 2700 - 199 = 301
        margin_pct = 301 / 2700 * 100 = 11.1%
        """
        entry = _make_ref(
            signal="Reserve", risk_nr=25.0,
            max_buy_nr=2910, max_buy_res=2860,
        )
        d = _score_decision(entry, 2700)
        assert d["grailzee"] == "MAYBE"
        assert d["format"] == "Reserve"
        assert d["margin_pct"] == pytest.approx(11.1, abs=0.1)

    def test_careful_above_threshold(self):
        """Careful signal (risk=45%) above threshold -> YES (recommend_reserve=True).

        risk=45 > 40 -> recommend_reserve=True -> Reserve format from start
        max_buy=2860, price=2700 < 2860 -> not over max
        2700 > 0.98*2860=2802.8? No
        signal Careful + recommend_reserve=True -> doesn't match MAYBE branch
        Falls to YES. 2700 <= 0.90*2860=2574? No
        -> "Buy works"
        margin_dollars = 3200 - 2700 - 199 = 301
        """
        entry = _make_ref(
            signal="Careful", risk_nr=45.0,
            max_buy_nr=2910, max_buy_res=2860,
        )
        d = _score_decision(entry, 2700)
        assert d["grailzee"] == "YES"
        assert d["format"] == "Reserve"

    def test_reserve_price_calculated(self):
        """Reserve price = round(buy + fees + 2% buffer, -1).

        purchase=2700, RES fees=199, buffer=2700*0.02=54
        reserve_price = round(2700 + 199 + 54, -1) = round(2953, -1) = 2950
        """
        entry = _make_ref(signal="Careful", risk_nr=35.0)
        d = _score_decision(entry, 2700)
        assert d["format"] == "Reserve"
        assert d["reserve_price"] == 2950

    def test_no_reserve_price_on_nr(self):
        """NR format -> reserve_price is None."""
        entry = _make_ref(signal="Strong", risk_nr=8.5)
        d = _score_decision(entry, 2750)
        assert d["format"] == "NR"
        assert d["reserve_price"] is None


class TestRiskReserveThresholdParity:
    """Phase A.2: _score_decision reads risk_reserve_threshold_fraction
    from analyzer_config. Output must be identical whether the config
    file is present (factory defaults) or absent (fallback path).

    Covers two branches where the threshold changes the decision tree:
    the Careful/Reserve MAYBE branch and the implicit signal=Pass branch.
    """

    def setup_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def teardown_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def _decide(self, entry, price, config_path=None):
        from scripts.grailzee_common import (
            _reset_analyzer_config_cache,
            load_analyzer_config,
        )
        _reset_analyzer_config_cache()
        load_analyzer_config(
            path=(str(config_path) if config_path else "/tmp/__absent_for_eval__")
        )
        return _score_decision(entry, price)

    def test_reserve_in_band_parity(self, tmp_path):
        """Reserve signal risk=25% -> MAYBE branch; identical both ways."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import ANALYZER_CONFIG_FACTORY_DEFAULTS

        cfg = tmp_path / "analyzer_config.json"
        write_config(
            cfg,
            json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS)),
            [], "test",
        )
        entry = _make_ref(
            signal="Reserve", risk_nr=25.0,
            max_buy_nr=2910, max_buy_res=2860,
        )

        absent = self._decide(entry, 2700, config_path=None)
        present = self._decide(entry, 2700, config_path=cfg)
        assert absent == present

    def test_careful_above_threshold_parity(self, tmp_path):
        """Careful signal risk=45% -> YES (recommend_reserve=True)."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import ANALYZER_CONFIG_FACTORY_DEFAULTS

        cfg = tmp_path / "analyzer_config.json"
        write_config(
            cfg,
            json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS)),
            [], "test",
        )
        entry = _make_ref(
            signal="Careful", risk_nr=45.0,
            max_buy_nr=2910, max_buy_res=2860,
        )

        absent = self._decide(entry, 2700, config_path=None)
        present = self._decide(entry, 2700, config_path=cfg)
        assert absent == present

    def test_pass_signal_parity(self, tmp_path):
        """signal='Pass' -> NO (independent of threshold, but still must match)."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import ANALYZER_CONFIG_FACTORY_DEFAULTS

        cfg = tmp_path / "analyzer_config.json"
        write_config(
            cfg,
            json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS)),
            [], "test",
        )
        entry = _make_ref(
            signal="Pass", risk_nr=65.0,
            max_buy_nr=2910, max_buy_res=2860,
        )

        absent = self._decide(entry, 2700, config_path=None)
        present = self._decide(entry, 2700, config_path=cfg)
        assert absent == present
        assert absent["grailzee"] == "NO"

    def test_threshold_change_shifts_decision(self, tmp_path):
        """Discriminative power: lowering threshold to 20% flips a
        risk=30% Reserve entry from MAYBE to YES-on-Reserve."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import ANALYZER_CONFIG_FACTORY_DEFAULTS

        cfg = tmp_path / "analyzer_config.json"
        content = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        content["scoring"]["risk_reserve_threshold_fraction"] = 0.20
        write_config(cfg, content, [], "test")

        entry = _make_ref(
            signal="Reserve", risk_nr=30.0,
            max_buy_nr=2910, max_buy_res=2860,
        )

        absent = self._decide(entry, 2700, config_path=None)
        tightened = self._decide(entry, 2700, config_path=cfg)
        # With factory default (40%): risk=30 < 40 -> recommend_reserve=False
        # -> MAYBE branch. With tightened (20%): risk=30 > 20 ->
        # recommend_reserve=True -> YES.
        assert absent["grailzee"] == "MAYBE"
        assert tightened["grailzee"] == "YES"


class TestAdBudget:
    """Verify ad_budget appears correctly in response."""

    def test_ad_budget_low_median(self, tmp_path):
        """median=2000 <= 3500 -> '$37\u201350'"""
        cache = _make_cache(refs={"TEST": _make_ref(
            reference="TEST", median=2000, max_buy_nr=1760,
            max_buy_res=1720, signal="Strong", risk_nr=5.0,
        )})
        cache_path = _write_cache(tmp_path, cache)
        result = evaluate(
            "Test", "TEST", 1500,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["ad_budget"] == "$37\u201350"

    def test_ad_budget_high_median(self, tmp_path):
        """median=6000: 5000 < 6000 <= 10000 -> '$200\u2013250'"""
        cache = _make_cache(refs={"HIGHREF": _make_ref(
            reference="HIGHREF", median=6000,
            # max_buy_nr = round((6000-149)/1.05, -1) = round(5572.38, -1) = 5570
            max_buy_nr=5570,
            max_buy_res=5530,
            signal="Strong", risk_nr=5.0,
        )})
        cache_path = _write_cache(tmp_path, cache)
        result = evaluate(
            "Test", "HIGHREF", 4000,
            cache_path=cache_path,
            ledger_path=str(tmp_path / "no_ledger.csv"),
            cycle_focus_path=str(tmp_path / "no_focus.json"),
            reports_csv_dir=str(tmp_path / "no_csv"),
        )
        assert result["ad_budget"] == "$200\u2013250"
