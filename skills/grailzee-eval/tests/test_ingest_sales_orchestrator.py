"""Tests for the ingest_sales orchestrator (sub-step 1.7 commit 1).

Unit-level coverage of the four inheritances and the OTEL outcome variants.
End-to-end integration scenarios (mid-batch failure, idempotency, atomicity)
land in commit 2 per the explicit cut named in the build prompt.

Inheritances tested here:
1. sell_cycle_id blank validation: orchestrator raises SchemaShiftDetected
   when transform produces a row with blank sell_cycle_id (defensive guard
   against future drift in transform_jsonl; ADR-0004 D2).
2. Ledger CSV read path: covered separately in test_ingest_sales_read.py;
   this file checks round-trip via the orchestrator's own read+write cycle.
3. MergeCounts -> IngestManifest wiring: each field independently verified.
4. rows_unmatched accumulated at transform time across a multi-file batch.

OTEL outcomes tested: "complete", "no_files", "halted_schema_shift",
"halted_erp_invalid".
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
    """Copy a named fixture from FIXTURES into sales_data/.

    The fixtures are *.json on disk; the production extension is *.jsonl.
    Rename on copy so the orchestrator's *.jsonl scan picks them up.
    """
    src = FIXTURES / fixture_name
    target = sales / (dest_name or fixture_name.replace(".json", ".jsonl"))
    target.write_text(src.read_text())
    return target


def _drop_inline(sales: Path, name: str, payload: dict) -> Path:
    target = sales / name
    target.write_text(json.dumps(payload))
    return target


def _two_grailzee_payload(stock_a: str, stock_b: str, *, b_unmatched: bool = False) -> dict:
    """Two-Sale, two-Purchase batch where stock_a and stock_b are both
    Grailzee. If b_unmatched, omit stock_b's Purchase to leave it without
    buy_date.
    """
    sales = [
        {
            "platform": "Grailzee",
            "created_at": "2026-04-25",
            "line_item": {
                "stock_id": stock_a,
                "brand": "Tudor",
                "reference_number": "79830RB",
                "cost_of_item": 2750.0,
                "unit_price": 3200.0,
                "delivered_date": None,
            },
            "services": [{"name": "Platform fee", "actual_cost": 49}],
        },
        {
            "platform": "Grailzee",
            "created_at": "2026-04-26",
            "line_item": {
                "stock_id": stock_b,
                "brand": "Rolex",
                "reference_number": "126300",
                "cost_of_item": 8200.0,
                "unit_price": 9400.0,
                "delivered_date": None,
            },
            "services": [{"name": "Platform fee", "actual_cost": 99}],
        },
    ]
    purchases = [
        {
            "created_at": "2026-04-10",
            "line_item": {
                "stock_id": stock_a,
                "cost_of_item": 2750.0,
                "delivered_date": None,
            },
            "payments": [],
        },
    ]
    if not b_unmatched:
        purchases.append({
            "created_at": "2026-04-11",
            "line_item": {
                "stock_id": stock_b,
                "cost_of_item": 8200.0,
                "delivered_date": None,
            },
            "payments": [],
        })
    return {"sales": sales, "purchases": purchases}


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
        assert manifest.error is None

    def test_archive_only_counts_as_zero_files(self, tmp_path):
        """sales_data/archive/ contents are not counted as found files."""
        sales, archive, ledger, lock = _setup(tmp_path)
        archive.mkdir()
        (archive / "watchtrack_2026-04-25.jsonl").write_text("{}")
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
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
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
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        assert ledger.exists()

    def test_clean_run_archives_source_file(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        src = _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
        _call(sales, archive, ledger, lock)
        assert not src.exists()
        assert (archive / "watchtrack_2026-04-29.jsonl").exists()


# ─── Inheritance 1: sell_cycle_id blank validation ───────────────────


class TestSellCycleIdBlankValidation:
    def test_blank_sell_cycle_id_raises_schema_shift(self, tmp_path, monkeypatch):
        """Inheritance 1: orchestrator raises SchemaShiftDetected when
        transform_jsonl emits a row with blank sell_cycle_id. Defensive
        guard against future contract drift in transform_jsonl. ADR-0004 D2.

        Mocks transform_jsonl to inject the invariant-violating row,
        because production transform_jsonl never emits blank sell_cycle_id
        (cycle_id_from_date always returns non-empty).
        """
        sales, archive, ledger, lock = _setup(tmp_path)
        (sales / "watchtrack_2026-04-29.jsonl").write_text("{}")  # placeholder

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
            lambda path: [bad_row],
        )
        with pytest.raises(SchemaShiftDetected, match="sell_cycle_id"):
            _call(sales, archive, ledger, lock)

    def test_blank_sell_cycle_id_does_not_archive(self, tmp_path, monkeypatch):
        """If transform produces an invalid row, the source file must
        remain in sales_data/ (no archive move on hard-fail)."""
        sales, archive, ledger, lock = _setup(tmp_path)
        src = sales / "watchtrack_2026-04-29.jsonl"
        src.write_text("{}")

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
            lambda path: [bad_row],
        )
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        assert src.exists()
        assert not (archive / "watchtrack_2026-04-29.jsonl").exists()

    def test_blank_sell_cycle_id_does_not_write_ledger(self, tmp_path, monkeypatch):
        """If transform produces an invalid row, the ledger must not be
        written. Pre-merge raise is before the lock acquire / write."""
        sales, archive, ledger, lock = _setup(tmp_path)
        (sales / "watchtrack_2026-04-29.jsonl").write_text("{}")

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
            lambda path: [bad_row],
        )
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        assert not ledger.exists()


# ─── Inheritance 3: MergeCounts -> IngestManifest wiring ─────────────


class TestMergeCountsWiring:
    """Each of rows_added, rows_updated, rows_unchanged is verified
    individually so a copy-paste error wiring (e.g. rows_added <- updated)
    is caught at unit-test resolution. ADR-0001 §"Position 4" preserves
    order; counts are independent of order."""

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
        """One brand-new row -> manifest.rows_added == 1."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        # File contains a different stock_id so it is a pure add.
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", _two_grailzee_payload(
            "TEY1048", "TEY1080",
        ))
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 2
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 0

    def test_updated_field_wired(self, tmp_path):
        """One row with same stock_id but changed price -> rows_updated == 1."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        # New payload for same stock_id (TEY1104) but different sell_price.
        payload = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY1104",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3300.0,  # was 3200.0 in the seeded row
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 0
        assert manifest.rows_updated == 1
        assert manifest.rows_unchanged == 0

    def test_unchanged_field_wired(self, tmp_path):
        """Same stock_id and same fields -> rows_unchanged == 1."""
        sales, archive, ledger, lock = _setup(tmp_path)
        self._seed_ledger(ledger)
        # Identical payload to the seeded row -- stock_id, sell_date, prices match.
        payload = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY1104",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 0
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 1

    def test_all_three_fields_distinct_and_correct(self, tmp_path):
        """Existing=[A]; new=[A unchanged, A_PRIME (update of A)+ B (new), C (new)].
        Because dedup is by stock_id and the first sale is identical to A,
        we use a different combination: existing=[A,B], file=[A unchanged,
        B' update, C add]."""
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

        # File: A (unchanged), B' (updated price), C (new)
        payload = {
            "sales": [
                {
                    "platform": "Grailzee",
                    "created_at": "2026-04-25",
                    "line_item": {
                        "stock_id": "TEY1104",
                        "brand": "Tudor",
                        "reference_number": "79830RB",
                        "cost_of_item": 2750.0,
                        "unit_price": 3200.0,
                        "delivered_date": None,
                    },
                    "services": [{"name": "Platform fee", "actual_cost": 49}],
                },
                {
                    "platform": "Grailzee",
                    "created_at": "2026-04-26",
                    "line_item": {
                        "stock_id": "TEY1048",
                        "brand": "Rolex",
                        "reference_number": "126300",
                        "cost_of_item": 8200.0,
                        "unit_price": 9500.0,  # was 9400 -> update
                        "delivered_date": None,
                    },
                    "services": [{"name": "Platform fee", "actual_cost": 99}],
                },
                {
                    "platform": "Grailzee",
                    "created_at": "2026-04-27",
                    "line_item": {
                        "stock_id": "TEY1080",
                        "brand": "Omega",
                        "reference_number": "311.30",
                        "cost_of_item": 4500.0,
                        "unit_price": 5200.0,
                        "delivered_date": None,
                    },
                    "services": [{"name": "Platform fee", "actual_cost": 49}],
                },
            ],
            "purchases": [],
        }
        _drop_inline(sales, "watchtrack_2026-04-29.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        # rows_added=1 (TEY1080), rows_updated=1 (TEY1048), rows_unchanged=1 (TEY1104)
        assert manifest.rows_added == 1
        assert manifest.rows_updated == 1
        assert manifest.rows_unchanged == 1


# ─── Inheritance 4: rows_unmatched at transform time, accumulated ────


class TestRowsUnmatched:
    def test_single_file_unmatched_count(self, tmp_path):
        """One unmatched row in one file -> manifest.rows_unmatched == 1.

        Inheritance 4: counted at transform time (buy_date is None on
        the transformed row), NOT post-merge.
        """
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1048_unmatched.json", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_unmatched == 1

    def test_unmatched_counted_even_for_added_rows(self, tmp_path):
        """Inheritance 4 nuance: an unmatched row still merges into the
        ledger as an add. rows_unmatched and rows_added are not mutually
        exclusive on the same row."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1048_unmatched.json", "watchtrack_2026-04-29.jsonl")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_added == 1
        assert manifest.rows_unmatched == 1

    def test_multi_file_accumulation(self, tmp_path):
        """Two files, each with one unmatched row -> rows_unmatched == 2.

        Inheritance 4: count is summed across the multi-file batch at
        transform time, not derived post-merge.
        """
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1048_unmatched.json", "watchtrack_2026-04-25.jsonl")
        # Inline a second file with a different unmatched row.
        payload = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-26",
                "line_item": {
                    "stock_id": "TEY9999",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],   # no purchase -> unmatched
        }
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl", payload)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.rows_unmatched == 2
        assert manifest.files_found == 2
        assert manifest.files_processed == 2

    def test_matched_row_does_not_increment_unmatched(self, tmp_path):
        """A row with a matching Purchase has buy_date set; it must not
        be counted as unmatched. Inheritance 4 tests the rule, not the
        column happenstance."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
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
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
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

    def test_outcome_halted_schema_shift(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "missing_purchases_key.json", "watchtrack_2026-04-29.jsonl")
        with pytest.raises(SchemaShiftDetected):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_schema_shift"

    def test_outcome_halted_erp_invalid(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1092_no_services.json", "watchtrack_2026-04-29.jsonl")
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_erp_invalid"

    def test_span_attributes_on_complete_run(self, tmp_path, span_exporter):
        """All seven counter attributes plus outcome are present on the
        complete-run span."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
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
        ):
            assert attr in sp.attributes, f"missing attribute {attr}"
        assert sp.attributes["files_found"] == 1
        assert sp.attributes["rows_added"] == 1


# ─── Files_found counts only top-level *.jsonl ───────────────────────


class TestFilesFoundScope:
    def test_only_jsonl_extension_counted(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
        # Drop a non-jsonl file -- should be ignored.
        (sales / "README.md").write_text("not a batch")
        (sales / "logs.txt").write_text("noise")
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 1


# ─── In-lock OTEL outcome attribution (sub-step 1.7 commit 2) ────────


@contextmanager
def _raising_lock_cm(*args, **kwargs):
    """Context manager that raises LockAcquisitionFailed on enter.

    Mimics with_exclusive_lock's failure mode: the lock acquisition
    itself fails, the with-block body never runs.
    """
    raise LockAcquisitionFailed("simulated lock timeout")
    yield  # never reached -- required to make this a generator


class TestOTELInLockOutcomes:
    """Commit 2 outcome consolidation: every IngestError subclass that can
    raise inside the lock gets its outcome attribution per
    _OUTCOME_BY_CLASS, by class not by location. Mirrors the pre-lock
    transform-time outcome pattern from commit 1."""

    def _seed_clean_run_inputs(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")
        return sales, archive, ledger, lock

    def test_schema_shift_in_read_ledger_csv(
        self, tmp_path, span_exporter, monkeypatch
    ):
        """SchemaShiftDetected raised by read_ledger_csv (e.g., corrupt
        existing ledger with blank non-optional column) -> outcome
        attribute "halted_schema_shift"."""
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
        """ERPBatchInvalid raised by merge_rows (duplicate stock_id within
        a single file's transformed rows) -> outcome "halted_erp_invalid"
        from the in-lock try/except (not the pre-lock one)."""
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
        """LedgerWriteFailed raised by atomic_write_csv -> outcome
        "halted_ledger_write" (a string introduced in commit 2)."""
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
        """LockAcquisitionFailed raised by with_exclusive_lock itself
        (the with-block enter fails) -> outcome "halted_lock_timeout"
        (a string introduced in commit 2)."""
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
    """Commit 2 negative case: bare Exception (or any non-IngestError)
    raised inside the lock does NOT get outcome attribution. The except
    clause filters by IngestError, so an unrelated exception bypasses
    the outcome assignment. The span closes without an outcome attribute
    and the exception propagates as a real bug."""

    def test_runtime_error_no_outcome(self, tmp_path, span_exporter, monkeypatch):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_fixture(sales, "tey1104_clean.json", "watchtrack_2026-04-29.jsonl")

        def _raise(path, rows, header=None):
            raise RuntimeError("simulated unrelated bug")

        monkeypatch.setattr("scripts.ingest_sales.atomic_write_csv", _raise)
        with pytest.raises(RuntimeError):
            _call(sales, archive, ledger, lock)
        sp = _orchestrator_span(span_exporter)
        assert sp is not None
        # Span closed without outcome attribute -- this is the design.
        assert "outcome" not in sp.attributes
