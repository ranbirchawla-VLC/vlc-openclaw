"""Integration tests for the ingest_sales orchestrator (sub-step 1.7 commit 2).

End-to-end composition validation against design v1 §13.1 four scenarios
plus idempotency (§12.5) and lock-release-on-exception. Unit-level
inheritances + OTEL outcomes live in test_ingest_sales_orchestrator.py;
these tests exercise the full primitive composition with real fixture
content moving through transform -> merge -> prune -> write -> archive.

File-naming convention: ISO-dash dates so alphabetical sort matches
chronological order (handoff §5 #7 carry-forward); watchtrack_<date>.jsonl
fixtures dropped into sales_data/ are the orchestrator's scan input.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    ERPBatchInvalid,
    IngestError,
    LedgerRow,
    LedgerWriteFailed,
    SchemaShiftDetected,
    atomic_write_csv,
    ingest_sales,
    read_ledger_csv,
    with_exclusive_lock,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ingest_sales"


# ─── Setup helpers ───────────────────────────────────────────────────


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Return (sales_data_dir, archive_dir, ledger_path, lock_path).

    Lock path is local to tmp_path so tests do not contend on the
    production ~/.grailzee/trade_ledger.lock.
    """
    sales = tmp_path / "sales_data"
    sales.mkdir()
    archive = sales / "archive"
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "trade_ledger.csv"
    lock = tmp_path / "trade_ledger.lock"
    return sales, archive, ledger, lock


def _drop_fixture(sales: Path, fixture_name: str, dest_name: str) -> Path:
    """Copy a JSONL fixture into sales_data/ under a chosen name."""
    src = FIXTURES / fixture_name
    target = sales / dest_name
    target.write_text(src.read_text())
    return target


def _drop_inline(sales: Path, name: str, payload: dict) -> Path:
    target = sales / name
    target.write_text(json.dumps(payload))
    return target


def _grailzee_payload(stock_id: str, *, matched: bool = True) -> dict:
    """Single-Sale, optional-Purchase payload, all valid Grailzee."""
    sales_block = [{
        "platform": "Grailzee",
        "created_at": "2026-04-25",
        "line_item": {
            "stock_id": stock_id,
            "brand": "Tudor",
            "reference_number": "79830RB",
            "cost_of_item": 2750.0,
            "unit_price": 3200.0,
            "delivered_date": None,
        },
        "services": [{"name": "Platform fee", "actual_cost": 49}],
    }]
    purchases_block = []
    if matched:
        purchases_block.append({
            "created_at": "2026-04-10",
            "line_item": {
                "stock_id": stock_id,
                "cost_of_item": 2750.0,
                "delivered_date": None,
            },
            "payments": [],
        })
    return {"sales": sales_block, "purchases": purchases_block}


def _call(sales, archive, ledger, lock, *, today: date = date(2026, 4, 29)):
    return ingest_sales(
        sales_data_dir=sales,
        archive_dir=archive,
        ledger_path=ledger,
        lock_path=lock,
        today=today,
    )


# ─── Scenario 1: full clean run end-to-end ────────────────────────────


