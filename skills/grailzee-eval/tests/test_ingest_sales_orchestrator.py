"""Tests for the ingest_sales orchestrator (sub-step 1.7 commit 1).

Unit-level coverage of the four inheritances and the OTEL outcome variants.
End-to-end integration scenarios (mid-batch failure, idempotency, atomicity)
land in test_ingest_sales_integration.py; these tests exercise the full
primitive composition with fixture content moving through the orchestrator.

Inheritances tested here:
1. sell_cycle_id blank validation: orchestrator raises SchemaShiftDetected
   when transform produces a row with blank sell_cycle_id (defensive guard
   against future contract drift in transform_jsonl; ADR-0004 D2).
2. Ledger CSV read path: covered separately in test_ingest_sales_read.py;
   this file checks round-trip via the orchestrator's own read+write cycle.
3. MergeCounts -> IngestManifest wiring: each field independently verified.
4. rows_unmatched accumulated at transform time across a multi-file batch.

OTEL outcomes tested: "complete", "no_files", "halted_schema_shift",
"halted_erp_invalid" (from merge_rows), "halted_ledger_write",
"halted_lock_timeout".

All test fixtures are real-derived JSONL (post-1.2 rebuild, ADR-0005).
Inline payloads use JSONL strings (one JSON object per line, no wrapper).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    ERPBatchInvalid,
    IngestManifest,
    LedgerRow,
    LedgerWriteFailed,
    LockAcquisitionFailed,
    SchemaShiftDetected,
    atomic_write_csv,
    ingest_sales,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ingest_sales"


# ─── Setup helpers ───────────────────────────────────────────────────


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Standard tmp_path scaffolding for orchestrator tests.

    Returns (sales_data_dir, archive_dir, ledger_path, lock_path).
    The lock path is local-only (in tmp_path) so tests do not contend
    on the production ~/.grailzee/trade_ledger.lock.
    """
    sales = tmp_path / "sales_data"
    sales.mkdir()
    archive = sales / "archive"
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "trade_ledger.csv"
    lock = tmp_path / "trade_ledger.lock"
    return sales, archive, ledger, lock


def _drop_fixture(sales: Path, fixture_name: str, dest_name: str | None = None) -> Path:
    """Copy a named fixture from FIXTURES into sales_data/."""
    src = FIXTURES / fixture_name
    target = sales / (dest_name or fixture_name)
    target.write_text(src.read_text())
    return target


def _drop_inline(sales: Path, name: str, jsonl_content: str) -> Path:
    """Write a JSONL string directly to sales_data/."""
    target = sales / name
    target.write_text(jsonl_content)
    return target


def _grailzee_jsonl(stock_id: str, *, matched: bool = True, account: str = "NR") -> str:
    """Return a JSONL string with one Grailzee Sale and optional Purchase.

    Format: one JSON object per line (ADR-0005). Intended for orchestrator
    tests that exercise lock / merge / archive behavior; data shape matches
    the real JSONL contract but stock IDs are synthetic test identifiers.
    """
    fee = 49 if account == "NR" else 99
    sale = {
        "type": "Sale",
        "transaction_id": f"TEST-{stock_id}",
        "status": "Fulfilled",
        "created_at": "2026-04-25T10:00:00Z",
        "platform": ["Grailzee"],
        "services": [{"name": "Platform fee", "actual_cost": fee}],
        "line_items": [{
            "stock_id": stock_id,
            "brand": "Tudor",
            "reference_number": "79830RB",
            "cost_of_item": 2750.0,
            "unit_price": 3200.0,
            "delivered_date": None,
        }],
    }
    lines = [json.dumps(sale)]
    if matched:
        purchase = {
            "type": "Purchase",
            "transaction_id": f"TESTPA-{stock_id}",
            "status": "Received",
            "created_at": "2026-04-10T10:00:00Z",
            "payments": [{"payment_date": "2026-04-11T10:00:00Z"}],
            "line_items": [{"stock_id": stock_id, "delivered_date": "2026-04-12T10:00:00Z"}],
        }
        lines.append(json.dumps(purchase))
    return "\n".join(lines)


