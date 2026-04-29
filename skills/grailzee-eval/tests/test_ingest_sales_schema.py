"""Tests for ingest_sales schema, dataclasses, error hierarchy, path resolution.

Sub-step 1.1. Pure stdlib dependencies only. No I/O, no plugin, no Telegram.
"""
from __future__ import annotations

import dataclasses
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    ERPBatchInvalid,
    IngestError,
    IngestManifest,
    LEDGER_CSV_COLUMNS,
    LEDGER_LOCK_DEFAULT,
    LedgerRow,
    LedgerWriteFailed,
    LockAcquisitionFailed,
    SchemaShiftDetected,
    _resolve_archive_dir,
    _resolve_ledger_path,
    _resolve_lock_path,
    _resolve_sales_data_dir,
    _row_to_csv_dict,
)

_REQUIRED = dict(
    stock_id="TEY1104",
    sell_date=date(2026, 4, 25),
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.0,
    sell_price=3200.0,
)


# ─── LedgerRow ────────────────────────────────────────────────────────


class TestLedgerRow:
    def test_required_fields_round_trip(self):
        row = LedgerRow(**_REQUIRED)
        assert row.stock_id == "TEY1104"
        assert row.sell_date == date(2026, 4, 25)
        assert row.sell_cycle_id == "cycle_2026-08"
        assert row.brand == "Tudor"
        assert row.reference == "79830RB"
        assert row.account == "NR"
        assert row.buy_price == 2750.0
        assert row.sell_price == 3200.0

    def test_optional_fields_default_none(self):
        row = LedgerRow(**_REQUIRED)
        assert row.buy_date is None
        assert row.buy_cycle_id is None
        assert row.buy_received_date is None
        assert row.sell_delivered_date is None
        assert row.buy_paid_date is None

    def test_optional_fields_accept_values(self):
        row = LedgerRow(
            **_REQUIRED,
            buy_date=date(2026, 4, 10),
            buy_cycle_id="cycle_2026-07",
            buy_received_date=date(2026, 4, 12),
            sell_delivered_date=date(2026, 4, 27),
            buy_paid_date=date(2026, 4, 11),
        )
        assert row.buy_date == date(2026, 4, 10)
        assert row.buy_cycle_id == "cycle_2026-07"
        assert row.buy_received_date == date(2026, 4, 12)
        assert row.sell_delivered_date == date(2026, 4, 27)
        assert row.buy_paid_date == date(2026, 4, 11)

    def test_frozen_rejects_mutation(self):
        row = LedgerRow(**_REQUIRED)
        with pytest.raises(FrozenInstanceError):
            row.brand = "Rolex"  # type: ignore[misc]

    def test_frozen_rejects_optional_mutation(self):
        row = LedgerRow(**_REQUIRED)
        with pytest.raises(FrozenInstanceError):
            row.buy_date = date(2026, 1, 1)  # type: ignore[misc]

    def test_exactly_thirteen_fields(self):
        assert len(dataclasses.fields(LedgerRow)) == 13

    def test_equality_by_value(self):
        a = LedgerRow(**_REQUIRED)
        b = LedgerRow(**_REQUIRED)
        assert a == b

    def test_inequality_on_differing_field(self):
        a = LedgerRow(**_REQUIRED)
        b = LedgerRow(**{**_REQUIRED, "sell_price": 3100.0})
        assert a != b


# ─── IngestManifest ───────────────────────────────────────────────────


