"""Tests for scripts.write_cache; analysis_cache.json (v3 schema) per schema v2.0 doc.

v3 post-fixup 2026-04-24: market fields live in buckets; reference-level
fields are identity + trend/momentum + `confidence` only. Ledger-vs-market
comparison (premium_vs_market, realized_premium) is no longer in the cache;
strategy session computes it at read time. Cross-bucket signal aggregates
(strong_count etc.) are no longer in summary.

Hand-computed fixture:
  Ref 79830RB: brand=Tudor, model=BB GMT, named=True (buckets empty in
    fixture; per-bucket shape covered by test_analyze_buckets.py).
  Ref A17320: brand=Breitling, model=SO Heritage, named=True.
  Ref NEW123: brand=Unknown, model=NEW123, named=False.

  Emerged: [NEW123]  Breakouts: [{ref: 79830RB, signals: [...]}]
  hot_references = |{NEW123} union {79830RB}| = 2

  Ledger trades (for confidence):
    Tudor 79830RB: buy=2750, sell=3200, NR -> net=301, roi=10.95
"""

import json
import os
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
        actual_keys = set(cache.keys())
        missing = expected_keys - actual_keys
        assert not missing, f"Missing expected top-level keys: {missing}"

    def test_schema_version_is_3(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        assert cache["schema_version"] == 3
        assert CACHE_SCHEMA_VERSION == 3

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
# Per-reference shape (v3 post-fixup)
# ═══════════════════════════════════════════════════════════════════════


class TestPerReferenceShape:
    """v3 reference entries carry identity + trend/momentum + `confidence` +
    `buckets` only. No reference-level market fields; no premium_vs_market;
    no realized_premium; no dominant-median proxy."""

    def test_expected_keys_present(self, tmp_path):
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["79830RB"]
        expected = {
            "brand", "model", "reference", "named",
            "trend_signal", "trend_median_change", "trend_median_pct",
            "momentum", "confidence", "buckets",
        }
        actual = set(ref.keys())
        missing = expected - actual
        assert not missing, f"Missing expected per-reference keys: {missing}"

    def test_ripped_fields_absent(self, tmp_path):
        """Regression guard against judgment-creep re-adding the ripped
        fields. If any of these names comes back, the rip lost."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ripped = {
            "premium_vs_market_pct", "premium_vs_market_sale_count",
            "realized_premium_pct", "realized_premium_trade_count",
            "median", "max_buy_nr", "max_buy_res", "risk_nr", "signal",
            "volume", "st_pct", "condition_mix",
            "capital_required_nr", "capital_required_res",
            "expected_net_at_median_nr", "expected_net_at_median_res",
        }
        for ref_key, ref_entry in cache["references"].items():
            leaked = ripped & set(ref_entry.keys())
            assert not leaked, f"{ref_key}: ripped fields leaked: {leaked}"

    def test_identity_values(self, tmp_path):
        """Identity fields (brand, model, reference, named) match input."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["79830RB"]
        assert ref["brand"] == "Tudor"
        assert ref["model"] == "BB GMT"
        assert ref["reference"] == "79830RB"
        assert ref["named"] is True

    def test_trend_threaded(self, tmp_path):
        """79830RB has a trend entry -> trend_signal/change/pct carry it."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["79830RB"]
        assert ref["trend_signal"] == "Momentum"
        assert ref["trend_median_change"] == 200
        assert ref["trend_median_pct"] == 6.67
        assert ref["momentum"] == {"score": 2, "label": "Heating Up"}

    def test_buckets_passed_through(self, tmp_path):
        """buckets dict on input -> buckets dict on output (unchanged)."""
        args = list(_fixture(tmp_path))
        args[0]["references"]["79830RB"]["buckets"] = {
            "arabic|nr|black": {"signal": "Strong", "volume": 5},
        }
        path = write_cache(*tuple(args))
        cache = _load(path)
        assert cache["references"]["79830RB"]["buckets"] == {
            "arabic|nr|black": {"signal": "Strong", "volume": 5},
        }

    def test_buckets_default_empty(self, tmp_path):
        """Reference input without a `buckets` field -> entry has `buckets: {}`."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        # Fixture _ref() doesn't set buckets
        assert cache["references"]["79830RB"]["buckets"] == {}

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
# DJ config shape (v3 post-fixup)
# ═══════════════════════════════════════════════════════════════════════


class TestDJConfigShape:
    """DJ config entries: identity fields carry inherited/declared values;
    confidence and trend fields are always null (no per-config ledger
    or trend data). No premium_vs_market / realized_premium inheritance
    in v3 post-fixup."""

    def _dj_args(self, tmp_path):
        args = list(_fixture(tmp_path))
        args[0] = {
            "references": {},
            "dj_configs": {
                "Rose/Jubilee": {
                    "brand": "Rolex", "model": "DJ 41 Rose/Jubilee",
                    "reference": "126300", "section": "dj_config",
                    "buckets": {},
                },
            },
            "unnamed": [],
        }
        args[6] = {"trades": [], "summary": {"total_trades": 0}}
        return tuple(args)

    def test_confidence_null(self, tmp_path):
        path = write_cache(*self._dj_args(tmp_path))
        cache = _load(path)
        assert cache["dj_configs"]["Rose/Jubilee"]["confidence"] is None

    def test_trend_all_null(self, tmp_path):
        """trend_signal / _change / _pct / momentum all null, not string or 0."""
        path = write_cache(*self._dj_args(tmp_path))
        cache = _load(path)
        cfg = cache["dj_configs"]["Rose/Jubilee"]
        assert cfg["trend_signal"] is None
        assert cfg["trend_median_change"] is None
        assert cfg["trend_median_pct"] is None
        assert cfg["momentum"] is None

    def test_no_premium_fields_inherited(self, tmp_path):
        """Ripped fields do not leak into DJ config entries."""
        path = write_cache(*self._dj_args(tmp_path))
        cache = _load(path)
        cfg = cache["dj_configs"]["Rose/Jubilee"]
        ripped = {
            "premium_vs_market_pct", "premium_vs_market_sale_count",
            "realized_premium_pct", "realized_premium_trade_count",
        }
        leaked = ripped & set(cfg.keys())
        assert not leaked, f"Ripped fields leaked into DJ config: {leaked}"


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
        """A17320 has no trend entry -> trend fields are null (bug 2 fix)."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        ref = cache["references"]["A17320"]
        assert ref["trend_signal"] is None
        assert ref["trend_median_change"] is None
        assert ref["trend_median_pct"] is None

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
        """Post-fixup: no per-signal reference counts in summary; only
        counts that do not synthesize judgment across buckets stay."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        s = cache["summary"]
        assert s["total_references"] == 3
        assert s["emerged_count"] == 1
        assert s["breakout_count"] == 1
        assert s["watchlist_count"] == 1
        assert s["unnamed_count"] == 1

    def test_per_signal_counts_absent(self, tmp_path):
        """strong_count/normal_count/reserve_count/caution_count were
        ripped because signal is per-bucket (cross-bucket aggregation
        is judgment)."""
        path = write_cache(*_fixture(tmp_path))
        cache = _load(path)
        s = cache["summary"]
        for key in ("strong_count", "normal_count", "reserve_count", "caution_count"):
            assert key not in s, f"ripped summary field leaked: {key}"

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
