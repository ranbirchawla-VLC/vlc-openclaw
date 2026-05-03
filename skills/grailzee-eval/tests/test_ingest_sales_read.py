"""Tests for read_ledger_csv (sub-step 1.7 commit 1).

The read path is the inverse of `_row_to_csv_dict` / `atomic_write_csv`:
- nullable date fields and `buy_cycle_id` parse "" -> None
- non-optional fields ("stock_id", "sell_cycle_id", "brand", "reference",
  "account", "buy_price", "sell_price") raise SchemaShiftDetected when
  encountered as ""
- the file being absent is the first-run case and returns []

Round-trip identity: parse(serialize(row)) == row for every nullable-field
state combination on a LedgerRow. Float price fields use the f"{v:.2f}"
serialization contract from sub-step 1.3 to stay equality-stable across
the round trip (ADR-0001 Position 1).
"""
from __future__ import annotations

from datetime import date
from itertools import product
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    LedgerRow,
    SchemaShiftDetected,
    atomic_write_csv,
    read_ledger_csv,
)


_BASE = dict(
    stock_id="TEY1104",
    sell_date=date(2026, 4, 25),
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.00,
    sell_price=3200.00,
)


def _row(**overrides) -> LedgerRow:
    fields = {**_BASE, **overrides}
    return LedgerRow(**fields)


# ─── Missing file ────────────────────────────────────────────────────


class TestMissingFile:
    def test_returns_empty_list_when_file_absent(self, tmp_path):
        """First-run case: trade_ledger.csv does not exist yet."""
        path = tmp_path / "does_not_exist.csv"
        assert read_ledger_csv(path) == []

    def test_does_not_create_the_file(self, tmp_path):
        """Read path is read-only; missing file must not be created."""
        path = tmp_path / "does_not_exist.csv"
        read_ledger_csv(path)
        assert not path.exists()


# ─── Empty CSV (header only) ─────────────────────────────────────────


class TestHeaderOnly:
    def test_returns_empty_list(self, tmp_path):
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [])
        assert read_ledger_csv(path) == []


# ─── Basic round-trip ────────────────────────────────────────────────


class TestRoundTripBasic:
    def test_single_row_identity(self, tmp_path):
        path = tmp_path / "trade_ledger.csv"
        row = _row()
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed == [row]

    def test_multiple_rows_preserve_order(self, tmp_path):
        path = tmp_path / "trade_ledger.csv"
        rows = [
            _row(stock_id="TEY1104"),
            _row(stock_id="TEY1048", account="RES"),
            _row(stock_id="TEY1080"),
        ]
        atomic_write_csv(path, rows)
        parsed = read_ledger_csv(path)
        assert parsed == rows

    def test_returns_list(self, tmp_path):
        """Type contract: read_ledger_csv returns list[LedgerRow], not iterator."""
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [_row()])
        result = read_ledger_csv(path)
        assert isinstance(result, list)
        assert isinstance(result[0], LedgerRow)


# ─── Round-trip identity over nullable-field state combinations ──────


_NULLABLE_FIELDS = [
    "buy_date",
    "buy_cycle_id",
    "buy_received_date",
    "sell_delivered_date",
    "buy_paid_date",
]

# Sample non-None values to use when a nullable field is "populated" in
# the matrix. Picked once to keep the matrix size manageable; the
# round-trip identity guarantee is independent of the value picked.
_POPULATED = {
    "buy_date": date(2026, 4, 10),
    "buy_cycle_id": "cycle_2026-07",
    "buy_received_date": date(2026, 4, 12),
    "sell_delivered_date": date(2026, 4, 27),
    "buy_paid_date": date(2026, 4, 11),
}


class TestNullableFieldRoundTrip:
    @pytest.mark.parametrize(
        "states",
        list(product([True, False], repeat=len(_NULLABLE_FIELDS))),
        ids=lambda s: "".join("1" if x else "0" for x in s),
    )
    def test_every_nullable_combination_round_trips(self, tmp_path, states):
        """For each of the 32 nullable-field None/value combinations on a
        LedgerRow, atomic_write_csv -> read_ledger_csv must return an
        identical row."""
        overrides = {
            f: (_POPULATED[f] if populated else None)
            for f, populated in zip(_NULLABLE_FIELDS, states)
        }
        row = _row(**overrides)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        assert read_ledger_csv(path) == [row]