def _two_grailzee_jsonl(stock_a: str, stock_b: str, *, b_unmatched: bool = False) -> str:
    """Two-Sale JSONL (one NR, one RES) with optional Purchases."""
    records = [
        {
            "type": "Sale",
            "transaction_id": f"TEST-{stock_a}",
            "status": "Fulfilled",
            "created_at": "2026-04-25T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": stock_a, "brand": "Tudor",
                            "reference_number": "79830RB",
                            "cost_of_item": 2750.0, "unit_price": 3200.0,
                            "delivered_date": None}],
        },
        {
            "type": "Sale",
            "transaction_id": f"TEST-{stock_b}",
            "status": "Fulfilled",
            "created_at": "2026-04-26T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 99}],
            "line_items": [{"stock_id": stock_b, "brand": "Rolex",
                            "reference_number": "126300",
                            "cost_of_item": 8200.0, "unit_price": 9400.0,
                            "delivered_date": None}],
        },
        {
            "type": "Purchase",
            "transaction_id": f"TESTPA-{stock_a}",
            "status": "Received",
            "created_at": "2026-04-10T10:00:00Z",
            "payments": [],
            "line_items": [{"stock_id": stock_a, "delivered_date": None}],
        },
    ]
    if not b_unmatched:
        records.append({
            "type": "Purchase",
            "transaction_id": f"TESTPA-{stock_b}",
            "status": "Received",
            "created_at": "2026-04-11T10:00:00Z",
            "payments": [],
            "line_items": [{"stock_id": stock_b, "delivered_date": None}],
        })
    return "\n".join(json.dumps(r) for r in records)


def _call(sales, archive, ledger, lock, *, today: date = date(2026, 4, 29)) -> IngestManifest:
    return ingest_sales(
        sales_data_dir=sales,
        archive_dir=archive,
        ledger_path=ledger,
        lock_path=lock,
        today=today,
    )


# ─── No files (idempotency baseline) ─────────────────────────────────


