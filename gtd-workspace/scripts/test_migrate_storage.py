"""Tests for migrate_storage.py.

Path overrides via --source / --dest CLI args. Tests call the script
as a subprocess so real I/O failure modes surface (no mocked filesystem).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent / "migrate_storage.py"


def run_script(source: Path, dest: Path, dry_run: bool = False) -> tuple[int, dict[str, Any]]:
    cmd = [sys.executable, str(SCRIPT), "--source", str(source), "--dest", str(dest)]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, json.loads(result.stdout)


def seed_tree(root: Path) -> tuple[int, int]:
    """Create a nested tree; return (file_count, total_byte_count)."""
    entries: dict[Path, bytes] = {
        root / "top.jsonl": b'{"id": 0}\n',
        root / "dir_a" / "a1.jsonl": b'{"id": 1}\n',
        root / "dir_a" / "a2.txt": b"hello\n",
        root / "dir_b" / "dir_c" / "deep.jsonl": b'{"id": 2}\n',
    }
    for path, data in entries.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(entries), sum(len(d) for d in entries.values())


# ---------------------------------------------------------------------------
# Test 1: happy path
# ---------------------------------------------------------------------------

def test_happy_path(tmp_path: Path) -> None:
    """Guards against: silent data loss or incomplete copy on live migration."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    parked = tmp_path / "storage.migrated"
    n_files, n_bytes = seed_tree(source)

    code, result = run_script(source, dest)

    assert code == 0
    assert result["ok"] is True
    data = result["data"]
    assert data["files_moved"] == n_files
    assert data["bytes_moved"] == n_bytes
    assert data["source_parked_at"] == str(parked)
    assert data["destination"] == str(dest)
    assert not source.exists(), "source must be renamed after migration"
    assert parked.exists(), "parked directory must exist"
    assert (dest / "top.jsonl").read_bytes() == b'{"id": 0}\n'
    assert (dest / "dir_b" / "dir_c" / "deep.jsonl").read_bytes() == b'{"id": 2}\n'
    sentinel = json.loads((dest / ".migration_complete").read_text())
    assert "hash" in sentinel and "completed_at" in sentinel


# ---------------------------------------------------------------------------
# Test 2: dry run
# ---------------------------------------------------------------------------

def test_dry_run(tmp_path: Path) -> None:
    """Guards against: dry-run accidentally mutating disk state."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    n_files, n_bytes = seed_tree(source)

    code, result = run_script(source, dest, dry_run=True)

    assert code == 0
    assert result["ok"] is True
    data = result["data"]
    assert data["dry_run"] is True
    assert data["files_to_move"] == n_files
    assert data["bytes_to_move"] == n_bytes
    assert data["source"] == str(source)
    assert data["destination"] == str(dest)
    assert source.exists(), "dry-run must not touch source"
    assert not dest.exists(), "dry-run must not create destination"


# ---------------------------------------------------------------------------
# Test 3: refusal — destination not empty
# ---------------------------------------------------------------------------

def test_refusal_dest_not_empty(tmp_path: Path) -> None:
    """Guards against: overwriting live destination data during re-run."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    seed_tree(source)
    dest.mkdir()
    (dest / "existing.txt").write_text("preexisting")

    code, result = run_script(source, dest)

    assert code == 1
    assert result["ok"] is False
    assert "destination not empty" in result["error"]
    assert source.exists(), "source must be untouched on refusal"
    assert (dest / "existing.txt").read_text() == "preexisting"


# ---------------------------------------------------------------------------
# Test 4: refusal — source missing, no parked
# ---------------------------------------------------------------------------

def test_refusal_source_missing_no_parked(tmp_path: Path) -> None:
    """Guards against: confusing error when storage dir was never created."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"

    code, result = run_script(source, dest)

    assert code == 1
    assert result["ok"] is False
    assert "source not found" in result["error"]


# ---------------------------------------------------------------------------
# Test 5: refusal — parked exists, source missing
# ---------------------------------------------------------------------------

def test_refusal_already_migrated(tmp_path: Path) -> None:
    """Guards against: re-running migrate after successful migration and re-parked source."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    parked = tmp_path / "storage.migrated"
    parked.mkdir()
    (parked / "a.jsonl").write_bytes(b'{"id": 0}\n')

    code, result = run_script(source, dest)

    assert code == 1
    assert result["ok"] is False
    assert "already migrated" in result["error"]