class TestIngestManifest:
    def test_construction_required_fields_only(self):
        m = IngestManifest(files_found=0, files_processed=0)
        assert m.files_found == 0
        assert m.files_processed == 0
        assert m.files_skipped == []
        assert m.last_processed is None
        assert m.rows_added == 0
        assert m.rows_updated == 0
        assert m.rows_unchanged == 0
        assert m.rows_unmatched == 0
        assert m.rows_pruned == 0
        assert m.error is None

    def test_full_construction(self):
        m = IngestManifest(
            files_found=2,
            files_processed=2,
            files_skipped=[],
            last_processed="watchtrack_2026-04-28.jsonl",
            rows_added=12,
            rows_updated=1,
            rows_unchanged=1,
            rows_unmatched=1,
            rows_pruned=3,
            error=None,
        )
        assert m.files_found == 2
        assert m.rows_added == 12
        assert m.last_processed == "watchtrack_2026-04-28.jsonl"

    def test_files_skipped_is_list_and_independent(self):
        a = IngestManifest(files_found=0, files_processed=0)
        b = IngestManifest(files_found=0, files_processed=0)
        a.files_skipped.append("x.jsonl")
        assert b.files_skipped == []  # default_factory gives independent lists

    def test_error_field_none_on_success(self):
        m = IngestManifest(files_found=1, files_processed=1)
        assert m.error is None

    def test_error_field_accepts_ingest_error(self):
        err = ERPBatchInvalid("batch failed")
        m = IngestManifest(
            files_found=1,
            files_processed=0,
            files_skipped=["f.jsonl"],
            error=err,
        )
        assert isinstance(m.error, IngestError)
        assert isinstance(m.error, ERPBatchInvalid)

    def test_exactly_ten_fields(self):
        assert len(dataclasses.fields(IngestManifest)) == 10

    def test_mutable_counter_update(self):
        m = IngestManifest(files_found=3, files_processed=0)
        m.rows_added += 5
        m.files_processed += 1
        assert m.rows_added == 5
        assert m.files_processed == 1


# ─── IngestError hierarchy ────────────────────────────────────────────


class TestIngestErrorHierarchy:
    def test_ingest_error_is_exception(self):
        assert issubclass(IngestError, Exception)

    @pytest.mark.parametrize("cls", [
        ERPBatchInvalid,
        LedgerWriteFailed,
        LockAcquisitionFailed,
        SchemaShiftDetected,
    ])
    def test_each_subclass_inherits_ingest_error(self, cls):
        assert issubclass(cls, IngestError)

    @pytest.mark.parametrize("cls,msg", [
        (ERPBatchInvalid, "extraction halted"),
        (LedgerWriteFailed, "disk full"),
        (LockAcquisitionFailed, "30s timeout"),
        (SchemaShiftDetected, "missing stock_id on line_item"),
    ])
    def test_each_subclass_instantiable_with_message(self, cls, msg):
        err = cls(msg)
        assert str(err) == msg
        assert isinstance(err, IngestError)
        assert isinstance(err, Exception)

    def test_can_catch_subclass_as_ingest_error(self):
        with pytest.raises(IngestError):
            raise ERPBatchInvalid("batch invalid")

    def test_subclasses_are_distinct(self):
        assert ERPBatchInvalid is not LedgerWriteFailed
        assert LockAcquisitionFailed is not SchemaShiftDetected


# ─── Path resolution ─────────────────────────────────────────────────