class TestNoFiles:
    def test_empty_sales_dir_returns_zero_manifest(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 0
        assert manifest.files_processed == 0
        assert manifest.rows_added == 0
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 0
        assert manifest.rows_unmatched == 0
        assert manifest.rows_pruned == 0
        assert manifest.rows_skipped == []
        assert manifest.error is None

    def test_archive_only_counts_as_zero_files(self, tmp_path):
        """sales_data/archive/ contents are not counted as found files."""
        sales, archive, ledger, lock = _setup(tmp_path)
        archive.mkdir()
        (archive / "watchtrack_2026-04-25.jsonl").write_text(
            json.dumps({"type": "Sale", "transaction_id": "X"})
        )
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 0

    def test_no_files_does_not_create_ledger(self, tmp_path):
        """No-op invocation must not write trade_ledger.csv."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _call(sales, archive, ledger, lock)
        assert not ledger.exists()


# ─── Clean single-file run ───────────────────────────────────────────


class TestCleanRun:
    def test_clean_run_returns_complete_manifest(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 1
        assert manifest.files_processed == 1
        assert manifest.last_processed == "watchtrack_2026-04-29.jsonl"
        assert manifest.rows_added == 1
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 0
        assert manifest.error is None

    def test_clean_run_writes_ledger(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        assert ledger.exists()

    def test_clean_run_archives_source_file(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        src = _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        assert not src.exists()
        assert (archive / "watchtrack_2026-04-29.jsonl").exists()


# ─── Inheritance 1: sell_cycle_id blank validation ───────────────────


class TestSellCycleIdBlankValidation:
    def test_blank_sell_cycle_id_raises_schema_shift(self, tmp_path, monkeypatch):
        """Inheritance 1: orchestrator raises SchemaShiftDetected when
        transform_jsonl emits a row with blank sell_cycle_id. Defensive
        guard against future contract drift in transform_jsonl. ADR-0004 D2.

        Mocks transform_jsonl to inject the invariant-violating row.
        transform_jsonl now returns tuple (rows, skipped); monkeypatch returns
        the correct tuple shape.
        """
        sales, archive, ledger, lock = _setup(tmp_path)
        (sales / "watchtrack_2026-04-29.jsonl").write_text(
            json.dumps({"type": "Purchase", "transaction_id": "P1",
                        "payments": [], "line_items": []})
        )

        bad_row = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="",  # BLANK -- the invariant violation under test
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,
        )
        monkeypatch.setattr(
            "scripts.ingest_sales.transform_jsonl",
            lambda path: ([bad_row], []),
        )
        with pytest.raises(SchemaShiftDetected, match="sell_cycle_id"):
            _call(sales, archive, ledger, lock)

    def test_blank_sell_cycle_id_does_not_archive(self, tmp_path, monkeypatch):
        """If transform produces an invalid row, the source file must
        remain in sales_data/ (no archive move on hard-fail)."""
        sales, archive, ledger, lock = _setup(tmp_path)
        src = sales / "watchtrack_2026-04-29.jsonl"
        src.write_text(json.dumps({"type": "Purchase", "transaction_id": "P1",
                                    "payments": [], "line_items": []}))

        bad_row = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,
        )
        monkeypatch.setattr(
            "scripts.ingest_sales.transform_jsonl",
            lambda path: ([bad_row], []),
        )
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        assert src.exists()
        assert not (archive / "watchtrack_2026-04-29.jsonl").exists()

    def test_blank_sell_cycle_id_does_not_write_ledger(self, tmp_path, monkeypatch):
        """If transform produces an invalid row, the ledger must not be
        written. Pre-merge raise is before the lock acquire / write."""
        sales, archive, ledger, lock = _setup(tmp_path)
        (sales / "watchtrack_2026-04-29.jsonl").write_text(
            json.dumps({"type": "Purchase", "transaction_id": "P1",
                        "payments": [], "line_items": []})
        )

        bad_row = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,
        )
        monkeypatch.setattr(
            "scripts.ingest_sales.transform_jsonl",
            lambda path: ([bad_row], []),
        )
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        assert not ledger.exists()


# ─── Inheritance 3: MergeCounts -> IngestManifest wiring ─────────────


class TestMergeCountsWiring:
    """Each of rows_added, rows_updated, rows_unchanged is verified
    individually so a copy-paste error wiring is caught at unit-test
    resolution. ADR-0001 §"Position 4" preserves order."""

    def _seed_ledger(self, ledger: Path) -> LedgerRow:
        existing = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,
        )
        atomic_write_csv(ledger, [existing])
        return existing

    def test_added_field_wired(self, tmp_path):
        """Two brand-new stock_ids -> manifest.rows_added == 2."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl",
                     _two_grailzee_jsonl("TEY1048", "TEY1080"))
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 2
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 0

    def test_updated_field_wired(self, tmp_path):
        """Same stock_id but changed price -> rows_updated == 1."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        # New payload for same stock_id (TEY1104) but different sell_price.
        payload = json.dumps({
            "type": "Sale",
            "transaction_id": "TEST-TEY1104",
            "status": "Fulfilled",
            "created_at": "2026-04-25T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "TEY1104", "brand": "Tudor",
                            "reference_number": "79830RB",
                            "cost_of_item": 2750.0,
                            "unit_price": 3300.0,  # was 3200 → update
                            "delivered_date": None}],
        })
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 0
        assert manifest.rows_updated == 1
        assert manifest.rows_unchanged == 0

    def test_unchanged_field_wired(self, tmp_path):
        """Same stock_id and same fields -> rows_unchanged == 1."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        payload = json.dumps({
            "type": "Sale",
            "transaction_id": "TEST-TEY1104",
            "status": "Fulfilled",
            "created_at": "2026-04-25T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "TEY1104", "brand": "Tudor",
                            "reference_number": "79830RB",
                            "cost_of_item": 2750.0,
                            "unit_price": 3200.0,  # same as seeded → unchanged
                            "delivered_date": None}],
        })
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 0
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 1

    def test_all_three_fields_distinct_and_correct(self, tmp_path):
        """existing=[A,B]; file=[A unchanged, B' updated, C new].
        Expects rows_added=1 (C), rows_updated=1 (B'), rows_unchanged=1 (A)."""
        sales, archive, ledger, lock = _setup(tmp_path)
        a = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,
        )
        b = LedgerRow(
            stock_id="TEY1048",
            sell_date=date(2026, 4, 26),
            sell_cycle_id="cycle_2026-08",
            brand="Rolex",
            reference="126300",
            account="RES",
            buy_price=8200.0,
            sell_price=9400.0,
        )
        atomic_write_csv(ledger, [a, b])

        records = [
            # A unchanged
            {"type": "Sale", "transaction_id": "TEST-TEY1104", "status": "Fulfilled",
             "created_at": "2026-04-25T10:00:00Z", "platform": ["Grailzee"],
             "services": [{"name": "Platform fee", "actual_cost": 49}],
             "line_items": [{"stock_id": "TEY1104", "brand": "Tudor",
                             "reference_number": "79830RB",
                             "cost_of_item": 2750.0, "unit_price": 3200.0,
                             "delivered_date": None}]},
            # B' updated price
            {"type": "Sale", "transaction_id": "TEST-TEY1048", "status": "Fulfilled",
             "created_at": "2026-04-26T10:00:00Z", "platform": ["Grailzee"],
             "services": [{"name": "Platform fee", "actual_cost": 99}],
             "line_items": [{"stock_id": "TEY1048", "brand": "Rolex",
                             "reference_number": "126300",
                             "cost_of_item": 8200.0, "unit_price": 9500.0,
                             "delivered_date": None}]},
            # C new
            {"type": "Sale", "transaction_id": "TEST-TEY1080", "status": "Fulfilled",
             "created_at": "2026-04-27T10:00:00Z", "platform": ["Grailzee"],
             "services": [{"name": "Platform fee", "actual_cost": 49}],
             "line_items": [{"stock_id": "TEY1080", "brand": "Omega",
                             "reference_number": "311.30",
                             "cost_of_item": 4500.0, "unit_price": 5200.0,
                             "delivered_date": None}]},
        ]
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl",
                     "\n".join(json.dumps(r) for r in records))
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 1
        assert manifest.rows_updated == 1
        assert manifest.rows_unchanged == 1


