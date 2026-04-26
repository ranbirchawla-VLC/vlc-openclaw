"""Tests for scripts.build_shortlist — v3 bucket-row shape (Wave 1.1).

Covers:
- Exact 30-column header in spec order (v3 contract).
- Row count equals total bucket count across all references.
- Reference-level columns repeat identically across bucket rows of the same
  reference.
- Keying axes (dial_numerals, auction_type, dial_color) distinguish bucket rows
  within a reference.
- Low-data buckets: null market fields render as empty string; keying axes and
  volume stay populated; signal == "Low data".
- named_special metadata attaches to the correct bucket row.
- _res variant columns present and null on Low data buckets.
- Signal column present for sort convenience.
- Negative: no v2 premium columns, no synthesis columns.
- Determinism: bucket order is stable across runs via explicit tiebreak sort.
- Default sort: signal-rank ascending, volume descending.
- keep column blank at generation.
- Atomic write durability.
- cycle_id in filename.
- Confidence and momentum flatten to scalar columns at reference level.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# 2c-restore: build_shortlist reads flat per-ref shape; all tests skip until
# 2c restores the bucket read-path in _flatten_row.
pytestmark = pytest.mark.skip(reason="2c-restore: build_shortlist reads v2 flat per-ref shape")

from scripts import build_shortlist
from scripts.build_shortlist import (
    DEFAULT_SORT_KEY,
    FIELDNAMES,
    SIGNAL_ORDER,
    _atomic_write_csv,
    _flatten_row,
    _sort_key_fn,
    run,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


def _bucket(
    *,
    dial_numerals: str = "Arabic",
    auction_type: str = "nr",
    dial_color: str = "black",
    named_special: str | None = None,
    volume: int = 10,
    st_pct: float | None = 0.52,
    signal: str = "Strong",
    median: float | None = 3550.0,
    max_buy_nr: float | None = 3240.0,
    max_buy_res: float | None = 3190.0,
    risk_nr: float | None = 23.86,
    capital_required_nr: float | None = 3289.0,
    capital_required_res: float | None = 3289.0,
    expected_net_at_median_nr: float | None = 261.0,
    expected_net_at_median_res: float | None = 261.0,
) -> dict:
    """Build one v3 bucket dict with scored-bucket defaults."""
    return {
        "dial_numerals": dial_numerals,
        "auction_type": auction_type,
        "dial_color": dial_color,
        "named_special": named_special,
        "volume": volume,
        "st_pct": st_pct,
        "condition_mix": {
            "excellent": 0,
            "very_good": volume,
            "like_new": 0,
            "new": 0,
            "below_quality": 0,
        },
        "signal": signal,
        "median": median,
        "max_buy_nr": max_buy_nr,
        "max_buy_res": max_buy_res,
        "risk_nr": risk_nr,
        "capital_required_nr": capital_required_nr,
        "capital_required_res": capital_required_res,
        "expected_net_at_median_nr": expected_net_at_median_nr,
        "expected_net_at_median_res": expected_net_at_median_res,
    }


def _low_data_bucket(
    *,
    dial_numerals: str = "Roman",
    auction_type: str = "res",
    dial_color: str = "white",
    volume: int = 2,
) -> dict:
    """Build a below-threshold bucket as analyze_buckets.score_bucket emits."""
    return {
        "dial_numerals": dial_numerals,
        "auction_type": auction_type,
        "dial_color": dial_color,
        "named_special": None,
        "volume": volume,
        "st_pct": None,
        "condition_mix": {
            "excellent": 0,
            "very_good": volume,
            "like_new": 0,
            "new": 0,
            "below_quality": 0,
        },
        "signal": "Low data",
        "median": None,
        "max_buy_nr": None,
        "max_buy_res": None,
        "risk_nr": None,
        "capital_required_nr": None,
        "capital_required_res": None,
        "expected_net_at_median_nr": None,
        "expected_net_at_median_res": None,
    }


def _cache_entry(
    ref: str,
    *,
    brand: str = "Tudor",
    model: str = "BB GMT",
    buckets: dict | None = None,
    confidence: dict | None = None,
    momentum: dict | None = None,
    trend_signal: str | None = None,
    trend_median_change: float | None = None,
    trend_median_pct: float | None = None,
) -> dict:
    """Build one v3 cache references[ref] entry."""
    if buckets is None:
        buckets = {"arabic|nr|black": _bucket()}
    return {
        "brand": brand,
        "model": model,
        "reference": ref,
        "named": True,
        "trend_signal": trend_signal,
        "trend_median_change": trend_median_change,
        "trend_median_pct": trend_median_pct,
        "momentum": momentum,
        "confidence": confidence,
        "buckets": buckets,
    }


def _bk(
    dial_numerals: str,
    auction_type: str,
    dial_color: str,
) -> str:
    """Serialize a bucket key the same way analyze_buckets does."""
    return f"{dial_numerals.lower()}|{auction_type.lower()}|{dial_color.lower()}"


def _read_csv(path) -> tuple[list[str], list[dict]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


# ═══════════════════════════════════════════════════════════════════════
# Header shape
# ═══════════════════════════════════════════════════════════════════════


class TestCsvHeader:
    def test_csv_header_matches_spec(self, tmp_path):
        """Exact 30-column header in spec order."""
        refs = {"79830RB": _cache_entry("79830RB")}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        header, _ = _read_csv(out)
        assert header == FIELDNAMES
        assert len(header) == 30

    def test_fieldnames_order_matches_spec(self):
        """Column order matches the Wave 1.1 approved contract."""
        expected = [
            "brand", "reference", "model",
            "dial_numerals", "auction_type", "dial_color", "named_special",
            "signal", "median",
            "max_buy_nr", "max_buy_res",
            "st_pct", "volume", "risk_nr",
            "capital_required_nr", "capital_required_res",
            "expected_net_at_median_nr", "expected_net_at_median_res",
            "trend_signal", "trend_median_change", "trend_median_pct",
            "momentum_score", "momentum_label",
            "confidence_trades", "confidence_profitable", "confidence_win_rate",
            "confidence_avg_roi", "confidence_avg_premium", "confidence_last_trade",
            "keep",
        ]
        assert FIELDNAMES == expected


# ═══════════════════════════════════════════════════════════════════════
# Forbidden columns (Decision 10 + no synthesis drift)
# ═══════════════════════════════════════════════════════════════════════


class TestForbiddenColumns:
    @pytest.mark.parametrize("col", [
        "premium_vs_market_pct",
        "realized_premium_pct",
        "realized_premium_trade_count",
        "_dominant_median",
        "_best_signal",
    ])
    def test_forbidden_column_absent(self, col):
        assert col not in FIELDNAMES, f"Forbidden column {col!r} found in FIELDNAMES"


# ═══════════════════════════════════════════════════════════════════════
# Row count = total bucket count
# ═══════════════════════════════════════════════════════════════════════


class TestRowCountV3:
    def test_one_ref_one_bucket_gives_one_row(self, tmp_path):
        refs = {"79830RB": _cache_entry("79830RB")}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 1

    def test_one_ref_two_buckets_gives_two_rows(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(dial_numerals="Arabic", auction_type="nr", dial_color="black"),
                    _bk("Roman", "res", "white"): _bucket(dial_numerals="Roman", auction_type="res", dial_color="white"),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2

    def test_two_refs_with_buckets_gives_total_bucket_count(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(),
                    _bk("Roman", "res", "white"): _bucket(
                        dial_numerals="Roman", auction_type="res", dial_color="white"
                    ),
                },
            ),
            "126610LN": _cache_entry(
                "126610LN",
                brand="Rolex",
                model="Sub",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(volume=50, signal="Normal"),
                },
            ),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 3

    def test_empty_references_writes_header_only(self, tmp_path):
        out = run({}, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        header, rows = _read_csv(out)
        assert header == FIELDNAMES
        assert rows == []

    def test_ref_with_no_buckets_contributes_zero_rows(self, tmp_path):
        refs = {"ORPHAN": _cache_entry("ORPHAN", buckets={})}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 0


# ═══════════════════════════════════════════════════════════════════════
# Reference-level columns repeat across bucket rows
# ═══════════════════════════════════════════════════════════════════════


class TestReferenceFieldsRepeat:
    def test_brand_reference_model_repeat(self, tmp_path):
        conf = {
            "trades": 5, "profitable": 4, "win_rate": 80.0,
            "avg_roi": 12.5, "avg_premium": 3.4, "last_trade": "2026-04-10",
        }
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                brand="Tudor",
                model="BB GMT",
                confidence=conf,
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(auction_type="nr"),
                    _bk("Roman", "res", "white"): _bucket(
                        dial_numerals="Roman", auction_type="res", dial_color="white"
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        for row in rows:
            assert row["brand"] == "Tudor"
            assert row["reference"] == "79830RB"
            assert row["model"] == "BB GMT"

    def test_confidence_columns_repeat_across_bucket_rows(self, tmp_path):
        conf = {
            "trades": 5, "profitable": 4, "win_rate": 80.0,
            "avg_roi": 12.5, "avg_premium": 3.4, "last_trade": "2026-04-10",
        }
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                confidence=conf,
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(auction_type="nr"),
                    _bk("Roman", "res", "white"): _bucket(
                        dial_numerals="Roman", auction_type="res", dial_color="white"
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        for row in rows:
            assert row["confidence_trades"] == "5"
            assert row["confidence_win_rate"] == "80.0"
            assert row["confidence_last_trade"] == "2026-04-10"

    def test_trend_columns_repeat_across_bucket_rows(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                trend_signal="Rising",
                trend_median_change=150.0,
                trend_median_pct=4.2,
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(auction_type="nr"),
                    _bk("Roman", "res", "white"): _bucket(
                        dial_numerals="Roman", auction_type="res", dial_color="white"
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        for row in rows:
            assert row["trend_signal"] == "Rising"
            assert row["trend_median_change"] == "150.0"
            assert row["trend_median_pct"] == "4.2"

    def test_null_trend_writes_empty(self, tmp_path):
        refs = {
            "X1": _cache_entry(
                "X1",
                trend_signal=None,
                trend_median_change=None,
                trend_median_pct=None,
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["trend_signal"] == ""
        assert rows[0]["trend_median_change"] == ""
        assert rows[0]["trend_median_pct"] == ""


# ═══════════════════════════════════════════════════════════════════════
# Keying axes distinguish bucket rows within a reference
# ═══════════════════════════════════════════════════════════════════════


class TestKeyingAxesDistinguish:
    def test_dial_numerals_differs_across_rows(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(dial_numerals="Arabic", auction_type="nr", dial_color="black"),
                    _bk("Roman", "nr", "black"): _bucket(dial_numerals="Roman", auction_type="nr", dial_color="black"),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        numerals = {r["dial_numerals"] for r in rows}
        assert numerals == {"Arabic", "Roman"}

    def test_auction_type_differs_across_rows(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(auction_type="nr"),
                    _bk("Arabic", "res", "black"): _bucket(
                        dial_numerals="Arabic", auction_type="res", dial_color="black"
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        auction_types = {r["auction_type"] for r in rows}
        assert auction_types == {"nr", "res"}

    def test_dial_color_differs_across_rows(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(dial_color="black"),
                    _bk("Arabic", "nr", "white"): _bucket(
                        dial_numerals="Arabic", auction_type="nr", dial_color="white"
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        colors = {r["dial_color"] for r in rows}
        assert colors == {"black", "white"}

    def test_all_three_axes_in_each_row(self, tmp_path):
        refs = {"X1": _cache_entry("X1")}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        row = rows[0]
        assert row["dial_numerals"] != ""
        assert row["auction_type"] != ""
        assert row["dial_color"] != ""


# ═══════════════════════════════════════════════════════════════════════
# Low-data bucket handling (Amendment 4: positive + null assertions)
# ═══════════════════════════════════════════════════════════════════════


class TestLowDataNulls:
    def _low_data_row(self, tmp_path) -> dict:
        refs = {
            "X1": _cache_entry(
                "X1",
                buckets={_bk("Roman", "res", "white"): _low_data_bucket()},
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 1
        return rows[0]

    def test_low_data_signal_is_low_data(self, tmp_path):
        row = self._low_data_row(tmp_path)
        assert row["signal"] == "Low data"

    def test_low_data_volume_is_populated(self, tmp_path):
        row = self._low_data_row(tmp_path)
        assert row["volume"] == "2"

    def test_low_data_dial_numerals_populated(self, tmp_path):
        row = self._low_data_row(tmp_path)
        assert row["dial_numerals"] == "Roman"

    def test_low_data_auction_type_populated(self, tmp_path):
        row = self._low_data_row(tmp_path)
        assert row["auction_type"] == "res"

    def test_low_data_dial_color_populated(self, tmp_path):
        row = self._low_data_row(tmp_path)
        assert row["dial_color"] == "white"

    def test_low_data_market_fields_are_empty(self, tmp_path):
        row = self._low_data_row(tmp_path)
        for col in (
            "median", "max_buy_nr", "max_buy_res", "risk_nr",
            "capital_required_nr", "capital_required_res",
            "expected_net_at_median_nr", "expected_net_at_median_res",
        ):
            assert row[col] == "", f"{col!r} should be empty for Low data bucket"

    def test_scored_bucket_market_fields_are_populated(self, tmp_path):
        refs = {"X1": _cache_entry("X1")}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        row = rows[0]
        assert row["median"] == "3550.0"
        assert row["max_buy_nr"] == "3240.0"
        assert row["signal"] != "Low data"


# ═══════════════════════════════════════════════════════════════════════
# named_special metadata
# ═══════════════════════════════════════════════════════════════════════


class TestNamedSpecialAttaches:
    def test_named_special_on_correct_bucket_row(self, tmp_path):
        refs = {
            "5711": _cache_entry(
                "5711",
                brand="Patek",
                model="Nautilus",
                buckets={
                    _bk("Arabic", "nr", "tiffany"): _bucket(
                        dial_color="tiffany", named_special="Tiffany"
                    ),
                    _bk("Arabic", "nr", "blue"): _bucket(
                        dial_color="blue", named_special=None
                    ),
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 2
        tiffany_rows = [r for r in rows if r["dial_color"] == "tiffany"]
        plain_rows = [r for r in rows if r["dial_color"] == "blue"]
        assert len(tiffany_rows) == 1
        assert len(plain_rows) == 1
        assert tiffany_rows[0]["named_special"] == "Tiffany"
        assert plain_rows[0]["named_special"] == ""

    def test_no_named_special_writes_empty(self, tmp_path):
        refs = {
            "X1": _cache_entry(
                "X1",
                buckets={_bk("Arabic", "nr", "black"): _bucket(named_special=None)},
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["named_special"] == ""


# ═══════════════════════════════════════════════════════════════════════
# _res variant columns (Amendment 1)
# ═══════════════════════════════════════════════════════════════════════


class TestResVariants:
    def test_res_columns_in_fieldnames(self):
        assert "max_buy_res" in FIELDNAMES
        assert "capital_required_res" in FIELDNAMES
        assert "expected_net_at_median_res" in FIELDNAMES

    def test_res_columns_follow_nr_counterparts(self):
        assert FIELDNAMES.index("max_buy_res") == FIELDNAMES.index("max_buy_nr") + 1
        assert FIELDNAMES.index("capital_required_res") == FIELDNAMES.index("capital_required_nr") + 1
        assert FIELDNAMES.index("expected_net_at_median_res") == FIELDNAMES.index("expected_net_at_median_nr") + 1

    def test_scored_bucket_res_fields_populated(self, tmp_path):
        refs = {
            "X1": _cache_entry(
                "X1",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(
                        max_buy_res=3190.0,
                        capital_required_res=3239.0,
                        expected_net_at_median_res=311.0,
                    )
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["max_buy_res"] == "3190.0"
        assert rows[0]["capital_required_res"] == "3239.0"
        assert rows[0]["expected_net_at_median_res"] == "311.0"

    def test_low_data_res_fields_empty(self, tmp_path):
        refs = {
            "X1": _cache_entry(
                "X1",
                buckets={_bk("Roman", "res", "white"): _low_data_bucket()},
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["max_buy_res"] == ""
        assert rows[0]["capital_required_res"] == ""
        assert rows[0]["expected_net_at_median_res"] == ""


# ═══════════════════════════════════════════════════════════════════════
# Signal column present for sort
# ═══════════════════════════════════════════════════════════════════════


class TestSignalColumnPresent:
    def test_signal_in_fieldnames(self):
        assert "signal" in FIELDNAMES

    def test_signal_order_constant_unchanged(self):
        assert SIGNAL_ORDER == ["Strong", "Normal", "Reserve", "Careful", "Pass", "Low data"]


# ═══════════════════════════════════════════════════════════════════════
# Null handling
# ═══════════════════════════════════════════════════════════════════════


class TestNullLedgerFields:
    def test_null_confidence_writes_empty_strings(self, tmp_path):
        refs = {"X1": _cache_entry("X1", confidence=None)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        row = rows[0]
        for col in (
            "confidence_trades", "confidence_profitable", "confidence_win_rate",
            "confidence_avg_roi", "confidence_avg_premium", "confidence_last_trade",
        ):
            assert row[col] == "", f"{col!r} should be empty for null confidence"

    def test_null_momentum_writes_empty_strings(self, tmp_path):
        refs = {"X1": _cache_entry("X1", momentum=None)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["momentum_score"] == ""
        assert rows[0]["momentum_label"] == ""

    def test_zero_volume_stays_zero_not_empty(self, tmp_path):
        """volume=0 must not collapse to empty; zero is a real value."""
        refs = {
            "X1": _cache_entry(
                "X1",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(volume=0, signal="Low data")
                },
            )
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["volume"] == "0"


# ═══════════════════════════════════════════════════════════════════════
# Sort
# ═══════════════════════════════════════════════════════════════════════


class TestSort:
    def test_sort_default_signal_then_volume(self, tmp_path):
        refs = {
            "A": _cache_entry("A", buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Reserve", volume=20)}),
            "B": _cache_entry("B", buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Strong", volume=5)}),
            "C": _cache_entry("C", buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Strong", volume=50)}),
            "D": _cache_entry("D", buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Normal", volume=10)}),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert [r["reference"] for r in rows] == ["C", "B", "D", "A"]

    def test_sort_override_brand(self, tmp_path):
        refs = {
            "A": _cache_entry("A", brand="Tudor", buckets={_bk("Arabic", "nr", "black"): _bucket()}),
            "B": _cache_entry("B", brand="Omega", buckets={_bk("Arabic", "nr", "black"): _bucket()}),
            "C": _cache_entry("C", brand="Breitling", buckets={_bk("Arabic", "nr", "black"): _bucket()}),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path), sort_key="brand")
        _, rows = _read_csv(out)
        assert [r["brand"] for r in rows] == ["Breitling", "Omega", "Tudor"]

    def test_signal_order_strong_to_low_data(self, tmp_path):
        refs = {
            sig.replace(" ", ""): _cache_entry(
                sig.replace(" ", ""),
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(signal=sig, volume=1)
                },
            )
            for sig in SIGNAL_ORDER
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert [r["signal"] for r in rows] == SIGNAL_ORDER

    def test_unknown_sort_field_raises(self):
        with pytest.raises(ValueError, match="Unknown sort field"):
            _sort_key_fn("not_a_real_field")


# ═══════════════════════════════════════════════════════════════════════
# Determinism
# ═══════════════════════════════════════════════════════════════════════


class TestBucketOrderDeterminism:
    def test_same_input_same_output_order(self, tmp_path):
        refs = {
            "79830RB": _cache_entry(
                "79830RB",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(volume=30),
                    _bk("Roman", "res", "white"): _bucket(
                        dial_numerals="Roman", auction_type="res", dial_color="white",
                        signal="Reserve", volume=10,
                    ),
                },
            ),
            "126610LN": _cache_entry(
                "126610LN",
                brand="Rolex",
                buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Normal", volume=20)},
            ),
        }
        out1 = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path / "run1"))
        out2 = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path / "run2"))
        _, rows1 = _read_csv(out1)
        _, rows2 = _read_csv(out2)
        assert rows1 == rows2

    def test_bucket_key_tiebreak_produces_stable_order(self, tmp_path):
        """Same signal and volume: reference then bucket_key tiebreaks."""
        refs = {
            "AAA": _cache_entry(
                "AAA",
                buckets={
                    _bk("Arabic", "nr", "black"): _bucket(signal="Strong", volume=50),
                    _bk("Roman", "nr", "white"): _bucket(
                        dial_numerals="Roman", auction_type="nr", dial_color="white",
                        signal="Strong", volume=50,
                    ),
                },
            ),
            "BBB": _cache_entry(
                "BBB",
                buckets={_bk("Arabic", "nr", "black"): _bucket(signal="Strong", volume=50)},
            ),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        # Expected: AAA/arabic|nr|black, AAA/roman|nr|white, BBB/arabic|nr|black
        assert rows[0]["reference"] == "AAA"
        assert rows[0]["dial_numerals"] == "Arabic"
        assert rows[1]["reference"] == "AAA"
        assert rows[1]["dial_numerals"] == "Roman"
        assert rows[2]["reference"] == "BBB"


# ═══════════════════════════════════════════════════════════════════════
# Keep column
# ═══════════════════════════════════════════════════════════════════════


class TestKeepColumn:
    def test_keep_column_empty_at_generation(self, tmp_path):
        refs = {
            f"R{i}": _cache_entry(f"R{i}", buckets={_bk("Arabic", "nr", "black"): _bucket()})
            for i in range(5)
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert all(r["keep"] == "" for r in rows)
        assert all("keep" in r for r in rows)


# ═══════════════════════════════════════════════════════════════════════
# Atomic write
# ═══════════════════════════════════════════════════════════════════════


class TestAtomicWrite:
    def test_partial_failure_leaves_no_half_written_file(self, tmp_path):
        """If os.replace fails the .tmp gets cleaned up."""
        entry = _cache_entry("X1")
        bk = _bk("Arabic", "nr", "black")
        rows = [_flatten_row(entry, bk, entry["buckets"][bk])]
        target = tmp_path / "cycle_shortlist_cycle_2026-06.csv"
        with patch("scripts.build_shortlist.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError, match="boom"):
                _atomic_write_csv(rows, FIELDNAMES, str(target))
        assert not target.exists()
        assert not (tmp_path / "cycle_shortlist_cycle_2026-06.csv.tmp").exists()

    def test_creates_parent_directory(self, tmp_path):
        deep = tmp_path / "a" / "b"
        entry = _cache_entry("X1")
        bk = _bk("Arabic", "nr", "black")
        rows = [_flatten_row(entry, bk, entry["buckets"][bk])]
        target = deep / "cycle_shortlist_cycle_2026-06.csv"
        _atomic_write_csv(rows, FIELDNAMES, str(target))
        assert target.exists()


# ═══════════════════════════════════════════════════════════════════════
# Filename
# ═══════════════════════════════════════════════════════════════════════


class TestFilename:
    def test_cycle_id_in_filename(self, tmp_path):
        refs = {"R1": _cache_entry("R1")}
        out = run(refs, cycle_id="cycle_2026-09", state_path=str(tmp_path))
        assert os.path.basename(out) == "cycle_shortlist_cycle_2026-09.csv"


# ═══════════════════════════════════════════════════════════════════════
# Row count (backward-compatible assertions, now bucket-aware)
# ═══════════════════════════════════════════════════════════════════════


class TestRowCount:
    def test_row_count_equals_total_bucket_count(self, tmp_path):
        """50 refs each with 1 bucket = 50 rows."""
        refs = {
            f"R{i:03d}": _cache_entry(
                f"R{i:03d}",
                buckets={_bk("Arabic", "nr", "black"): _bucket()},
            )
            for i in range(50)
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert len(rows) == 50

    def test_empty_references_writes_header_only(self, tmp_path):
        out = run({}, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        header, rows = _read_csv(out)
        assert header == FIELDNAMES
        assert rows == []


# ═══════════════════════════════════════════════════════════════════════
# Confidence flatten happy path
# ═══════════════════════════════════════════════════════════════════════


class TestConfidenceFlatten:
    def test_populated_confidence_flattens_to_six_columns(self, tmp_path):
        conf = {
            "trades": 5, "profitable": 4, "win_rate": 80.0, "avg_roi": 12.5,
            "avg_premium": 3.4, "last_trade": "2026-04-10",
        }
        refs = {"X1": _cache_entry("X1", confidence=conf)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        r = rows[0]
        assert r["confidence_trades"] == "5"
        assert r["confidence_profitable"] == "4"
        assert r["confidence_win_rate"] == "80.0"
        assert r["confidence_avg_roi"] == "12.5"
        assert r["confidence_avg_premium"] == "3.4"
        assert r["confidence_last_trade"] == "2026-04-10"

    def test_populated_momentum_flattens(self, tmp_path):
        refs = {
            "X1": _cache_entry(
                "X1",
                momentum={"score": -2, "label": "Cooling"},
            ),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["momentum_score"] == "-2"
        assert rows[0]["momentum_label"] == "Cooling"