class TestPathResolution:
    def test_ledger_path_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        with pytest.raises(EnvironmentError, match="GRAILZEE_ROOT"):
            _resolve_ledger_path()

    def test_sales_data_dir_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        with pytest.raises(EnvironmentError, match="GRAILZEE_ROOT"):
            _resolve_sales_data_dir()

    def test_archive_dir_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        with pytest.raises(EnvironmentError, match="GRAILZEE_ROOT"):
            _resolve_archive_dir()

    def test_lock_path_has_local_default_when_no_env(self, monkeypatch):
        """Lock path never raises on missing env: it has a local-filesystem default."""
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        monkeypatch.delenv("GRAILZEE_LOCK_PATH", raising=False)
        result = _resolve_lock_path()
        assert result == LEDGER_LOCK_DEFAULT
        assert isinstance(result, Path)

    def test_empty_string_env_raises(self, monkeypatch):
        monkeypatch.setenv("GRAILZEE_ROOT", "")
        with pytest.raises(EnvironmentError, match="GRAILZEE_ROOT"):
            _resolve_ledger_path()

    def test_whitespace_only_env_raises(self, monkeypatch):
        monkeypatch.setenv("GRAILZEE_ROOT", "   ")
        with pytest.raises(EnvironmentError, match="GRAILZEE_ROOT"):
            _resolve_ledger_path()

    def test_explicit_override_beats_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", "/some/env/path")
        override = tmp_path / "explicit_ledger.csv"
        assert _resolve_ledger_path(override) == override

    def test_explicit_override_beats_missing_env(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        override = tmp_path / "no_env_needed.csv"
        assert _resolve_ledger_path(override) == override

    def test_env_resolves_ledger_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", str(tmp_path))
        assert _resolve_ledger_path() == tmp_path / "state" / "trade_ledger.csv"

    def test_env_resolves_sales_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", str(tmp_path))
        assert _resolve_sales_data_dir() == tmp_path / "sales_data"

    def test_env_resolves_archive_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", str(tmp_path))
        assert _resolve_archive_dir() == tmp_path / "sales_data" / "archive"

    def test_lock_path_env_var_resolves(self, monkeypatch, tmp_path):
        """GRAILZEE_LOCK_PATH env var overrides the local default."""
        monkeypatch.setenv("GRAILZEE_LOCK_PATH", str(tmp_path / "my.lock"))
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        assert _resolve_lock_path() == tmp_path / "my.lock"

    def test_lock_path_default_not_on_fuse(self, monkeypatch):
        """Default lock path must not be on Google Drive or other FUSE mount."""
        monkeypatch.delenv("GRAILZEE_LOCK_PATH", raising=False)
        path_str = str(_resolve_lock_path())
        assert "Library/CloudStorage" not in path_str
        assert "GoogleDrive" not in path_str
        assert not path_str.startswith("/Volumes/")

    def test_sales_data_override_beats_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", "/ignored")
        override = tmp_path / "my_sales"
        assert _resolve_sales_data_dir(override) == override

    def test_archive_override_beats_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", "/ignored")
        override = tmp_path / "my_archive"
        assert _resolve_archive_dir(override) == override

    def test_lock_explicit_override_beats_all(self, monkeypatch, tmp_path):
        """Explicit arg wins over GRAILZEE_LOCK_PATH and over the local default."""
        monkeypatch.setenv("GRAILZEE_LOCK_PATH", str(tmp_path / "env.lock"))
        override = tmp_path / "explicit.lock"
        assert _resolve_lock_path(override) == override

    def test_all_resolvers_return_path_type(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GRAILZEE_ROOT", str(tmp_path))
        monkeypatch.delenv("GRAILZEE_LOCK_PATH", raising=False)
        assert isinstance(_resolve_ledger_path(), Path)
        assert isinstance(_resolve_sales_data_dir(), Path)
        assert isinstance(_resolve_archive_dir(), Path)
        assert isinstance(_resolve_lock_path(), Path)  # returns local default


# ─── sell_date nullability (ADR-0004) ─────────────────────────────────


_NULL_SELL = LedgerRow(
    stock_id="LEGACY-001",
    sell_date=None,
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.0,
    sell_price=3200.0,
)


class TestSellDateNullability:
    def test_sell_date_none_constructs(self) -> None:
        """sell_date=None is valid per the Phase 1 nullability contract (ADR-0004)."""
        assert _NULL_SELL.sell_date is None

    def test_sell_date_none_serializes_to_empty_string(self) -> None:
        """_row_to_csv_dict renders sell_date=None as '' (matches buy_date pattern)."""
        d = _row_to_csv_dict(_NULL_SELL)
        assert d["sell_date"] == ""

    def test_sell_date_none_round_trip_serialization_shape(self) -> None:
        """CSV dict produced from a None-sell_date row has all 13 expected keys.

        The round-trip-back assertion (reading '' sell_date from CSV back into a
        LedgerRow) is deferred to sub-step 1.7 when the read path is implemented.
        """
        d = _row_to_csv_dict(_NULL_SELL)
        assert set(d.keys()) == set(LEDGER_CSV_COLUMNS)