# ─── Inheritance 4: rows_unmatched at transform time, accumulated ────


class TestRowsUnmatched:
    def test_single_file_unmatched_count(self, tmp_path):
        """One unmatched row in one file -> manifest.rows_unmatched == 1.

        Uses fixture_nr_unmatched.jsonl (TEY1048, no matching Purchase).
        """
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_nr_unmatched.jsonl", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_unmatched == 1

    def test_unmatched_counted_even_for_added_rows(self, tmp_path):
        """An unmatched row still merges into the ledger as an add.
        rows_unmatched and rows_added are not mutually exclusive."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_nr_unmatched.jsonl", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 1
        assert manifest.rows_unmatched == 1

    def test_multi_file_accumulation(self, tmp_path):
        """Two files, each with one unmatched row -> rows_unmatched == 2."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_nr_unmatched.jsonl", "watchtrack_2026-04-25.jsonl")
        # Second file: a different unmatched Grailzee Sale (no Purchase record)
        payload = json.dumps({
            "type": "Sale",
            "transaction_id": "TEST-UNMATCHED2",
            "status": "Fulfilled",
            "created_at": "2026-04-26T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "TEY9999", "brand": "Tudor",
                            "reference_number": "79830RB",
                            "cost_of_item": 2750.0, "unit_price": 3200.0,
                            "delivered_date": None}],
        })
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_unmatched == 2
        assert manifest.files_found == 2
        assert manifest.files_processed == 2

    def test_matched_row_does_not_increment_unmatched(self, tmp_path):
        """A matched row (TEY1083 + TEYPA1061) has buy_date set; not counted."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_unmatched == 0
        assert manifest.rows_added == 1


# ─── OTEL outcomes ────────────────────────────────────────────────────


def _orchestrator_span(span_exporter):
    """Return the ingest_sales orchestrator span."""
    return next(
        (s for s in span_exporter.get_finished_spans()
         if s.name == "ingest_sales.ingest_sales"),
        None,
    )


class TestOTELOutcomes:
    def test_outcome_complete_on_clean_run(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None, "ingest_sales.ingest_sales span not found"
        assert sp.attributes["outcome"] == "complete"

    def test_outcome_no_files_when_dir_empty(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "no_files"

    def test_outcome_halted_schema_shift_on_unknown_type(self, tmp_path, span_exporter):
        """fixture_schema_shift.jsonl contains {"type":"Refund"} → SchemaShiftDetected."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_schema_shift.jsonl", "watchtrack_2026-04-29.jsonl")
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_schema_shift"

    def test_outcome_halted_erp_invalid_from_merge_rows(
        self, tmp_path, span_exporter, monkeypatch
    ):
        """ERPBatchInvalid from merge_rows (duplicate stock_id) → halted_erp_invalid."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")

        def _raise(existing, new):
            raise ERPBatchInvalid("simulated duplicate stock_id")

        monkeypatch.setattr("scripts.ingest_sales.merge_rows", _raise)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_erp_invalid"

    def test_span_attributes_on_complete_run(self, tmp_path, span_exporter):
        """All counter attributes plus outcome are present on the complete span."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        for attr in (
            "files_found",
            "rows_added",
            "rows_updated",
            "rows_unchanged",
            "rows_unmatched",
            "rows_pruned",
            "rows_skipped_count",
        ):
            assert attr in sp.attributes, f"missing attribute {attr}"
        assert sp.attributes["files_found"] == 1
        assert sp.attributes["rows_added"] == 1
        assert sp.attributes["rows_skipped_count"] == 0