class TestScenario1FullCleanRun:
    """Multi-file batch, all valid Grailzee, ledger pre-state empty.
    Verifies the full composition: transform each, merge under lock,
    prune, atomic write, archive each."""

    def test_writes_ledger_with_correct_row_count(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY1001"))
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                     _grailzee_payload("TEY1002"))
        _drop_inline(sales, "watchtrack_2026-04-27.jsonl",
                     _grailzee_payload("TEY1003"))
        _call(sales, archive, ledger, lock)
        rows = read_ledger_csv(ledger)
        assert len(rows) == 3
        assert {r.stock_id for r in rows} == {"TEY1001", "TEY1002", "TEY1003"}

    def test_archives_all_source_files(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        f1 = _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                          _grailzee_payload("TEY1001"))
        f2 = _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                          _grailzee_payload("TEY1002"))
        f3 = _drop_inline(sales, "watchtrack_2026-04-27.jsonl",
                          _grailzee_payload("TEY1003"))
        _call(sales, archive, ledger, lock)
        for source in (f1, f2, f3):
            assert not source.exists(), f"source {source.name} not archived"
            assert (archive / source.name).exists(), \
                f"archived {source.name} missing"

    def test_manifest_reports_complete(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY1001"))
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                     _grailzee_payload("TEY1002"))
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 2
        assert manifest.files_processed == 2
        assert manifest.last_processed == "watchtrack_2026-04-26.jsonl"
        assert manifest.rows_added == 2
        assert manifest.rows_updated == 0
        assert manifest.rows_unchanged == 0
        assert manifest.error is None

    def test_otel_outcome_complete(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY1001"))
        _call(sales, archive, ledger, lock)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.ingest_sales"),
            None,
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "complete"


# ─── Scenario 2: mid-batch failure atomicity ──────────────────────────


class TestScenario2MidBatchFailureAtomicity:
    """Three files in alphabetical/chronological order; the middle file
    raises ERPBatchInvalid via tey1092_no_services. Pre-seed the ledger
    with one known row so atomicity has something to verify against
    (post-state must be byte-identical to pre-state).

    The raise happens during transform_jsonl (pre-lock), so the lock
    is never acquired. Archive loop is post-lock and is also never
    reached. Atomicity is trivially preserved on this path; the test
    confirms nothing slipped through.
    """

    def _seed_ledger_with(self, ledger: Path, stock_id: str = "TEY9999") -> bytes:
        existing = LedgerRow(
            stock_id=stock_id,
            sell_date=date(2026, 4, 1),
            sell_cycle_id="cycle_2026-07",
            brand="Pre-Existing",
            reference="REF-PRE",
            account="NR",
            buy_price=1000.0,
            sell_price=1500.0,
        )
        atomic_write_csv(ledger, [existing])
        return ledger.read_bytes()

    def _setup_three_files_with_middle_invalid(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        # File 1: clean
        f1 = _drop_inline(
            sales, "watchtrack_2026-04-25.jsonl", _grailzee_payload("TEY1001")
        )
        # File 2: no services -> ERPBatchInvalid in transform
        f2 = _drop_fixture(
            sales, "tey1092_no_services.json", "watchtrack_2026-04-26.jsonl"
        )
        # File 3: clean
        f3 = _drop_inline(
            sales, "watchtrack_2026-04-27.jsonl", _grailzee_payload("TEY1003")
        )
        return sales, archive, ledger, lock, f1, f2, f3

    def test_raises_erp_batch_invalid(self, tmp_path):
        sales, archive, ledger, lock, *_ = (
            self._setup_three_files_with_middle_invalid(tmp_path)
        )
        self._seed_ledger_with(ledger)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)

    def test_no_archive_moves_on_raise(self, tmp_path):
        sales, archive, ledger, lock, f1, f2, f3 = (
            self._setup_three_files_with_middle_invalid(tmp_path)
        )
        self._seed_ledger_with(ledger)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        # All three source files must remain in sales_data/
        for source in (f1, f2, f3):
            assert source.exists(), f"{source.name} archived despite raise"
        # archive/ either doesn't exist or is empty
        if archive.exists():
            assert list(archive.iterdir()) == []

    def test_ledger_bytes_unchanged_on_raise(self, tmp_path):
        sales, archive, ledger, lock, *_ = (
            self._setup_three_files_with_middle_invalid(tmp_path)
        )
        seeded_bytes = self._seed_ledger_with(ledger)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        assert ledger.read_bytes() == seeded_bytes, \
            "ledger content changed despite mid-batch raise -- atomicity broken"

    def test_lock_released_after_raise(self, tmp_path):
        """After the orchestrator raises, the next caller can acquire
        the exclusive lock with a short timeout. With pre-lock raise
        the lock was never acquired, so this is trivially true; the
        in-lock case is covered in Scenario 6."""
        sales, archive, ledger, lock, *_ = (
            self._setup_three_files_with_middle_invalid(tmp_path)
        )
        self._seed_ledger_with(ledger)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        with with_exclusive_lock(lock, timeout=0.5):
            pass

    def test_otel_outcome_halted_erp_invalid(self, tmp_path, span_exporter):
        sales, archive, ledger, lock, *_ = (
            self._setup_three_files_with_middle_invalid(tmp_path)
        )
        self._seed_ledger_with(ledger)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.ingest_sales"),
            None,
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "halted_erp_invalid"


# ─── Scenario 3: zero-files end-to-end ────────────────────────────────


class TestScenario3ZeroFilesEndToEnd:
    """Empty sales_data/. Orchestrator short-circuits to manifest with
    files_found=0 and outcome="no_files" without acquiring the lock."""

    def test_zero_files_returns_zero_manifest(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        manifest = _call(sales, archive, ledger, lock)
        assert manifest.files_found == 0
        assert manifest.files_processed == 0

    def test_zero_files_does_not_create_ledger(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _call(sales, archive, ledger, lock)
        assert not ledger.exists()

    def test_zero_files_does_not_create_archive(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _call(sales, archive, ledger, lock)
        assert not archive.exists()

    def test_zero_files_otel_outcome_no_files(self, tmp_path, span_exporter):
        sales, archive, ledger, lock = _setup(tmp_path)
        _call(sales, archive, ledger, lock)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.ingest_sales"),
            None,
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "no_files"


# ─── Scenario 4: multi-file merge into ledger ─────────────────────────


class TestScenario4MultiFileMerge:
    """Two files, both valid; rows from both end up in the merged ledger
    after a single ingest_sales invocation. Specifically validates the
    merge-loop accumulation across files."""

    def test_two_files_both_archived(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        f1 = _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                          _grailzee_payload("TEY2001"))
        f2 = _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                          _grailzee_payload("TEY2002"))
        _call(sales, archive, ledger, lock)
        assert (archive / f1.name).exists()
        assert (archive / f2.name).exists()

    def test_two_files_rows_merged_into_ledger(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY2001"))
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                     _grailzee_payload("TEY2002"))
        _call(sales, archive, ledger, lock)
        rows = read_ledger_csv(ledger)
        ids = {r.stock_id for r in rows}
        assert ids == {"TEY2001", "TEY2002"}

    def test_existing_ledger_row_preserved_alongside_new_rows(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        existing = LedgerRow(
            stock_id="TEY9000",
            sell_date=date(2026, 4, 1),
            sell_cycle_id="cycle_2026-07",
            brand="Existing",
            reference="REF-EX",
            account="NR",
            buy_price=500.0,
            sell_price=750.0,
        )
        atomic_write_csv(ledger, [existing])
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY2001"))
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                     _grailzee_payload("TEY2002"))
        _call(sales, archive, ledger, lock)
        rows = read_ledger_csv(ledger)
        ids = {r.stock_id for r in rows}
        assert ids == {"TEY9000", "TEY2001", "TEY2002"}


# ─── Scenario 5: idempotency (§12.5, sharper than "no-op") ────────────


class TestScenario5Idempotency:
    """Two consecutive runs against the same effective state. After the
    first run, sales_data/ contains only archive/ contents; the second
    run's scan finds zero top-level files and short-circuits.

    Atomicity-of-no-op contract: ledger CSV mtime unchanged AND bytes
    byte-identical between runs. Mtime-unchanged is the strong assertion
    (no rewrite occurred at all under the no_files path); bytes-identical
    is belt-and-suspenders against a future regression where the no_files
    branch grows logic that touches the ledger.
    """

    def _first_run(self, tmp_path):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY3001"))
        _drop_inline(sales, "watchtrack_2026-04-26.jsonl",
                     _grailzee_payload("TEY3002"))
        manifest1 = _call(sales, archive, ledger, lock)
        return sales, archive, ledger, lock, manifest1

    def test_second_run_files_found_zero(self, tmp_path):
        sales, archive, ledger, lock, manifest1 = self._first_run(tmp_path)
        assert manifest1.files_processed == 2  # sanity check
        manifest2 = _call(sales, archive, ledger, lock)
        assert manifest2.files_found == 0
        assert manifest2.files_processed == 0
        assert manifest2.rows_added == 0
        assert manifest2.rows_updated == 0
        assert manifest2.rows_unchanged == 0

    def test_second_run_ledger_mtime_unchanged(self, tmp_path):
        """Strong assertion: the no_files path does not rewrite the
        ledger at all -- mtime stays at the first-run value.

        Sleep crosses the 1-second boundary so coarse-resolution
        filesystems (HFS+, FAT) would still surface a rewrite. The
        bytes-identical sibling test is belt-and-suspenders if mtime
        resolution misses; both are intentional.
        """
        sales, archive, ledger, lock, _ = self._first_run(tmp_path)
        mtime_after_first = ledger.stat().st_mtime_ns
        time.sleep(1.05)
        _call(sales, archive, ledger, lock)
        mtime_after_second = ledger.stat().st_mtime_ns
        assert mtime_after_second == mtime_after_first, \
            "ledger was rewritten on no_files path -- §12.5 idempotency broken"

    def test_second_run_ledger_bytes_identical(self, tmp_path):
        """Belt-and-suspenders: bytes match between runs. Trivially true
        when mtime is unchanged but explicit so a future regression
        where the no_files branch DOES rewrite is still caught here."""
        sales, archive, ledger, lock, _ = self._first_run(tmp_path)
        bytes_after_first = ledger.read_bytes()
        _call(sales, archive, ledger, lock)
        bytes_after_second = ledger.read_bytes()
        assert bytes_after_first == bytes_after_second

    def test_second_run_archive_unchanged(self, tmp_path):
        sales, archive, ledger, lock, _ = self._first_run(tmp_path)
        before = sorted(p.name for p in archive.iterdir())
        _call(sales, archive, ledger, lock)
        after = sorted(p.name for p in archive.iterdir())
        assert before == after

    def test_second_run_otel_no_files(self, tmp_path, span_exporter):
        sales, archive, ledger, lock, _ = self._first_run(tmp_path)
        # Clear spans collected during first run.
        span_exporter.clear()
        _call(sales, archive, ledger, lock)
        sp = next(
            (s for s in span_exporter.get_finished_spans()
             if s.name == "ingest_sales.ingest_sales"),
            None,
        )
        assert sp is not None
        assert sp.attributes["outcome"] == "no_files"


# ─── Scenario 6: lock-release-on-exception ────────────────────────────


class TestScenario6LockReleaseOnException:
    """In-lock raise releases the lock via the with-block. Verified by
    attempting a second exclusive acquisition with a short timeout
    immediately after the orchestrator raised. This guards against a
    regression where a future change moves logic outside the with-block
    such that the language-level guarantee no longer applies.
    """

    def test_lock_released_after_in_lock_ingest_error(
        self, tmp_path, monkeypatch
    ):
        """Monkeypatch merge_rows to raise IngestError in-lock, call
        ingest_sales, expect raise; then attempt with_exclusive_lock with
        a short timeout and assert it acquires."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY4001"))

        def _raise(existing, new):
            raise ERPBatchInvalid("simulated in-lock failure")

        monkeypatch.setattr("scripts.ingest_sales.merge_rows", _raise)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        # Second acquisition with short timeout. If the with-block did
        # not release on exception, this raises LockAcquisitionFailed.
        with with_exclusive_lock(lock, timeout=0.2):
            pass

    def test_lock_released_after_in_lock_ledger_write_failed(
        self, tmp_path, monkeypatch
    ):
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY4001"))

        def _raise(path, rows, header=None):
            raise LedgerWriteFailed("simulated write failure")

        monkeypatch.setattr("scripts.ingest_sales.atomic_write_csv", _raise)
        with pytest.raises(LedgerWriteFailed):
            _call(sales, archive, ledger, lock)
        with with_exclusive_lock(lock, timeout=0.2):
            pass

    def test_lock_released_after_in_lock_runtime_error(
        self, tmp_path, monkeypatch
    ):
        """Even non-IngestError exceptions in the with-block must release
        the lock -- the with-block exit is unconditional. Outcome
        attribute is not set (TestBareExceptionInLock asserts that), but
        lock release still works."""
        sales, archive, ledger, lock = _setup(tmp_path)
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY4001"))

        def _raise(path, rows, header=None):
            raise RuntimeError("simulated unrelated bug in lock")

        monkeypatch.setattr("scripts.ingest_sales.atomic_write_csv", _raise)
        with pytest.raises(RuntimeError):
            _call(sales, archive, ledger, lock)
        with with_exclusive_lock(lock, timeout=0.2):
            pass

    def test_in_lock_raise_preserves_ledger_bytes(self, tmp_path, monkeypatch):
        """In-lock atomicity (complement to Scenario 2's pre-lock check):
        seed the ledger with a known row, monkeypatch merge_rows to raise
        IngestError after read_ledger_csv but before atomic_write_csv,
        verify the on-disk ledger bytes are byte-identical to the seeded
        bytes. Proves the orchestrator does not partially write on
        in-lock raise."""
        sales, archive, ledger, lock = _setup(tmp_path)
        existing = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2026, 4, 1),
            sell_cycle_id="cycle_2026-07",
            brand="Pre-Existing",
            reference="REF-PRE",
            account="NR",
            buy_price=1000.0,
            sell_price=1500.0,
        )
        atomic_write_csv(ledger, [existing])
        seeded_bytes = ledger.read_bytes()
        _drop_inline(sales, "watchtrack_2026-04-25.jsonl",
                     _grailzee_payload("TEY4001"))

        def _raise(existing, new):
            raise ERPBatchInvalid("simulated in-lock failure post-read")

        monkeypatch.setattr("scripts.ingest_sales.merge_rows", _raise)
        with pytest.raises(ERPBatchInvalid):
            _call(sales, archive, ledger, lock)
        assert ledger.read_bytes() == seeded_bytes, \
            "in-lock raise wrote partial ledger -- atomicity broken"


# ─── CLI surface (sub-step 1.7 commit 2) ──────────────────────────────


class TestCLISurface:
    """The __main__ block is a minimal operator escape hatch. Zero
    arguments, env-resolved paths, exit 0/1 by IngestError. Subprocess
    invocation lets us verify the actual entry-point behavior without
    importing into the test process.
    """

    def _env_for(self, tmp_path: Path) -> dict[str, str]:
        """Environment for the subprocess: GRAILZEE_ROOT pointing at
        the test sandbox so the orchestrator's defaults resolve into
        tmp_path/state, tmp_path/sales_data, etc.
        """
        env = os.environ.copy()
        env["GRAILZEE_ROOT"] = str(tmp_path)
        env["GRAILZEE_LOCK_PATH"] = str(tmp_path / "trade_ledger.lock")
        # PYTHONPATH so the subprocess can import scripts.ingest_sales.
        repo_root = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = str(repo_root)
        return env

    def _setup_sandbox(self, tmp_path: Path) -> None:
        (tmp_path / "sales_data").mkdir()
        (tmp_path / "state").mkdir()

    def test_exit_zero_on_no_files(self, tmp_path):
        """Empty sales_data/: subprocess exits 0 and prints a manifest
        summary line on stdout."""
        self._setup_sandbox(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "scripts.ingest_sales"],
            env=self._env_for(tmp_path),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0, result.stderr
        assert "files_found=0" in result.stdout
        assert "files_processed=0" in result.stdout

    def test_exit_one_on_ingest_error(self, tmp_path):
        """Drop a fixture that raises during transform; subprocess exits
        1 and prints "<ClassName>: <message>" on stderr."""
        self._setup_sandbox(tmp_path)
        sales = tmp_path / "sales_data"
        # tey1092_no_services -> ERPBatchInvalid in transform_jsonl
        target = sales / "watchtrack_2026-04-25.jsonl"
        target.write_text((FIXTURES / "tey1092_no_services.json").read_text())
        result = subprocess.run(
            [sys.executable, "-m", "scripts.ingest_sales"],
            env=self._env_for(tmp_path),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 1
        assert "ERPBatchInvalid" in result.stderr
