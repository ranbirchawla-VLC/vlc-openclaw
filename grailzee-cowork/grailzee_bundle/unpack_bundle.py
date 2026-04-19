"""INBOUND bundle handler.

Validates a ``.zip`` returned from a Chat strategy session and, only after
every validation passes, atomically writes the contained planning
artifacts back into ``<grailzee_root>/state/``.

Roles (whitelist)
-----------------
- ``cycle_focus``           → state/cycle_focus.json
- ``monthly_goals``         → state/monthly_goals.json
- ``quarterly_allocation``  → state/quarterly_allocation.json

Any other role in the manifest triggers rejection.

Validation sequence (all run before any write)
---------------------------------------------
1. ``manifest.json`` present.
2. Manifest parses as JSON and has ``manifest_version == 1``.
3. ``bundle_kind == "inbound"``.
4. ``cycle_id`` matches the current cache's cycle_id.
5. Every ``manifest.files`` entry has a role in the whitelist.
6. Zip contains no symlinks (checked via ``ZipInfo.external_attr`` S_IFLNK bits).
7. No arcname escapes the archive: no absolute paths, no ``..`` components,
   no backslashes or drive prefixes.
8. Each manifest file's declared ``sha256`` + ``size_bytes`` matches the
   actual archive member bytes; no archive member exists outside the
   manifest (excluding ``manifest.json`` itself).

Atomic two-phase commit
-----------------------
1. Read all payload bytes into memory (after validation).
2. Snapshot existing target files to ``<target>.prior.<pid>``.
3. Write each new payload to ``<target>.tmp.<pid>`` then atomically
   ``Path.replace()`` over the live target.
4. On any exception during step 3, restore every completed replace from
   the corresponding ``.prior.<pid>`` snapshot, then re-raise.
5. On success, remove all snapshots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
EXPECTED_BUNDLE_KIND = "inbound"

ROLE_TO_TARGET: dict[str, str] = {
    "cycle_focus": "cycle_focus.json",
    "monthly_goals": "monthly_goals.json",
    "quarterly_allocation": "quarterly_allocation.json",
}


class BundleValidationError(ValueError):
    """Raised when an inbound bundle fails any validation rule."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    """True iff this zip entry's POSIX mode bits indicate a symlink."""
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _is_unsafe_arcname(name: str) -> bool:
    """Reject absolute paths, drive prefixes, backslashes, and `..`
    components. Arcnames must be plain relative POSIX-style paths."""
    if not name:
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if "\\" in name:
        return True
    # Drive-letter prefix on Windows-style paths ("C:")
    if len(name) >= 2 and name[1] == ":":
        return True
    parts = name.split("/")
    return any(part == ".." for part in parts)


def _load_current_cycle_id(state_dir: Path) -> str:
    cache_path = state_dir / "analysis_cache.json"
    if not cache_path.exists():
        raise BundleValidationError(
            f"Current analysis cache missing at {cache_path}; cannot verify cycle_id"
        )
    cache = json.loads(cache_path.read_text())
    cycle_id = cache.get("cycle_id") if isinstance(cache, dict) else None
    if not cycle_id:
        raise BundleValidationError(
            f"Current analysis cache at {cache_path} has no cycle_id"
        )
    return cycle_id


def _validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise BundleValidationError("manifest.json is not a JSON object")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise BundleValidationError(
            f"Unsupported manifest_version: {manifest.get('manifest_version')!r} "
            f"(expected {MANIFEST_VERSION})"
        )
    if manifest.get("bundle_kind") != EXPECTED_BUNDLE_KIND:
        raise BundleValidationError(
            f"Expected bundle_kind='{EXPECTED_BUNDLE_KIND}', got "
            f"{manifest.get('bundle_kind')!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BundleValidationError(
            "manifest.files is absent, empty, or not a list"
        )
    for entry in files:
        if not isinstance(entry, dict):
            raise BundleValidationError("manifest.files contains a non-object entry")
        for key in ("path", "role", "sha256", "size_bytes"):
            if key not in entry:
                raise BundleValidationError(
                    f"manifest.files entry missing required key {key!r}"
                )
        if entry["role"] not in ROLE_TO_TARGET:
            raise BundleValidationError(
                f"manifest.files entry has non-whitelisted role {entry['role']!r}; "
                f"allowed: {sorted(ROLE_TO_TARGET)}"
            )
    return manifest