# ─── Files_found counts only top-level *.jsonl ───────────────────────


class TestFilesFoundScope:
    def test_only_jsonl_extension_counted(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        (sales / "README.md").write_text("not a batch")
        (sales / "logs.txt").write_text("noise")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 1


# ─── In-lock OTEL outcome attribution (sub-step 1.7 commit 2) ────────


@contextmanager
def _raising_lock_cm(*args, **kwargs):
    """Context manager that raises LockAcquisitionFailed on enter."""
    raise LockAcquisitionFailed("simulated lock timeout")
    yield  # never reached


class TestOTELInLockOutcomes:
    """Every IngestError subclass that can raise inside the lock gets its
    outcome attribution per _OUTCOME_BY_CLASS, by class not by location."""

    def _seed_clean_run_inputs(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")
        return sales, archive, ledger, lock

    def test_schema_shift_in_read_ledger_csv(
        self, tmp_path, span_exporter, monkeypatch
    ):
        sales, archive, ledger, lock = self._seed_clean_run_inputs(tmp_path)

        def _raise(path):
            raise SchemaShiftDetected("simulated corrupt ledger")

        monkeypatch.setattr("scripts.ingest_sales.read_ledger_csv", _raise)
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_schema_shift"

    def test_erp_batch_invalid_in_merge_rows(
        self, tmp_path, span_exporter, monkeypatch
    ):
        sales, archive, ledger, lock = self._seed_clean_run_inputs(tmp_path)

        def _raise(existing, new):
            raise ERPBatchInvalid("simulated duplicate stock_id in batch")

        monkeypatch.setattr("scripts.ingest_sales.merge_rows", _raise)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_erp_invalid"

    def test_ledger_write_failed_in_atomic_write_csv(
        self, tmp_path, span_exporter, monkeypatch
    ):
        sales, archive, ledger, lock = self._seed_clean_run_inputs(tmp_path)

        def _raise(path, rows, header=None):
            raise LedgerWriteFailed("simulated rename failure")

        monkeypatch.setattr("scripts.ingest_sales.atomic_write_csv", _raise)
        with pytest.raises(LedgerWriteFailed):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_ledger_write"

    def test_lock_acquisition_failed_in_with_exclusive_lock(
        self, tmp_path, span_exporter, monkeypatch
    ):
        sales, archive, ledger, lock = self._seed_clean_run_inputs(tmp_path)
        monkeypatch.setattr(
            "scripts.ingest_sales.with_exclusive_lock", _raising_lock_cm
        )
        with pytest.raises(LockAcquisitionFailed):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_lock_timeout"


class TestBareExceptionInLock:
    """Bare Exception in the lock does NOT get outcome attribution."""

    def test_runtime_error_no_outcome(self, tmp_path, span_exporter, monkeypatch):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "fixture_res_matched.jsonl", "watchtrack_2026-04-29.jsonl")

        def _raise(path, rows, header=None):
            raise RuntimeError("simulated unrelated bug")

        monkeypatch.setattr("scripts.ingest_sales.atomic_write_csv", _raise)
        with pytest.raises(RuntimeError):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert "outcome" not in sp.attributes