class TestSellDateNullable:
    """ADR-0004 D1: sell_date is `date | None`. Round-trip an explicit None."""

    def test_sell_date_none_round_trips(self, tmp_path):
        row = _row(sell_date=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed == [row]
        assert parsed[0].sell_date is None


# ─── Empty string in non-optional fields raises ──────────────────────


# Non-optional fields per ADR-0004 D2/D3. Each must trigger raise on empty.
_NON_OPTIONAL_STR = ["stock_id", "sell_cycle_id", "brand", "reference", "account"]
_NON_OPTIONAL_NUM = ["buy_price", "sell_price"]


def _csv_with_blank(tmp_path: Path, blank_field: str) -> Path:
    """Write a CSV where one named non-optional column is the empty string."""
    from scripts.ingest_sales import LEDGER_CSV_COLUMNS

    base_values = {
        "stock_id": "TEY1104",
        "sell_date": "2026-04-25",
        "sell_cycle_id": "cycle_2026-08",
        "brand": "Tudor",
        "reference": "79830RB",
        "account": "NR",
        "buy_price": "2750.00",
        "sell_price": "3200.00",
        "buy_date": "",
        "buy_cycle_id": "",
        "buy_received_date": "",
        "sell_delivered_date": "",
        "buy_paid_date": "",
    }
    base_values[blank_field] = ""
    path = tmp_path / "trade_ledger.csv"
    header = ",".join(LEDGER_CSV_COLUMNS)
    row_values = ",".join(base_values[k] for k in LEDGER_CSV_COLUMNS)
    path.write_text(f"{header}\n{row_values}\n")
    return path


class TestEmptyNonOptionalFieldRaises:
    @pytest.mark.parametrize("field", _NON_OPTIONAL_STR + _NON_OPTIONAL_NUM)
    def test_blank_in_non_optional_field_raises(self, tmp_path, field):
        path = _csv_with_blank(tmp_path, field)
        with pytest.raises(SchemaShiftDetected, match=field):
            read_ledger_csv(path)


# ─── Empty string in nullable fields parses to None (not raise) ──────


class TestNullableEmptyStringIsNone:
    def test_buy_date_blank_is_none(self, tmp_path):
        row = _row(buy_date=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed[0].buy_date is None

    def test_buy_cycle_id_blank_is_none(self, tmp_path):
        row = _row(buy_cycle_id=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed[0].buy_cycle_id is None

    def test_buy_received_date_blank_is_none(self, tmp_path):
        row = _row(buy_received_date=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed[0].buy_received_date is None

    def test_sell_delivered_date_blank_is_none(self, tmp_path):
        row = _row(sell_delivered_date=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed[0].sell_delivered_date is None

    def test_buy_paid_date_blank_is_none(self, tmp_path):
        row = _row(buy_paid_date=None)
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [row])
        parsed = read_ledger_csv(path)
        assert parsed[0].buy_paid_date is None


# ─── Account legacy values pass through ──────────────────────────────


class TestAccountLegacyValues:
    """Per ADR-0004 D3: account is non-optional but its value-domain is
    not constrained at the read path. A legacy row carrying "UNKNOWN"
    parses without error."""

    def test_unknown_account_parses(self, tmp_path):
        # Build a row inline to test a value the dataclass would accept
        # but that the writer never produces; round through the CSV layer.
        legacy = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2025, 1, 10),
            sell_cycle_id="cycle_2025-01",
            brand="Rolex",
            reference="126300",
            account="UNKNOWN",
            buy_price=7800.00,
            sell_price=8900.00,
        )
        path = tmp_path / "trade_ledger.csv"
        atomic_write_csv(path, [legacy])
        rows = read_ledger_csv(path)
        assert rows[0].account == "UNKNOWN"
        assert rows[0] == legacy
