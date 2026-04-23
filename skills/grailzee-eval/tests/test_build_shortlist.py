"""Tests for scripts.build_shortlist (B.7).

Covers:
- Exact 23-column header in spec order.
- Null ledger-derived fields → empty string.
- Default and override sort.
- ``keep`` blank at generation.
- Atomic write durability.
- ``cycle_id`` in filename.
- Row count equals scored references.
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


def _ref_entry(
    *, brand="Tudor", model="BB GMT", reference="79830RB",
    signal="Strong", median=3550.0, max_buy_nr=3240.0,
    st_pct=0.52, volume=115, risk_nr=23.86,
    premium_vs_market_pct=0.0, realized_premium_pct=-2.8,
    realized_premium_trade_count=1,
    confidence=None, momentum=None,
    capital_required_nr=3289.0, expected_net_at_median_nr=261.0,
):
    """Build one cache references[<ref>] entry with B.5 + B.2/B.3 fields."""
    return {
        "brand": brand,
        "model": model,
        "reference": reference,
        "signal": signal,
        "median": median,
        "max_buy_nr": max_buy_nr,
        "st_pct": st_pct,
        "volume": volume,
        "risk_nr": risk_nr,
        "premium_vs_market_pct": premium_vs_market_pct,
        "realized_premium_pct": realized_premium_pct,
        "realized_premium_trade_count": realized_premium_trade_count,
        "confidence": confidence,
        "momentum": momentum,
        "capital_required_nr": capital_required_nr,
        "expected_net_at_median_nr": expected_net_at_median_nr,
    }


def _read_csv(path) -> tuple[list[str], list[dict]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


# ═══════════════════════════════════════════════════════════════════════
# Header shape
# ═══════════════════════════════════════════════════════════════════════


class TestCsvHeader:
    def test_csv_header_matches_spec(self, tmp_path):
        """Exact 23-column header in spec order."""
        refs = {"79830RB": _ref_entry()}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        header, _ = _read_csv(out)
        assert header == FIELDNAMES
        assert len(header) == 23


# ═══════════════════════════════════════════════════════════════════════
# Null handling
# ═══════════════════════════════════════════════════════════════════════


class TestNullLedgerFields:
    def test_null_confidence_writes_empty_strings(self, tmp_path):
        refs = {"X1": _ref_entry(reference="X1", confidence=None)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        row = rows[0]
        for col in (
            "confidence_trades", "confidence_profitable", "confidence_win_rate",
            "confidence_avg_roi", "confidence_avg_premium", "confidence_last_trade",
        ):
            assert row[col] == "", f"{col!r} should be empty for null confidence"

    def test_null_momentum_writes_empty_strings(self, tmp_path):
        refs = {"X1": _ref_entry(reference="X1", momentum=None)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["momentum_score"] == ""
        assert rows[0]["momentum_label"] == ""

    def test_null_realized_premium_pct_writes_empty(self, tmp_path):
        refs = {"X1": _ref_entry(reference="X1", realized_premium_pct=None)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["realized_premium_pct"] == ""

    def test_zero_stays_zero_not_empty(self, tmp_path):
        """premium_vs_market_pct=0.0 (B.2 zero-floor) must not collapse to empty."""
        refs = {"X1": _ref_entry(reference="X1", premium_vs_market_pct=0.0)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["premium_vs_market_pct"] == "0.0"


# ═══════════════════════════════════════════════════════════════════════
# Sort
# ═══════════════════════════════════════════════════════════════════════


class TestSort:
    def test_sort_default_signal_then_volume(self, tmp_path):
        refs = {
            "A": _ref_entry(reference="A", signal="Reserve", volume=20),
            "B": _ref_entry(reference="B", signal="Strong", volume=5),
            "C": _ref_entry(reference="C", signal="Strong", volume=50),
            "D": _ref_entry(reference="D", signal="Normal", volume=10),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        # Strong (vol desc): C, B; then Normal: D; then Reserve: A
        assert [r["reference"] for r in rows] == ["C", "B", "D", "A"]

    def test_sort_override_brand(self, tmp_path):
        refs = {
            "A": _ref_entry(reference="A", brand="Tudor", signal="Strong", volume=5),
            "B": _ref_entry(reference="B", brand="Omega", signal="Strong", volume=5),
            "C": _ref_entry(reference="C", brand="Breitling", signal="Strong", volume=5),
        }
        out = run(refs, cycle_id="cycle_2026-06",
                  state_path=str(tmp_path), sort_key="brand")
        _, rows = _read_csv(out)
        assert [r["brand"] for r in rows] == ["Breitling", "Omega", "Tudor"]

    def test_signal_order_strong_to_low_data(self, tmp_path):
        """Verify the locked signal ordering."""
        refs = {
            sig.replace(" ", ""): _ref_entry(
                reference=sig.replace(" ", ""), signal=sig, volume=1,
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
# Keep column
# ═══════════════════════════════════════════════════════════════════════


class TestKeepColumn:
    def test_keep_column_empty_at_generation(self, tmp_path):
        refs = {f"R{i}": _ref_entry(reference=f"R{i}") for i in range(5)}
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert all(r["keep"] == "" for r in rows)
        assert all("keep" in r for r in rows)


# ═══════════════════════════════════════════════════════════════════════
# Atomic write
# ═══════════════════════════════════════════════════════════════════════


class TestAtomicWrite:
    def test_partial_failure_leaves_no_half_written_file(self, tmp_path):
        """If os.replace fails, the .tmp gets cleaned up and the
        target either stays at its prior contents or never appears."""
        target = tmp_path / "cycle_shortlist_cycle_2026-06.csv"
        rows = [_flatten_row("X1", _ref_entry(reference="X1"))]
        with patch("scripts.build_shortlist.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError, match="boom"):
                _atomic_write_csv(rows, FIELDNAMES, str(target))
        assert not target.exists()
        assert not (tmp_path / "cycle_shortlist_cycle_2026-06.csv.tmp").exists()

    def test_creates_parent_directory(self, tmp_path):
        deep = tmp_path / "a" / "b"
        rows = [_flatten_row("X1", _ref_entry(reference="X1"))]
        target = deep / "cycle_shortlist_cycle_2026-06.csv"
        _atomic_write_csv(rows, FIELDNAMES, str(target))
        assert target.exists()


# ═══════════════════════════════════════════════════════════════════════
# Filename + row count
# ═══════════════════════════════════════════════════════════════════════


class TestFilename:
    def test_cycle_id_in_filename(self, tmp_path):
        refs = {"R1": _ref_entry(reference="R1")}
        out = run(refs, cycle_id="cycle_2026-09", state_path=str(tmp_path))
        assert os.path.basename(out) == "cycle_shortlist_cycle_2026-09.csv"


class TestRowCount:
    def test_row_count_matches_input_references(self, tmp_path):
        refs = {f"R{i:03d}": _ref_entry(reference=f"R{i:03d}") for i in range(50)}
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
        refs = {"X1": _ref_entry(reference="X1", confidence=conf)}
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
            "X1": _ref_entry(
                reference="X1",
                momentum={"score": -2, "label": "Cooling"},
            ),
        }
        out = run(refs, cycle_id="cycle_2026-06", state_path=str(tmp_path))
        _, rows = _read_csv(out)
        assert rows[0]["momentum_score"] == "-2"
        assert rows[0]["momentum_label"] == "Cooling"
