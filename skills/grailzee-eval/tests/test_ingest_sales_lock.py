"""Tests for lockfile and atomic write primitives — sub-step 1.3.

Lock contention tests use subprocess.Popen so that flock semantics operate
across OS processes (flock is per-process on POSIX/macOS; threads within the
same process share lock state and cannot contend with each other).

Atomic write tests use a real temp directory and real fsync; the rename-
interrupted case mocks os.rename to verify the error path without needing
kernel-level signal injection.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.ingest_sales import (
    LEDGER_CSV_COLUMNS,
    LedgerRow,
    LedgerWriteFailed,
    LockAcquisitionFailed,
    atomic_write_csv,
    with_exclusive_lock,
    with_shared_lock,
)

# Absolute path to skills/grailzee-eval — injected into subprocess PYTHONPATH.
_GRAILZEE_EVAL = str(Path(__file__).parent.parent)

_SAMPLE_ROW = LedgerRow(
    stock_id="TEY1104",
    sell_date=date(2026, 4, 25),
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.0,
    sell_price=3200.0,
    buy_date=date(2026, 4, 10),
    buy_cycle_id="cycle_2026-07",
    buy_received_date=date(2026, 4, 12),
    sell_delivered_date=date(2026, 4, 27),
    buy_paid_date=date(2026, 4, 11),
)


def _spawn_lock_holder(
    lock_path: Path,
    lock_fn: str,
    hold_secs: float,
) -> subprocess.Popen:
    """Start a subprocess that acquires lock_fn on lock_path for hold_secs.

    The subprocess writes "acquired\\n" to stdout once the lock is held,
    then sleeps hold_secs, then exits (releasing the lock on process exit).
    """
    code = (
        f"import sys; sys.path.insert(0, {_GRAILZEE_EVAL!r})\n"
        f"from pathlib import Path\n"
        f"from scripts.ingest_sales import {lock_fn}\n"
        f"import time\n"
        f"with {lock_fn}(Path({str(lock_path)!r}), timeout=10):\n"
        f"    sys.stdout.write('acquired\\n'); sys.stdout.flush()\n"
        f"    time.sleep({hold_secs!r})\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_acquired(proc: subprocess.Popen) -> None:
    """Block until the subprocess signals it holds the lock."""
    line = proc.stdout.readline()
    assert line == "acquired\n", f"subprocess did not acquire lock: {line!r}"


# ─── Exclusive lock — single process ─────────────────────────────────


class TestExclusiveLockSingleProcess:
    def test_creates_lockfile_on_first_use(self, tmp_path):
        lock = tmp_path / "test.lock"
        assert not lock.exists()
        with with_exclusive_lock(lock, timeout=5):
            assert lock.exists()

    def test_can_reacquire_after_release(self, tmp_path):
        lock = tmp_path / "test.lock"
        with with_exclusive_lock(lock, timeout=5):
            pass
        # No exception means lock was released and re-acquired.
        with with_exclusive_lock(lock, timeout=1):
            pass

    def test_yields_control_to_body(self, tmp_path):
        lock = tmp_path / "test.lock"
        ran = []
        with with_exclusive_lock(lock, timeout=5):
            ran.append(True)
        assert ran == [True]

    def test_releases_on_exception_in_body(self, tmp_path):
        lock = tmp_path / "test.lock"
        with pytest.raises(ValueError):
            with with_exclusive_lock(lock, timeout=5):
                raise ValueError("body error")
        # Should be able to re-acquire immediately.
        with with_exclusive_lock(lock, timeout=1):
            pass

    def test_timeout_raises_lock_acquisition_failed(self, tmp_path):
        """Mock flock to always raise BlockingIOError to simulate contention."""
        lock = tmp_path / "test.lock"
        with patch("fcntl.flock", side_effect=BlockingIOError):
            with pytest.raises(LockAcquisitionFailed, match=str(lock)):
                with with_exclusive_lock(lock, timeout=0.1):
                    pass


# ─── Shared lock — single process ────────────────────────────────────


class TestSharedLockSingleProcess:
    def test_creates_lockfile_on_first_use(self, tmp_path):
        lock = tmp_path / "test.lock"
        assert not lock.exists()
        with with_shared_lock(lock, timeout=5):
            assert lock.exists()

    def test_can_reacquire_after_release(self, tmp_path):
        lock = tmp_path / "test.lock"
        with with_shared_lock(lock, timeout=5):
            pass
        with with_shared_lock(lock, timeout=1):
            pass

    def test_timeout_raises_lock_acquisition_failed(self, tmp_path):
        lock = tmp_path / "test.lock"
        with patch("fcntl.flock", side_effect=BlockingIOError):
            with pytest.raises(LockAcquisitionFailed):
                with with_shared_lock(lock, timeout=0.1):
                    pass


# ─── Lock contention — two processes ─────────────────────────────────


class TestLockContention:
    def test_exclusive_waits_for_exclusive_holder(self, tmp_path):
        """Second LOCK_EX waits while first holds, then acquires after release."""
        lock = tmp_path / "test.lock"
        holder = _spawn_lock_holder(lock, "with_exclusive_lock", hold_secs=1.5)
        try:
            _wait_for_acquired(holder)
            t0 = time.monotonic()
            with with_exclusive_lock(lock, timeout=10):
                pass
            elapsed = time.monotonic() - t0
            assert elapsed >= 1.0, f"Acquired too fast ({elapsed:.2f}s); holder may not have been active"
        finally:
            holder.wait(timeout=10)
        assert holder.returncode == 0

    def test_exclusive_times_out_under_contention(self, tmp_path):
        """LOCK_EX times out when another process holds LOCK_EX."""
        lock = tmp_path / "test.lock"
        holder = _spawn_lock_holder(lock, "with_exclusive_lock", hold_secs=5.0)
        try:
            _wait_for_acquired(holder)
            with pytest.raises(LockAcquisitionFailed):
                with with_exclusive_lock(lock, timeout=0.3):
                    pass
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_shared_shared_coexistence(self, tmp_path):
        """Two LOCK_SH holders can coexist without blocking."""
        lock = tmp_path / "test.lock"
        h1 = _spawn_lock_holder(lock, "with_shared_lock", hold_secs=2.0)
        h2 = _spawn_lock_holder(lock, "with_shared_lock", hold_secs=2.0)
        try:
            _wait_for_acquired(h1)
            _wait_for_acquired(h2)  # would block forever if SH blocked SH
        finally:
            h1.wait(timeout=10)
            h2.wait(timeout=10)
        assert h1.returncode == 0
        assert h2.returncode == 0

    def test_shared_blocks_exclusive(self, tmp_path):
        """LOCK_SH holder prevents LOCK_EX acquisition."""
        lock = tmp_path / "test.lock"
        holder = _spawn_lock_holder(lock, "with_shared_lock", hold_secs=5.0)
        try:
            _wait_for_acquired(holder)
            with pytest.raises(LockAcquisitionFailed):
                with with_exclusive_lock(lock, timeout=0.3):
                    pass
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_exclusive_blocks_shared(self, tmp_path):
        """LOCK_EX holder prevents LOCK_SH acquisition."""
        lock = tmp_path / "test.lock"
        holder = _spawn_lock_holder(lock, "with_exclusive_lock", hold_secs=5.0)
        try:
            _wait_for_acquired(holder)
            with pytest.raises(LockAcquisitionFailed):
                with with_shared_lock(lock, timeout=0.3):
                    pass
        finally:
            holder.terminate()
            holder.wait(timeout=5)


# ─── Atomic CSV write ────────────────────────────────────────────────


class TestAtomicWriteCsv:
    def test_creates_target_file(self, tmp_path):
        target = tmp_path / "ledger.csv"
        atomic_write_csv(target, [_SAMPLE_ROW])
        assert target.exists()

    def test_tmp_file_removed_after_success(self, tmp_path):
        target = tmp_path / "ledger.csv"
        atomic_write_csv(target, [_SAMPLE_ROW])
        assert not Path(str(target) + ".tmp").exists()

    def test_round_trip_all_fields(self, tmp_path):
        """Write a row, read back via csv.DictReader, fields match source."""
        target = tmp_path / "ledger.csv"
        atomic_write_csv(target, [_SAMPLE_ROW])
        with open(target, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        r = rows[0]
        assert r["stock_id"] == "TEY1104"
        assert r["sell_date"] == "2026-04-25"
        assert r["buy_date"] == "2026-04-10"
        assert r["sell_cycle_id"] == "cycle_2026-08"
        assert r["buy_cycle_id"] == "cycle_2026-07"
        assert r["brand"] == "Tudor"
        assert r["reference"] == "79830RB"
        assert r["account"] == "NR"
        assert float(r["buy_price"]) == 2750.0
        assert float(r["sell_price"]) == 3200.0
        assert r["buy_received_date"] == "2026-04-12"
        assert r["sell_delivered_date"] == "2026-04-27"
        assert r["buy_paid_date"] == "2026-04-11"

    def test_none_dates_written_as_empty_string(self, tmp_path):
        target = tmp_path / "ledger.csv"
        row = LedgerRow(
            stock_id="TEY1048",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Rolex",
            reference="126300",
            account="RES",
            buy_price=8200.0,
            sell_price=9400.0,
        )
        atomic_write_csv(target, [row])
        with open(target, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        r = rows[0]
        assert r["buy_date"] == ""
        assert r["buy_cycle_id"] == ""
        assert r["buy_received_date"] == ""
        assert r["sell_delivered_date"] == ""
        assert r["buy_paid_date"] == ""

    def test_default_header_uses_ledger_csv_columns(self, tmp_path):
        target = tmp_path / "ledger.csv"
        atomic_write_csv(target, [_SAMPLE_ROW])
        with open(target, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == LEDGER_CSV_COLUMNS

    def test_custom_header_respected(self, tmp_path):
        target = tmp_path / "ledger.csv"
        custom = ["sell_date", "account", "sell_price"]
        atomic_write_csv(target, [_SAMPLE_ROW], header=custom)
        with open(target, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == custom

    def test_multiple_rows_written(self, tmp_path):
        target = tmp_path / "ledger.csv"
        row2 = LedgerRow(
            stock_id="TEY1048",
            sell_date=date(2026, 4, 20),
            sell_cycle_id="cycle_2026-08",
            brand="Rolex",
            reference="126300",
            account="RES",
            buy_price=8200.0,
            sell_price=9400.0,
        )
        atomic_write_csv(target, [_SAMPLE_ROW, row2])
        with open(target, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["stock_id"] == "TEY1104"
        assert rows[1]["stock_id"] == "TEY1048"

    def test_empty_rows_writes_header_only(self, tmp_path):
        target = tmp_path / "ledger.csv"
        atomic_write_csv(target, [])
        with open(target, newline="", encoding="utf-8") as f:
            content = f.read()
        assert content.startswith(",".join(LEDGER_CSV_COLUMNS[:3]))


class TestAtomicWriteFailures:
    def test_rename_failure_raises_ledger_write_failed(self, tmp_path):
        target = tmp_path / "ledger.csv"
        with patch("os.rename", side_effect=OSError("disk full")):
            with pytest.raises(LedgerWriteFailed, match="disk full"):
                atomic_write_csv(target, [_SAMPLE_ROW])

    def test_no_partial_target_on_rename_failure(self, tmp_path):
        """Target file must not exist after rename failure."""
        target = tmp_path / "ledger.csv"
        with patch("os.rename", side_effect=OSError("rename failed")):
            with pytest.raises(LedgerWriteFailed):
                atomic_write_csv(target, [_SAMPLE_ROW])
        assert not target.exists()

    def test_permission_denied_raises_ledger_write_failed(self, tmp_path):
        """PermissionError on write surfaces as LedgerWriteFailed."""
        target = tmp_path / "ledger.csv"
        tmp_path.chmod(0o555)
        try:
            with pytest.raises(LedgerWriteFailed):
                atomic_write_csv(target, [_SAMPLE_ROW])
        finally:
            tmp_path.chmod(0o755)

    def test_permission_denied_leaves_no_target(self, tmp_path):
        """Target must not be created when the write itself fails."""
        target = tmp_path / "ledger.csv"
        tmp_path.chmod(0o555)
        try:
            with pytest.raises(LedgerWriteFailed):
                atomic_write_csv(target, [_SAMPLE_ROW])
        finally:
            tmp_path.chmod(0o755)
        assert not target.exists()


# ─── B2: Inode re-check ───────────────────────────────────────────────


class TestInodeRecheck:
    def test_retries_when_inode_mismatches_on_first_attempt(self, tmp_path):
        """Simulates stale lockfile inode: first os.fstat returns wrong inode;
        retry from open() acquires correctly."""
        lock = tmp_path / "test.lock"
        real_fstat = os.fstat
        call_count = [0]

        def fake_fstat(fd_no: int):
            call_count[0] += 1
            real = real_fstat(fd_no)
            if call_count[0] == 1:
                # Return a mock with a different inode to trigger retry.
                m = MagicMock()
                m.st_ino = real.st_ino + 9999
                return m
            return real

        with patch("os.fstat", side_effect=fake_fstat):
            with with_exclusive_lock(lock, timeout=5):
                pass

        assert call_count[0] >= 2, "Inode re-check was not invoked twice"

    def test_shared_lock_also_rechecks_inode(self, tmp_path):
        """Inode re-check fires for LOCK_SH as well as LOCK_EX."""
        lock = tmp_path / "test.lock"
        real_fstat = os.fstat
        call_count = [0]

        def fake_fstat(fd_no: int):
            call_count[0] += 1
            real = real_fstat(fd_no)
            if call_count[0] == 1:
                m = MagicMock()
                m.st_ino = real.st_ino + 1
                return m
            return real

        with patch("os.fstat", side_effect=fake_fstat):
            with with_shared_lock(lock, timeout=5):
                pass

        assert call_count[0] >= 2


# ─── m1: extrasaction="raise" ────────────────────────────────────────


class TestExtrasaction:
    def test_extra_key_in_row_raises_ledger_write_failed(self, tmp_path):
        """extrasaction='raise': extra key wraps in LedgerWriteFailed, not raw ValueError."""
        target = tmp_path / "ledger.csv"
        bad_dict = {col: "" for col in LEDGER_CSV_COLUMNS}
        bad_dict["extra_column"] = "unexpected"
        with patch("scripts.ingest_sales._row_to_csv_dict", return_value=bad_dict):
            with pytest.raises(LedgerWriteFailed):
                atomic_write_csv(target, [_SAMPLE_ROW])

    def test_extra_key_leaves_no_target(self, tmp_path):
        """Target must not exist after schema violation during write."""
        target = tmp_path / "ledger.csv"
        bad_dict = {col: "" for col in LEDGER_CSV_COLUMNS}
        bad_dict["extra_column"] = "unexpected"
        with patch("scripts.ingest_sales._row_to_csv_dict", return_value=bad_dict):
            with pytest.raises(LedgerWriteFailed):
                atomic_write_csv(target, [_SAMPLE_ROW])
        assert not target.exists()


# ─── m2: float formatting ─────────────────────────────────────────────


class TestFloatFormatting:
    def test_buy_price_has_two_decimal_places(self, tmp_path):
        """buy_price=1234.5 writes as '1234.50', not '1234.5'."""
        target = tmp_path / "ledger.csv"
        row = LedgerRow(
            stock_id="TEST",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Rolex",
            reference="126300",
            account="NR",
            buy_price=1234.5,
            sell_price=1500.0,
        )
        atomic_write_csv(target, [row])
        with open(target, newline="", encoding="utf-8") as f:
            content = f.read()
        assert "1234.50" in content
        assert "1500.00" in content

    def test_round_trip_price_with_one_decimal(self, tmp_path):
        """Confirm DictReader reads back the formatted value."""
        target = tmp_path / "ledger.csv"
        row = LedgerRow(
            stock_id="TEST",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.5,
            sell_price=3200.9,
        )
        atomic_write_csv(target, [row])
        with open(target, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["buy_price"] == "2750.50"
        assert rows[0]["sell_price"] == "3200.90"
