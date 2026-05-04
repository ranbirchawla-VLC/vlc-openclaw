"""One-shot migration: gtd-workspace/storage/ → ~/agent_data/gtd/ranbir/

Usage:
    python migrate_storage.py            # live run
    python migrate_storage.py --dry-run  # report only, no mutation

Output: plugin JSON to stdout — {"ok": true, "data": {...}} or {"ok": false, "error": "..."}.

An empty pre-existing destination is treated the same as a missing destination — the migration
proceeds. This is intentional: the operator may have pre-created the path via launchd or
mkdir -p. Only a non-empty destination triggers the refusal or sentinel-recovery check.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

_DEFAULT_SOURCE: Path = Path(__file__).resolve().parent.parent / "storage"
_DEFAULT_DEST: Path = Path.home() / "agent_data" / "gtd" / "ranbir"
_SENTINEL: str = ".migration_complete"


def _hash_tree(root: Path, skip: frozenset[str] = frozenset()) -> tuple[str, int, int]:
    """SHA-256 over all file contents sorted by relative path. Returns (hex, file_count, byte_count).

    Files whose names are in `skip` are excluded from hash and counts — used to omit the
    sentinel file when re-verifying a destination that already has one.
    """
    h = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in skip:
            data = p.read_bytes()
            h.update(str(p.relative_to(root)).encode())
            h.update(data)
            file_count += 1
            byte_count += len(data)
    return h.hexdigest(), file_count, byte_count


def _ok(data: dict[str, Any]) -> None:
    print(json.dumps({"ok": True, "data": data}))


def _err(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate GTD storage to agent_data path.")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without mutating disk.")
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE, help="Override source path (tests only).")
    parser.add_argument("--dest", type=Path, default=_DEFAULT_DEST, help="Override destination path (tests only).")
    args = parser.parse_args()

    source: Path = args.source
    dest: Path = args.dest
    parked: Path = source.parent / (source.name + ".migrated")

    if not source.exists():
        if parked.exists():
            _err(f"already migrated: source '{source}' is missing but parked at '{parked}'")
        else:
            _err(f"source not found: '{source}' does not exist")

    # Non-empty dest: check for sentinel before refusing.
    if dest.exists() and any(dest.iterdir()):
        sentinel_path = dest / _SENTINEL
        if not sentinel_path.exists():
            _err(f"destination not empty: '{dest}' already contains files; refusing to overwrite")

        # Sentinel present: copy completed but rename did not. Verify integrity and recover.
        try:
            sentinel = json.loads(sentinel_path.read_text())
            recorded_hash: str = sentinel["hash"]
        except (json.JSONDecodeError, KeyError) as exc:
            _err(f"sentinel file at '{sentinel_path}' is malformed: {exc}; inspect manually")

        current_hash, recovered_files, recovered_bytes = _hash_tree(dest, skip=frozenset({_SENTINEL}))
        if current_hash != recorded_hash:
            _err(
                f"destination integrity check failed: recorded hash {recorded_hash[:12]}... "
                f"does not match current hash {current_hash[:12]}...; inspect manually"
            )

        # Hash matches — complete the interrupted rename.
        shutil.move(source, parked)  # handles cross-device moves that the rename syscall doesn't
        _ok({
            "source_parked_at": str(parked),
            "destination": str(dest),
            "files_moved": recovered_files,
            "bytes_moved": recovered_bytes,
            "recovery_status": "recovered interrupted rename",
            "next_step": (
                f"Set GTD_STORAGE_ROOT={dest} on the gateway process (launchd plist), "
                f"restart the gateway, smoke-test a GTD action through Telegram, "
                f"then delete the parked source: rm -rf '{parked}'"
            ),
        })
        return

    expected_hash, src_files, src_bytes = _hash_tree(source)

    if args.dry_run:
        _ok({
            "dry_run": True,
            "source": str(source),
            "destination": str(dest),
            "files_to_move": src_files,
            "bytes_to_move": src_bytes,
            "park_location": str(parked),
        })
        return

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, dirs_exist_ok=True)

    actual_hash, dst_files, dst_bytes = _hash_tree(dest)
    if actual_hash != expected_hash:
        _err(
            f"verification failed: hash mismatch after copy "
            f"(expected {expected_hash[:12]}..., got {actual_hash[:12]}...); "
            f"destination left in place at '{dest}' for inspection"
        )

    sentinel_path = dest / _SENTINEL
    sentinel_path.write_text(json.dumps({
        "hash": expected_hash,
        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }))

    shutil.move(source, parked)  # handles cross-device moves that the rename syscall doesn't

    _ok({
        "source_parked_at": str(parked),
        "destination": str(dest),
        "files_moved": dst_files,
        "bytes_moved": dst_bytes,
        "next_step": (
            f"Set GTD_STORAGE_ROOT={dest} on the gateway process (launchd plist), "
            f"restart the gateway, smoke-test a GTD action through Telegram, "
            f"then delete the parked source: rm -rf '{parked}'"
        ),
    })


if __name__ == "__main__":
    main()
