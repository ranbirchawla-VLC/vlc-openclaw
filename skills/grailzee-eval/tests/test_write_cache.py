"""Tests for scripts.write_cache; analysis_cache.json (v2 schema) per guide Section 13.

Extraction from v1 write_cache.py. Schema upgraded to v2. v1/v2 delta
tested via full deep-dict equality against hand-computed expected cache.

Hand-computed fixture:
──────────────────────────────────────────────────────────────────────
  Ref 79830RB: brand=Tudor, model=BB GMT, named=True,
    median=3200, max_buy_nr=2910, max_buy_res=2770, risk_nr=8.0,
    signal=Strong, volume=5, st_pct=0.6
  Ref A17320: brand=Breitling, model=SO Heritage, named=True,
    median=2400, risk_nr=25.0, signal=Reserve, volume=3
  Ref NEW123: brand=Unknown, model=NEW123, named=False,
    median=5000, signal=Normal, volume=4

  Emerged: [NEW123]  Breakouts: [{ref: 79830RB, signals: [...]}]
  hot_references = |{NEW123} union {79830RB}| = 2

  Summary (3 refs): strong=1, normal=1, reserve=1, caution=0,
    emerged=1, breakout=1, watchlist=1, unnamed=1, hot=2

  Ledger trades (for premium + confidence):
    Tudor 79830RB: buy=2750, sell=3200, NR -> net=301, roi=10.95
    Premium: 1 trade, avg_premium=0 (no median_at_trade), threshold not met,
      trades_to_threshold=9
──────────────────────────────────────────────────────────────────────
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from scripts.write_cache import write_cache, _backup_existing, _build_premium_status, CACHE_SCHEMA_VERSION


def _ref(brand="Tudor", model="BB GMT", reference="79830RB",
         named=True, median=3200, max_buy_nr=2910, max_buy_res=2770,
         risk_nr=8.0, signal="Strong", volume=5, st_pct=0.6,
         recommend_reserve=False) -> dict:
    return {
        "brand": brand, "model": model, "reference": reference,
        "named": named, "median": median, "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res, "risk_nr": risk_nr, "signal": signal,
        "volume": volume, "st_pct": st_pct,
        "recommend_reserve": recommend_reserve,
    }


def _trade(brand="Tudor", reference="79830RB", buy=2750, sell=3200,
           account="NR", net=301, roi=10.95, premium=None) -> dict:
    return {
        "sell_date": "2026-03-15", "sell_cycle_id": "cycle_2026-06",
        "buy_date": None, "buy_cycle_id": None,
        "brand": brand, "reference": reference,
        "account": account, "buy_price": buy, "sell_price": sell,
        "platform_fees": 149 if account == "NR" else 199,
        "net_profit": net, "roi_pct": roi,
        "median_at_trade": None, "max_buy_at_trade": None,
        "model_correct": None, "premium_vs_median": premium,
    }


def _fixture(tmp_path):
    all_results = {
        "references": {
            "79830RB": _ref(),
            "A17320": _ref(brand="Breitling", model="SO Heritage",
                           reference="A17320", median=2400, max_buy_nr=2140,
                           max_buy_res=2100, risk_nr=25.0, signal="Reserve",
                           volume=3, st_pct=0.45),
            "NEW123": _ref(brand="Unknown", model="NEW123",
                           reference="NEW123", named=False, median=5000,
                           max_buy_nr=4620, max_buy_res=4570, risk_nr=15.0,
                           signal="Normal", volume=4, st_pct=None),
        },
        "dj_configs": {},
        "unnamed": ["NEW123"],
    }
    trends = {
        "trends": [{
            "reference": "79830RB", "brand": "Tudor", "model": "BB GMT",
            "prev_median": 3000, "curr_median": 3200, "med_change": 200,
            "med_pct": 6.67, "signal_str": "Momentum",
            "signals": ["Momentum"],
            "prev_st": 0.5, "curr_st": 0.6, "st_change": 10.0,
            "prev_vol": 4, "curr_vol": 5,
        }],
        "momentum": {"79830RB": {"score": 2, "label": "Heating Up"}},
    }
    changes = {
        "emerged": ["NEW123"],
        "shifted": {"79830RB": {"direction": "up", "pct": 6.7}},
        "faded": [],
        "unnamed": ["NEW123"],
    }
    breakouts = {
        "breakouts": [{"reference": "79830RB", "signals": ["Momentum"]}],
        "count": 1,
    }
    watchlist_data = {
        "watchlist": [{"reference": "91650", "current_sales": 2, "avg_price": 1550}],
        "count": 1,
    }
    brands_data = {
        "brands": {"Tudor": {
            "reference_count": 2, "avg_momentum": 1.0,
            "warming": 1, "cooling": 0, "signal": "Brand heating",
        }},
        "count": 1,
    }
    ledger_stats = {
        "trades": [_trade()],
        "summary": {"total_trades": 1},
    }
    cache_path = str(tmp_path / "state" / "analysis_cache.json")
    backup_path = str(tmp_path / "backup")
    return (all_results, trends, changes, breakouts, watchlist_data,
            brands_data, ledger_stats, "cycle_2026-07", "grailzee_2026-04-12.csv",
            None, cache_path, backup_path)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


# ═══════════════════════════════════════════════════════════════════════
# Full v2 schema deep equality
# ═══════════════════════════════════════════════════════════════════════


class TestFullSchema:
    def test_top_level_keys(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        expected_keys = {
            "schema_version", "generated_at", "source_report", "cycle_id",
            "market_window", "premium_status", "references", "dj_configs",
            "changes", "breakouts", "watchlist", "brands", "unnamed", "summary",
        }
        assert set(cache.keys()) == expected_keys

    def test_schema_version_is_2(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["schema_version"] == 2
        assert CACHE_SCHEMA_VERSION == 2

    def test_generated_at_iso8601(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        datetime.fromisoformat(cache["generated_at"])  # no exception

    def test_cycle_id(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["cycle_id"] == "cycle_2026-07"

    def test_source_report(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["source_report"] == "grailzee_2026-04-12.csv"

    def test_market_window_default(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["market_window"] == {"pricing_reports": [], "trend_reports": []}


# ═══════════════════════════════════════════════════════════════════════
# Per-reference shape
# ═══════════════════════════════════════════════════════════════════════


class TestPerReferenceShape:
    def test_all_fields_present(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["79830RB"]
        expected_keys = {
            "brand", "model", "reference", "named", "median",
            "max_buy_nr", "max_buy_res", "risk_nr", "signal",
            "volume", "st_pct", "momentum", "confidence",
            "premium_vs_market_pct", "premium_vs_market_sale_count",
            "trend_signal", "trend_median_change", "trend_median_pct",
        }
        assert set(ref.keys()) == expected_keys

    def test_fully_populated_reference(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["79830RB"]
        assert ref["brand"] == "Tudor"
        assert ref["model"] == "BB GMT"
        assert ref["reference"] == "79830RB"
        assert ref["named"] is True
        assert ref["median"] == 3200
        assert ref["max_buy_nr"] == 2910
        assert ref["max_buy_res"] == 2770
        assert ref["risk_nr"] == 8.0
        assert ref["signal"] == "Strong"
        assert ref["volume"] == 5
        assert ref["st_pct"] == 0.6
        assert ref["momentum"] == {"score": 2, "label": "Heating Up"}
        assert ref["trend_signal"] == "Momentum"
        assert ref["trend_median_change"] == 200
        assert ref["trend_median_pct"] == 6.67

    def test_confidence_from_ledger(self, tmp_path):
        """79830RB has 1 trade: net=301 > 0. roi=10.95. No premium data."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        conf = cache["references"]["79830RB"]["confidence"]
        assert conf is not None
        assert conf["trades"] == 1
        assert conf["profitable"] == 1
        assert conf["win_rate"] == 100.0
        assert conf["avg_roi"] == 10.9  # round(10.95, 1); float repr
        assert conf["avg_premium"] is None
        assert conf["last_trade"] == "2026-03-15"


