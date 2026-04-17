"""Tests for scripts.build_summary; markdown analysis summary.

Partial extraction from v1 analyze_report.py:601-714, expanded for v2
analysis dimensions. v1/v2 equivalence is structural (section headings
and table format), not content-identical (v2 adds breakouts, watchlist,
brands sections).

Fixture reference:
  79830RB: signal=Strong, recommend_reserve=False, max_buy_nr=2910
  A17320:  signal=Normal, recommend_reserve=True,  max_buy_res=2100
"""

from pathlib import Path

import pytest

from scripts.build_summary import build_summary


def _ref(brand: str = "Tudor", model: str = "BB GMT", reference: str = "79830RB",
         signal: str = "Strong", recommend_reserve: bool = False,
         max_buy_nr: float = 2910, max_buy_res: float = 2770,
         risk_nr: float = 8.0, st_pct: float = 0.6, volume: int = 5,
         median: float = 3200, named: bool = True) -> dict:
    return {
        "brand": brand, "model": model, "reference": reference,
        "median": median, "st_pct": st_pct, "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res, "risk_nr": risk_nr, "signal": signal,
        "recommend_reserve": recommend_reserve, "floor": 3000, "volume": volume,
        "named": named,
    }


def _full_inputs() -> dict:
    return {
        "all_results": {
            "references": {
                "79830RB": _ref(),
                "A17320": _ref(brand="Breitling", model="SO Heritage", reference="A17320",
                               signal="Normal", recommend_reserve=True, max_buy_res=2100,
                               risk_nr=25.0),
            },
            "dj_configs": {
                "Black/Oyster": _ref(brand="Rolex", model="DJ 41 Black/Oyster",
                                     reference="126300", median=9500, max_buy_nr=8900),
            },
        },
        "trends": {
            "trends": [{
                "reference": "79830RB", "brand": "Tudor", "model": "BB GMT",
                "prev_median": 3000, "curr_median": 3200, "med_change": 200,
                "med_pct": 6.67, "prev_st": None, "curr_st": None,
                "st_change": None, "prev_vol": 4, "curr_vol": 5,
                "signals": ["Momentum"], "signal_str": "Momentum",
            }],
            "momentum": {"79830RB": {"score": 1, "label": "Warming"}},
        },
        "changes": {
            "emerged": ["NEW123"],
            "shifted": {"79830RB": {"direction": "up", "pct": 6.7}},
            "faded": [],
            "unnamed": [],
        },
        "breakouts": {
            "breakouts": [{"reference": "79830RB", "signals": ["Momentum"]}],
            "count": 1,
        },
        "watchlist": {
            "watchlist": [{"reference": "91650", "current_sales": 2, "avg_price": 1550}],
            "count": 1,
        },
        "brands": {
            "brands": {"Tudor": {
                "reference_count": 3, "avg_momentum": 1.0,
                "warming": 2, "cooling": 0, "signal": "Brand heating",
            }},
            "count": 1,
        },
        "ledger_stats": {
            "trades": [],
            "summary": {
                "total_trades": 5, "profitable": 4, "win_rate": 80.0,
                "total_net_profit": 1200, "avg_roi_pct": 7.5, "total_deployed": 15000,
            },
        },
        "current_cycle_id": "cycle_2026-07",
    }


def _build(tmp_path, **overrides):
    inputs = _full_inputs()
    inputs.update(overrides)
    return build_summary(
        inputs["all_results"], inputs["trends"], inputs["changes"],
        inputs["breakouts"], inputs["watchlist"], inputs["brands"],
        inputs["ledger_stats"], inputs["current_cycle_id"], str(tmp_path),
    )


# ═══════════════════════════════════════════════════════════════════════
# Section presence
# ═══════════════════════════════════════════════════════════════════════


class TestSectionPresence:
    def test_market_snapshot(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Market Snapshot" in content

    def test_nr_buy_targets(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## NR Buy Targets" in content

    def test_reserve_candidates(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Reserve Candidates" in content

    def test_dj_configs(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Datejust 126300" in content

    def test_trend_movers(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Trend Movers" in content

    def test_emerged(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Emerged References" in content
        assert "NEW123" in content

    def test_breakouts(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Breakouts" in content

    def test_watchlist(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Watchlist" in content
        assert "91650" in content

    def test_brand_signals(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "## Brand Signals" in content
        assert "Brand heating" in content


# ═══════════════════════════════════════════════════════════════════════
# Cycle ID and key metrics
# ═══════════════════════════════════════════════════════════════════════


class TestKeyMetrics:
    def test_cycle_id_in_output(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "cycle_2026-07" in content

    def test_ledger_stats(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "5 trades" in content
        assert "80.0% win rate" in content

    def test_reference_counts(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "2 references scored" in content

    def test_rising_trend(self, tmp_path):
        path = _build(tmp_path)
        content = Path(path).read_text()
        assert "Rising:" in content


# ═══════════════════════════════════════════════════════════════════════
# Empty input
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyInput:
    def test_empty_produces_valid_markdown(self, tmp_path):
        path = build_summary({}, {}, {}, {}, {}, {}, {}, "cycle_0000-00", str(tmp_path))
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "## Market Snapshot" in content
        assert "0 references scored" in content

    def test_filename_convention(self, tmp_path):
        path = build_summary({}, {}, {}, {}, {}, {}, {}, "cycle_0000-00", str(tmp_path))
        assert "Vardalux_Grailzee_Analysis_" in Path(path).name
        assert path.endswith(".md")

    def test_empty_breakouts(self, tmp_path):
        """No breakouts -> no Breakouts section."""
        path = _build(tmp_path, breakouts={"breakouts": [], "count": 0})
        content = Path(path).read_text()
        assert "## Breakouts" not in content

    def test_empty_watchlist(self, tmp_path):
        path = _build(tmp_path, watchlist={"watchlist": [], "count": 0})
        content = Path(path).read_text()
        assert "## Watchlist" not in content
