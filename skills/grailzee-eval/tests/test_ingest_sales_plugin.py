"""Tests for the ingest_sales plugin dispatch layer (_run_from_dict, _run_from_argv).

Commit H. Mirrors the test structure from test_report_pipeline.py (Commit G).
Business logic is tested in the existing test_ingest_sales_*.py suite; this file
covers only the dispatch layer and exception-to-envelope mapping.
"""

from __future__ import annotations

import json
import sys

import pytest

import scripts.ingest_sales as ingest_sales_module
from scripts.ingest_sales import (
    ArchiveMoveFailed,
    ERPBatchInvalid,
    IngestError,
    IngestManifest,
    LedgerWriteFailed,
    LockAcquisitionFailed,
    SchemaShiftDetected,
    _run_from_argv,
    _run_from_dict,
)

_CANNED_MANIFEST = IngestManifest(
    files_found=1,
    files_processed=1,
    last_processed="watchtrack_2026-04-29.jsonl",
    rows_added=3,
    rows_updated=1,
    rows_unchanged=2,
    rows_unmatched=0,
    rows_pruned=0,
    rows_skipped=[],
)


def _stub_ingest(**_k):
    return _CANNED_MANIFEST


# ═══════════════════════════════════════════════════════════════════════
# H — _run_from_dict dispatch
# ═══════════════════════════════════════════════════════════════════════


class TestRunFromDict:
    def test_empty_input_success(self, tmp_path, monkeypatch, capsys):
        """Empty business-field JSON produces status=ok envelope with row counts; exit 0."""
        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _stub_ingest)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["status"] == "ok"
        assert out["rows_added"] == 3
        assert out["rows_updated"] == 1
        assert out["rows_unchanged"] == 2
        assert out["rows_pruned"] == 0
        assert "files_found" in out
        assert "files_processed" in out

    def test_extra_field_rejected(self, capsys):
        """Unknown business field → bad_input error envelope; exit 0."""
        rc = _run_from_dict({"unknown_field": "x"})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["status"] == "error"
        assert out["error_type"] == "bad_input"

    def test_erp_batch_invalid_maps_to_envelope(self, monkeypatch, capsys):
        def _raise(**_k):
            raise ERPBatchInvalid("duplicate stock_id in batch")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "erp_batch_invalid"
        assert "duplicate stock_id" in out["message"]

    def test_ledger_write_failed_maps_to_envelope(self, monkeypatch, capsys):
        def _raise(**_k):
            raise LedgerWriteFailed("disk full")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "ledger_write_failed"

    def test_lock_acquisition_failed_maps_to_envelope(self, monkeypatch, capsys):
        def _raise(**_k):
            raise LockAcquisitionFailed("timeout after 30s")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "lock_acquisition_failed"

    def test_schema_shift_detected_maps_to_envelope(self, monkeypatch, capsys):
        def _raise(**_k):
            raise SchemaShiftDetected("missing 'type' field")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "schema_shift_detected"

    def test_archive_move_failed_maps_to_envelope(self, monkeypatch, capsys):
        def _raise(**_k):
            raise ArchiveMoveFailed("EXDEV: cross-device rename")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "archive_move_failed"

    def test_generic_exception_maps_to_internal_error(self, monkeypatch, capsys):
        def _raise(**_k):
            raise RuntimeError("unexpected failure")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "internal_error"

    def test_test_hooks_not_rejected_as_extra_fields(self, tmp_path, monkeypatch, capsys):
        """All _TEST_HOOK_KEYS pass _Input validation without bad_input."""
        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _stub_ingest)

        rc = _run_from_dict({
            "sales_data_dir": str(tmp_path / "sales_data"),
            "ledger_path": str(tmp_path / "trade_ledger.csv"),
            "today": "2026-04-29",
        })
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["status"] == "ok"

    def test_base_ingest_error_maps_to_ingest_error_fallback(self, monkeypatch, capsys):
        """Bare IngestError (not a subclass) maps to 'ingest_error' fallback."""
        def _raise(**_k):
            raise IngestError("bare base class")

        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _raise)

        rc = _run_from_dict({})
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "ingest_error"


# ═══════════════════════════════════════════════════════════════════════
# H — _run_from_argv dispatch
# ═══════════════════════════════════════════════════════════════════════


class TestRunFromArgv:
    def test_valid_json_argv_dispatches(self, monkeypatch, capsys):
        """argv[1] as valid JSON object dispatches to _run_from_dict."""
        monkeypatch.setattr(ingest_sales_module, "ingest_sales", _stub_ingest)
        monkeypatch.setattr(sys, "argv", ["ingest_sales.py", json.dumps({})])

        rc = _run_from_argv()
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["status"] == "ok"

    def test_invalid_json_argv_returns_bad_input(self, monkeypatch, capsys):
        """Non-JSON argv[1] → bad_input envelope; exit 0."""
        monkeypatch.setattr(sys, "argv", ["ingest_sales.py", "not-json{{"])

        rc = _run_from_argv()
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "bad_input"

    def test_non_object_json_argv_returns_bad_input(self, monkeypatch, capsys):
        """JSON array instead of object → bad_input envelope; exit 0."""
        monkeypatch.setattr(sys, "argv", ["ingest_sales.py", json.dumps([1, 2, 3])])

        rc = _run_from_argv()
        out = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert out["error_type"] == "bad_input"