def _validate_bundle(
    zip_path: Path, *, current_cycle_id: str | None
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Run all 8 validation rules. Return (manifest, role_to_bytes)."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Inbound bundle not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Rule 6: symlink rejection — first pass over infolist
        for info in zf.infolist():
            if _is_symlink_entry(info):
                raise BundleValidationError(
                    f"Symlink zip entry rejected: {info.filename!r}"
                )
            # Rule 7: arcname safety
            if _is_unsafe_arcname(info.filename):
                raise BundleValidationError(
                    f"Unsafe arcname rejected: {info.filename!r}"
                )

        # Rule 1: manifest present
        try:
            manifest_bytes = zf.read("manifest.json")
        except KeyError as exc:
            raise BundleValidationError("manifest.json missing from bundle") from exc

        # Rule 2: manifest parses as JSON
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError(
                f"manifest.json is not valid JSON: {exc}"
            ) from exc

        # Rule 2/3/5: manifest shape + version + bundle_kind + roles
        _validate_manifest(manifest)

        # Rule 4: cycle_id alignment
        if current_cycle_id is not None:
            if manifest.get("cycle_id") != current_cycle_id:
                raise BundleValidationError(
                    f"Bundle cycle_id {manifest.get('cycle_id')!r} does not match "
                    f"current cache cycle_id {current_cycle_id!r}"
                )

        # Rule 8: each manifest file present + hash + size match; no extraneous members
        manifest_paths = {entry["path"] for entry in manifest["files"]}
        archive_paths = {info.filename for info in zf.infolist()} - {"manifest.json"}
        extraneous = archive_paths - manifest_paths
        if extraneous:
            raise BundleValidationError(
                f"Archive contains entries not listed in manifest: {sorted(extraneous)!r}"
            )
        missing = manifest_paths - archive_paths
        if missing:
            raise BundleValidationError(
                f"Manifest lists entries missing from archive: {sorted(missing)!r}"
            )

        role_to_bytes: dict[str, bytes] = {}
        for entry in manifest["files"]:
            data = zf.read(entry["path"])
            if len(data) != entry["size_bytes"]:
                raise BundleValidationError(
                    f"Size mismatch for {entry['path']!r}: declared "
                    f"{entry['size_bytes']}, actual {len(data)}"
                )
            if _sha256(data) != entry["sha256"]:
                raise BundleValidationError(
                    f"sha256 mismatch for {entry['path']!r}"
                )
            role_to_bytes[entry["role"]] = data

    return manifest, role_to_bytes


def _atomic_write_targets(
    state_dir: Path, role_to_bytes: dict[str, bytes]
) -> list[str]:
    """Two-phase atomic commit of role payloads into state_dir. Returns the
    list of role names successfully written (all-or-nothing on exception).
    """
    pid_tag = f".{os.getpid()}"
    targets: list[tuple[str, Path, Path, Path, bytes]] = []
    # (role, target_path, tmp_path, prior_path, data)
    for role, data in role_to_bytes.items():
        filename = ROLE_TO_TARGET[role]
        target = state_dir / filename
        targets.append(
            (
                role,
                target,
                target.with_suffix(target.suffix + ".tmp" + pid_tag),
                target.with_suffix(target.suffix + ".prior" + pid_tag),
                data,
            )
        )

    state_dir.mkdir(parents=True, exist_ok=True)
    # Phase 1: write tmps
    for _role, _target, tmp, _prior, data in targets:
        tmp.write_bytes(data)

    # Phase 2: snapshot existing targets
    for _role, target, _tmp, prior, _data in targets:
        if target.exists():
            prior.write_bytes(target.read_bytes())

    # Phase 3: atomic replace, with rollback on any failure
    committed: list[tuple[Path, Path]] = []  # (target, prior)
    try:
        for _role, target, tmp, prior, _data in targets:
            tmp.replace(target)
            committed.append((target, prior))
    except Exception:
        for target, prior in committed:
            if prior.exists():
                prior.replace(target)
            else:
                if target.exists():
                    target.unlink()
        for _role, _target, tmp, prior, _data in targets:
            if tmp.exists():
                tmp.unlink()
            if prior.exists():
                prior.unlink()
        raise

    # Cleanup: remove snapshots on success
    for _role, _target, _tmp, prior, _data in targets:
        if prior.exists():
            prior.unlink()

    return [role for role, *_rest in targets]


def unpack_inbound_bundle(
    zip_path: Path,
    grailzee_root: Path,
    *,
    strict_cycle_id: bool = True,
) -> dict[str, Any]:
    """Validate and unpack an INBOUND bundle into ``<grailzee_root>/state/``.

    Parameters
    ----------
    zip_path:
        Path to the inbound ``.zip``.
    grailzee_root:
        Path to the GrailzeeData tree (parent of ``state/``).
    strict_cycle_id:
        When True (default), reject if bundle cycle_id does not match
        the current cache's cycle_id. Primarily relaxed for tests that
        exercise validation without setting up a cache.

    Returns
    -------
    A summary dict: ``{"cycle_id", "roles_written", "source"}``.

    Raises
    ------
    BundleValidationError
        Any of the 8 validation rules failed. No files written.
    FileNotFoundError
        ``zip_path`` does not exist.
    """
    grailzee_root = Path(grailzee_root)
    state_dir = grailzee_root / "state"

    current_cycle_id: str | None = None
    if strict_cycle_id:
        current_cycle_id = _load_current_cycle_id(state_dir)

    manifest, role_to_bytes = _validate_bundle(
        Path(zip_path), current_cycle_id=current_cycle_id
    )

    roles_written = _atomic_write_targets(state_dir, role_to_bytes)
    return {
        "cycle_id": manifest["cycle_id"],
        "roles_written": sorted(roles_written),
        "source": manifest.get("source", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unpack an INBOUND Grailzee strategy-session bundle into state/."
    )
    parser.add_argument(
        "bundle",
        help="Path to the inbound .zip.",
    )
    parser.add_argument(
        "--grailzee-root",
        required=True,
        help="Path to the GrailzeeData tree (parent of state/).",
    )
    parser.add_argument(
        "--allow-cycle-mismatch",
        action="store_true",
        help="Skip the cycle_id equality check (advanced; use only when the "
        "agent has not yet rolled to the bundle's cycle).",
    )
    args = parser.parse_args(argv)
    try:
        result = unpack_inbound_bundle(
            Path(args.bundle),
            Path(args.grailzee_root),
            strict_cycle_id=not args.allow_cycle_mismatch,
        )
    except (BundleValidationError, FileNotFoundError) as exc:
        print(f"Unpack failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
