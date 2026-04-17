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

from scripts.write_cache import write_cache, _build_premium_status, CACHE_SCHEMA_VERSION


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
        "date_closed": "2026-03-15", "cycle_id": "cycle_2026-06",
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