# ═══════════════════════════════════════════════════════════════════════
# premium_vs_market_pct + premium_vs_market_sale_count (B.2)
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumVsMarket:
    """B.2: most-recent Vardalux sale on the reference vs current market
    median. Zero-floored; sale count reports total matching trades
    regardless of premium sign."""

    def _build_args(self, tmp_path, ref_median, trades):
        """Build write_cache args with a single reference at given median
        and a custom trades list."""
        args = list(_fixture(tmp_path))
        args[0] = {
            "references": {"79830RB": _ref(median=ref_median)},
            "dj_configs": {},
            "unnamed": [],
        }
        args[6] = {"trades": trades, "summary": {"total_trades": len(trades)}}
        return tuple(args)

    def test_no_sale_zero(self, tmp_path):
        """Reference with no matching ledger trades -> 0.0, count 0."""
        path = write_cache(*self._build_args(tmp_path, 3200, []))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 0

    def test_sale_above_median_positive_pct(self, tmp_path):
        """Most recent sale at 3520 vs median 3200 -> (3520-3200)/3200*100
        = 10.0."""
        trades = [_trade(sell=3520)]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 10.0
        assert ref["premium_vs_market_sale_count"] == 1

    def test_sale_at_median_zero(self, tmp_path):
        """Sale at exactly median -> 0.0 (floor)."""
        trades = [_trade(sell=3200)]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 1

    def test_sale_below_median_zero(self, tmp_path):
        """Sale below median -> 0.0 (floor); count still reports trade."""
        trades = [_trade(sell=3000)]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 1

    def test_only_most_recent_contributes(self, tmp_path):
        """Older sale above median + newer sale below median -> 0.0.
        Older sale must not leak into the value."""
        old_high = {**_trade(sell=4000), "sell_date": "2026-01-05"}
        recent_low = {**_trade(sell=3000), "sell_date": "2026-03-15"}
        trades = [old_high, recent_low]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 2

    def test_only_most_recent_contributes_inverse(self, tmp_path):
        """Older sale at median + newer sale above median -> positive pct
        from the newer sale only."""
        old_at = {**_trade(sell=3200), "sell_date": "2026-01-05"}
        recent_high = {**_trade(sell=3520), "sell_date": "2026-03-15"}
        trades = [old_at, recent_high]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 10.0
        assert ref["premium_vs_market_sale_count"] == 2

    def test_same_date_tiebreak_highest_price_wins(self, tmp_path):
        """Two sales on same sell_date -> highest sell_price is the
        'most recent' for premium purposes (new tiebreak convention)."""
        lo = {**_trade(sell=3300), "sell_date": "2026-03-15"}
        hi = {**_trade(sell=3600), "sell_date": "2026-03-15"}
        trades = [lo, hi]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        # hi wins: (3600-3200)/3200*100 = 12.5
        assert ref["premium_vs_market_pct"] == 12.5
        assert ref["premium_vs_market_sale_count"] == 2

    def test_cross_brand_same_reference_isolated(self, tmp_path):
        """A trade with the same reference under a different brand must
        not contaminate the computation. Mirrors the cross-brand
        isolation in _confidence_from_trades."""
        foreign = _trade(brand="Breitling", sell=5000)
        trades = [foreign]
        path = write_cache(*self._build_args(tmp_path, 3200, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 0

    def test_zero_median_collapses_to_zero(self, tmp_path):
        """Degenerate current_median (0 or None) -> 0.0 despite sales
        present. Count still reports matching trades."""
        trades = [_trade(sell=3520)]
        path = write_cache(*self._build_args(tmp_path, 0, trades))
        ref = _load(path)["references"]["79830RB"]
        assert ref["premium_vs_market_pct"] == 0.0
        assert ref["premium_vs_market_sale_count"] == 1

    def test_dj_configs_inherit_parent(self, tmp_path):
        """Per the B.2 addendum: DJ configs carry parent reference
        126300's values, because Grailzee Pro lacks dial-color
        granularity."""
        args = list(_fixture(tmp_path))
        args[0] = {
            "references": {"126300": _ref(
                brand="Rolex", model="DJ 41", reference="126300",
                median=10000, max_buy_nr=9100, max_buy_res=8900,
                risk_nr=5.0, signal="Strong", volume=50, st_pct=0.7,
            )},
            "dj_configs": {
                "Rose/Jubilee": {
                    "brand": "Rolex", "model": "DJ 41 Rose/Jubilee",
                    "reference": "126300", "section": "dj_config",
                    "median": 10500, "max_buy_nr": 9500, "max_buy_res": 9200,
                    "risk_nr": 4.0, "signal": "Strong", "volume": 20,
                    "st_pct": 0.75,
                },
                "Olive/Oyster": {
                    "brand": "Rolex", "model": "DJ 41 Olive/Oyster",
                    "reference": "126300", "section": "dj_config",
                    "median": 9800, "max_buy_nr": 8800, "max_buy_res": 8600,
                    "risk_nr": 6.0, "signal": "Normal", "volume": 15,
                    "st_pct": 0.65,
                },
            },
            "unnamed": [],
        }
        # One trade on parent 126300 at sell=11000 vs median 10000 -> 10.0
        args[6] = {
            "trades": [_trade(
                brand="Rolex", reference="126300", sell=11000,
            )],
            "summary": {"total_trades": 1},
        }
        path = write_cache(*tuple(args))
        cache = _load(path)

        parent = cache["references"]["126300"]
        assert parent["premium_vs_market_pct"] == 10.0
        assert parent["premium_vs_market_sale_count"] == 1

        for cfg_name in ("Rose/Jubilee", "Olive/Oyster"):
            cfg = cache["dj_configs"][cfg_name]
            assert cfg["premium_vs_market_pct"] == 10.0
            assert cfg["premium_vs_market_sale_count"] == 1

    def test_dj_configs_fall_back_when_parent_absent(self, tmp_path):
        """DJ configs without the parent 126300 in references get
        (0.0, 0) rather than crashing."""
        args = list(_fixture(tmp_path))
        args[0] = {
            "references": {},
            "dj_configs": {
                "Rose/Jubilee": {
                    "brand": "Rolex", "model": "DJ 41 Rose/Jubilee",
                    "reference": "126300", "section": "dj_config",
                    "median": 10500, "max_buy_nr": 9500, "max_buy_res": 9200,
                    "risk_nr": 4.0, "signal": "Strong", "volume": 20,
                    "st_pct": 0.75,
                },
            },
            "unnamed": [],
        }
        args[6] = {"trades": [], "summary": {"total_trades": 0}}
        path = write_cache(*tuple(args))
        cache = _load(path)

        assert "126300" not in cache["references"]
        cfg = cache["dj_configs"]["Rose/Jubilee"]
        assert cfg["premium_vs_market_pct"] == 0.0
        assert cfg["premium_vs_market_sale_count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Optional/null fields
# ═══════════════════════════════════════════════════════════════════════


class TestNullDefaults:
    def test_no_momentum(self, tmp_path):
        """A17320 has no momentum entry -> momentum is None."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["references"]["A17320"]["momentum"] is None

    def test_no_confidence(self, tmp_path):
        """A17320 has no ledger trades -> confidence is None."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["references"]["A17320"]["confidence"] is None

    def test_no_trend(self, tmp_path):
        """A17320 has no trend entry -> defaults."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["A17320"]
        assert ref["trend_signal"] == "No prior data"
        assert ref["trend_median_change"] == 0
        assert ref["trend_median_pct"] == 0

    def test_null_st_pct(self, tmp_path):
        """NEW123 has st_pct=None -> null in JSON."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["references"]["NEW123"]["st_pct"] is None

    def test_not_named(self, tmp_path):
        """NEW123 named=False."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["references"]["NEW123"]["named"] is False


# ═══════════════════════════════════════════════════════════════════════
# Backup rotation
# ═══════════════════════════════════════════════════════════════════════


class TestBackupTimestampCollision:
    """Flag #6: microsecond precision in backup filenames prevents silent
    overwrite when _backup_existing runs twice within the same second."""

    def test_distinct_filenames_within_same_second(self, tmp_path, monkeypatch):
        import scripts.write_cache as wc

        cache_path = tmp_path / "cache.json"
        backup_dir = tmp_path / "backup"
        cache_path.write_text("original")

        same_second = [
            datetime(2026, 4, 18, 14, 30, 52, 0),
            datetime(2026, 4, 18, 14, 30, 52, 500_000),
        ]

        class _FixedDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return same_second.pop(0)

        monkeypatch.setattr(wc, "datetime", _FixedDT)

        _backup_existing(str(cache_path), str(backup_dir))
        _backup_existing(str(cache_path), str(backup_dir))

        files = [f for f in os.listdir(str(backup_dir))
                 if f.startswith("analysis_cache_") and f.endswith(".json")]
        assert len(files) == 2, files


class TestBackupRotation:
    def test_keeps_last_10(self, tmp_path):
        """Pre-create 11 backup files, write once to trigger rotation, assert 10 retained."""
        cache_path = str(tmp_path / "state" / "analysis_cache.json")
        backup_dir = str(tmp_path / "backup")
        os.makedirs(backup_dir, exist_ok=True)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        # Pre-create 11 backup files with distinct sorted names
        for i in range(11):
            name = f"analysis_cache_20260101_{i:06d}.json"
            Path(backup_dir, name).write_text("{}")

        assert len(os.listdir(backup_dir)) == 11

        # Write a cache (which creates backup #12, then trims to 10)
        Path(cache_path).write_text("{}")
        write_cache(
            {"references": {}}, {}, {}, {"breakouts": []},
            {"watchlist": []}, {"brands": {}}, {"trades": []},
            "cycle_2026-01",
            cache_path=cache_path, backup_path=backup_dir,
        )

        backups = [f for f in os.listdir(backup_dir)
                   if f.startswith("analysis_cache_") and f.endswith(".json")]
        assert len(backups) == 10


# ═══════════════════════════════════════════════════════════════════════
# Summary aggregation
# ═══════════════════════════════════════════════════════════════════════


class TestSummaryAggregation:
    def test_summary_counts(self, tmp_path):
        """Hand-computed: 1 Strong, 1 Normal, 1 Reserve, 0 Careful."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        s = cache["summary"]
        assert s["total_references"] == 3
        assert s["strong_count"] == 1
        assert s["normal_count"] == 1
        assert s["reserve_count"] == 1
        assert s["caution_count"] == 0
        assert s["emerged_count"] == 1
        assert s["breakout_count"] == 1
        assert s["watchlist_count"] == 1
        assert s["unnamed_count"] == 1

    def test_hot_references_set_union(self, tmp_path):
        """emerged={NEW123}, breakouts={79830RB} -> union = 2."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["summary"]["hot_references"] == 2

    def test_hot_references_overlap_no_double_count(self, tmp_path):
        """A ref in both emerged and breakouts counts once."""
        args = list(_fixture(tmp_path))
        # Make 79830RB both emerged and a breakout
        args[2] = {
            "emerged": ["79830RB"],
            "shifted": {}, "faded": [], "unnamed": [],
        }
        args[3] = {
            "breakouts": [{"reference": "79830RB", "signals": ["Momentum"]}],
            "count": 1,
        }
        path = write_cache(*args)
        cache = _load(path)
        # Set union: {79830RB} | {79830RB} = {79830RB} = 1
        assert cache["summary"]["hot_references"] == 1

    def test_premium_status_string(self, tmp_path):
        """Fixture trade has premium_vs_median=None -> 0 valid premium trades."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["summary"]["premium_status"] == "0 trades, +0%, 10 to threshold"


# ═══════════════════════════════════════════════════════════════════════
# Premium status block
# ═══════════════════════════════════════════════════════════════════════


class TestPremiumStatus:
    def test_premium_block(self, tmp_path):
        """1 trade, no premium data -> avg_premium=0, threshold not met."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ps = cache["premium_status"]
        assert ps["trade_count"] == 0  # 0 because premium_vs_median is None
        assert ps["avg_premium"] == 0
        assert ps["threshold_met"] is False
        assert ps["adjustment"] == 0
        assert ps["trades_to_threshold"] == 10

    def test_trades_to_threshold_math(self):
        """max(0, 10 - trade_count)."""
        trades = [{"premium_vs_median": 10.0, "median_at_trade": 3000}] * 8
        ps = _build_premium_status(trades)
        assert ps["trades_to_threshold"] == 2
        assert ps["trade_count"] == 8

    def test_threshold_met_zero_remaining(self):
        """10+ trades at 8%+ -> threshold met, trades_to_threshold=0."""
        trades = [{"premium_vs_median": 10.0, "median_at_trade": 3000}] * 12
        ps = _build_premium_status(trades)
        assert ps["threshold_met"] is True
        assert ps["trades_to_threshold"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Changes, breakouts, watchlist, brands pass-through
# ═══════════════════════════════════════════════════════════════════════


class TestPassThrough:
    def test_changes(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["changes"]["emerged"] == ["NEW123"]
        assert cache["changes"]["shifted"] == {"79830RB": {"direction": "up", "pct": 6.7}}
        assert cache["changes"]["faded"] == []

    def test_breakouts(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert len(cache["breakouts"]) == 1
        assert cache["breakouts"][0]["reference"] == "79830RB"

    def test_watchlist(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert len(cache["watchlist"]) == 1
        assert cache["watchlist"][0]["reference"] == "91650"

    def test_brands(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert "Tudor" in cache["brands"]
        assert cache["brands"]["Tudor"]["signal"] == "Brand heating"

    def test_unnamed(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["unnamed"] == ["NEW123"]


# ═══════════════════════════════════════════════════════════════════════
# Empty inputs
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyInputs:
    def test_empty_everything(self, tmp_path):
        cache_path = str(tmp_path / "cache.json")
        backup_path = str(tmp_path / "backup")
        path = write_cache(
            {}, {}, {}, {"breakouts": []}, {"watchlist": []},
            {"brands": {}}, {"trades": []}, "cycle_0000-00",
            cache_path=cache_path, backup_path=backup_path,
        )
        cache = _load(path)
        assert cache["references"] == {}
        assert cache["summary"]["total_references"] == 0
        assert cache["summary"]["strong_count"] == 0
        assert cache["summary"]["hot_references"] == 0
        assert cache["breakouts"] == []
        assert cache["watchlist"] == []


# ═══════════════════════════════════════════════════════════════════════
# Idempotency
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotency:
    def test_identical_except_generated_at(self, tmp_path):
        args = _fixture(tmp_path)
        path1 = write_cache(*args)
        c1 = _load(path1)
        # Second write (backup of first, then overwrite)
        path2 = write_cache(*args)
        c2 = _load(path2)
        # Remove generated_at for comparison
        c1.pop("generated_at")
        c2.pop("generated_at")
        assert c1 == c2


# ═══════════════════════════════════════════════════════════════════════
# Run history
# ═══════════════════════════════════════════════════════════════════════


class TestRunHistory:
    def test_appends_entries(self, tmp_path):
        args = _fixture(tmp_path)
        write_cache(*args)
        write_cache(*args)
        history_path = os.path.join(os.path.dirname(args[10]), "run_history.json")
        history = json.loads(Path(history_path).read_text())
        assert len(history) == 2
        assert history[0]["cycle_id"] == "cycle_2026-07"

    def test_rotation_cap_50(self, tmp_path):
        """Write 51 entries, assert 50 retained."""
        cache_path = str(tmp_path / "state" / "analysis_cache.json")
        backup_path = str(tmp_path / "backup")
        for i in range(51):
            write_cache(
                {"references": {}}, {}, {}, {"breakouts": []},
                {"watchlist": []}, {"brands": {}}, {"trades": []},
                f"cycle_2026-{i:02d}",
                cache_path=cache_path, backup_path=backup_path,
            )
        history_path = str(tmp_path / "state" / "run_history.json")
        history = json.loads(Path(history_path).read_text())
        assert len(history) == 50