# ---------------------------------------------------------------------------
# Test 6: idempotent
# ---------------------------------------------------------------------------

def test_idempotent(tmp_path: Path) -> None:
    """Guards against: second invocation corrupting a completed migration."""
    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    seed_tree(source)

    code1, result1 = run_script(source, dest)
    assert code1 == 0
    assert result1["ok"] is True

    snapshot = {
        str(p.relative_to(dest)): p.read_bytes()
        for p in dest.rglob("*") if p.is_file()
    }

    code2, result2 = run_script(source, dest)
    assert code2 == 1
    assert result2["ok"] is False

    current = {
        str(p.relative_to(dest)): p.read_bytes()
        for p in dest.rglob("*") if p.is_file()
    }
    assert snapshot == current, "destination must be byte-for-byte unchanged after refused second run"


# ---------------------------------------------------------------------------
# Test 7: recursive walk counts all depths
# ---------------------------------------------------------------------------

def test_b1_recovery_interrupted_rename(tmp_path: Path) -> None:
    """Guards against: no recovery when copytree succeeded but rename(parked) failed.

    Seeds the interrupted state manually: dest populated + sentinel written, source still
    present, parked absent. Script must complete the rename and exit ok.

    TDD: confirmed to FAIL against pre-fix code (old code sees non-empty dest, has no
    sentinel check, refuses with 'destination not empty').
    """
    import hashlib

    source = tmp_path / "storage"
    dest = tmp_path / "dest"
    parked = tmp_path / "storage.migrated"
    seed_tree(source)

    # Simulate: copytree done, sentinel written, but rename did not run.
    shutil.copytree(str(source), str(dest))

    # Compute the hash the script would have written.
    h = hashlib.sha256()
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            h.update(str(p.relative_to(dest)).encode())
            h.update(data)
    expected_hash = h.hexdigest()

    (dest / ".migration_complete").write_text(
        json.dumps({"hash": expected_hash, "completed_at": "2026-05-02T00:00:00+00:00"})
    )

    assert source.exists(), "source must still be present to simulate interrupted rename"
    assert not parked.exists(), "parked must not exist to simulate interrupted rename"

    code, result = run_script(source, dest)

    assert code == 0, f"recovery run failed: {result}"
    assert result["ok"] is True
    data = result["data"]
    assert data.get("recovery_status") == "recovered interrupted rename"
    assert not source.exists(), "source must be parked after recovery"
    assert parked.exists(), "parked must exist after recovery"


def test_recursive_walk_counts_all_depths(tmp_path: Path) -> None:
    """Guards against: _count_tree using iterdir() instead of rglob(), which would
    only see the top level and miss nested files.

    TDD note: this test was confirmed to FAIL against a broken implementation that
    uses iterdir() (which counts only top-level entries). See Gate 1 report in
    sub-step-Z-migration.md for the failure transcript.
    """
    source = tmp_path / "storage"
    dest = tmp_path / "dest"

    source.mkdir()
    (source / "top.jsonl").write_bytes(b'{"id": 0}\n')

    level1 = source / "a"
    level1.mkdir()
    (level1 / "lvl1.jsonl").write_bytes(b'{"id": 1}\n')

    level2 = level1 / "b"
    level2.mkdir()
    (level2 / "lvl2.jsonl").write_bytes(b'{"id": 2}\n')

    level3 = level2 / "c"
    level3.mkdir()
    (level3 / "lvl3.jsonl").write_bytes(b'{"id": 3}\n')

    expected_files = 4
    expected_bytes = 4 * len(b'{"id": 0}\n')

    code, result = run_script(source, dest)

    assert code == 0, f"script failed: {result}"
    data = result["data"]
    assert data["files_moved"] == expected_files, (
        f"Expected {expected_files} files but got {data['files_moved']}; "
        "likely _count_tree uses iterdir() instead of rglob()"
    )
    assert data["bytes_moved"] == expected_bytes
