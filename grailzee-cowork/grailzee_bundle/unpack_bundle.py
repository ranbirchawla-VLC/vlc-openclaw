"""INBOUND bundle handler.

Accepts EITHER a ``.zip`` bundle (Phase 24a format) OR a
``strategy_output.json`` payload (Phase 24b format, produced by the
grailzee-strategy Chat skill). Dispatch is by file extension with a
magic-byte sanity check.

For ``.zip``: validates the bundle and, only after every validation
passes, atomically writes the contained planning artifacts back into
``<grailzee_root>/state/``.

For ``.json``: validates the payload against the strategy_output_v1
schema, then atomically writes each non-null decision section to
``state/`` using the same two-phase commit as the .zip path.

Roles
-----
``.zip`` whitelist (``ZIP_WHITELIST``, 3 roles — Phase 24a contract):
- ``cycle_focus``           → state/cycle_focus.json
- ``monthly_goals``         → state/monthly_goals.json
- ``quarterly_allocation``  → state/quarterly_allocation.json

``.json`` whitelist (``JSON_WHITELIST``, 9 roles) adds 6 config files:
signal_thresholds, scoring_thresholds, momentum_thresholds,
window_config, premium_config, margin_config.

The two whitelists are kept disjoint at the validation layer so a
hostile ``.zip`` cannot smuggle a config_update-shaped payload through
the Phase 24a trust boundary.

Validation sequence (all run before any write)
---------------------------------------------
1. ``manifest.json`` present and under ``MAX_MANIFEST_BYTES``.
2. Manifest parses as JSON and has ``manifest_version == 1``.
3. ``bundle_kind == "inbound"``.
4. ``cycle_id`` matches the current cache's cycle_id.
5. Every ``manifest.files`` entry has a role in the whitelist, and the
   file count is under ``MAX_MANIFEST_FILES``.
6. Zip contains no symlinks (checked via ``ZipInfo.external_attr`` S_IFLNK bits).
7. No arcname escapes the archive (absolute paths, ``..``, backslashes,
   drive prefixes, NUL bytes), for both ``ZipInfo.filename`` and the
   ``path`` field of every manifest entry.
8. Each manifest file's declared ``sha256`` + ``size_bytes`` matches the
   actual archive member bytes; per-member and total uncompressed sizes
   are capped (zip-bomb defense); no duplicate arcnames; no archive
   member exists outside the manifest (excluding ``manifest.json``).

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

# Phase 24a trust boundary: only these three roles may appear in a ``.zip``
# inbound bundle. Enforced by ``_validate_manifest``.
ZIP_WHITELIST: dict[str, str] = {
    "cycle_focus": "cycle_focus.json",
    "monthly_goals": "monthly_goals.json",
    "quarterly_allocation": "quarterly_allocation.json",
}

# Phase 24b ``.json`` path also accepts the six D5 config files as
# replacement payloads. Never merged with ZIP_WHITELIST at validation time.
_CONFIG_SUB_FILES: dict[str, str] = {
    "signal_thresholds": "signal_thresholds.json",
    "scoring_thresholds": "scoring_thresholds.json",
    "momentum_thresholds": "momentum_thresholds.json",
    "window_config": "window_config.json",
    "premium_config": "premium_config.json",
    "margin_config": "margin_config.json",
}
JSON_WHITELIST: dict[str, str] = {**ZIP_WHITELIST, **_CONFIG_SUB_FILES}

# Union map; used only by ``_atomic_write_targets`` to look up filenames.
# Trust enforcement happens before this point (either in _validate_manifest
# for .zip path, or in validate_strategy_output for .json path), so exposing
# all nine filename mappings here does not widen the trust boundary.
ROLE_TO_TARGET: dict[str, str] = JSON_WHITELIST

# Defenses against hostile bundles. Inbound role payloads are small JSON
# documents; a declared (or uncompressed) size larger than this indicates
# tampering or a zip-bomb. Ceilings are intentionally generous relative to
# realistic planning artifacts.
MAX_MANIFEST_BYTES = 1 * 1024 * 1024         # 1 MB
MAX_MEMBER_BYTES = 4 * 1024 * 1024           # 4 MB per member
MAX_TOTAL_DECOMPRESSED_BYTES = 16 * 1024 * 1024  # 16 MB aggregate
MAX_MANIFEST_FILES = 16                      # whitelist only has 3 roles


class BundleValidationError(ValueError):
    """Raised when an inbound bundle fails any validation rule."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    """True iff this zip entry's POSIX mode bits indicate a symlink."""
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _is_unsafe_arcname(name: str) -> bool:
    """Reject absolute paths, drive prefixes, backslashes, NUL bytes, and
    `..` components. Arcnames must be plain relative POSIX-style paths."""
    if not name:
        return True
    if "\x00" in name:
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
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
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
        if entry["role"] not in ZIP_WHITELIST:
            raise BundleValidationError(
                f"manifest.files entry has non-whitelisted role {entry['role']!r}; "
                f"allowed (.zip path): {sorted(ZIP_WHITELIST)}"
            )
    return manifest


def _validate_bundle(
    zip_path: Path, *, current_cycle_id: str | None
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Run all 8 validation rules. Return (manifest, role_to_bytes).

    All size-ceiling checks run against ``ZipInfo.file_size`` BEFORE any
    ``zf.read()`` decompression, so a zip-bomb is rejected without loading
    the payload into memory.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Inbound bundle not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()

        # Duplicate arcname rejection. Zip format allows duplicates; an
        # attacker can pair a manifest-matching member with a hostile
        # same-named twin, where zf.read() resolves to the last entry.
        name_counts: dict[str, int] = {}
        for info in infolist:
            name_counts[info.filename] = name_counts.get(info.filename, 0) + 1
        duplicates = [n for n, c in name_counts.items() if c > 1]
        if duplicates:
            raise BundleValidationError(
                f"Duplicate zip entries rejected: {sorted(duplicates)!r}"
            )

        # Rules 6 + 7 + per-member size ceiling, pre-read.
        total_declared = 0
        for info in infolist:
            if _is_symlink_entry(info):
                raise BundleValidationError(
                    f"Symlink zip entry rejected: {info.filename!r}"
                )
            if _is_unsafe_arcname(info.filename):
                raise BundleValidationError(
                    f"Unsafe arcname rejected: {info.filename!r}"
                )
            if info.file_size > MAX_MEMBER_BYTES:
                raise BundleValidationError(
                    f"Zip entry {info.filename!r} declares uncompressed size "
                    f"{info.file_size} exceeding per-member cap {MAX_MEMBER_BYTES}"
                )
            total_declared += info.file_size
        if total_declared > MAX_TOTAL_DECOMPRESSED_BYTES:
            raise BundleValidationError(
                f"Aggregate uncompressed size {total_declared} exceeds cap "
                f"{MAX_TOTAL_DECOMPRESSED_BYTES}"
            )

        # Rule 1: manifest present (and not over its own cap, before read).
        try:
            manifest_info = zf.getinfo("manifest.json")
        except KeyError as exc:
            raise BundleValidationError("manifest.json missing from bundle") from exc
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise BundleValidationError(
                f"manifest.json declares size {manifest_info.file_size} exceeding "
                f"cap {MAX_MANIFEST_BYTES}"
            )
        manifest_bytes = zf.read("manifest.json")

        # Rule 2: manifest parses as JSON.
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError(
                f"manifest.json is not valid JSON: {exc}"
            ) from exc

        # Rules 2/3/5: manifest shape + version + bundle_kind + roles.
        _validate_manifest(manifest)
        if len(manifest["files"]) > MAX_MANIFEST_FILES:
            raise BundleValidationError(
                f"manifest.files has {len(manifest['files'])} entries, "
                f"exceeding cap {MAX_MANIFEST_FILES}"
            )
        # Rule 7, continued: validate manifest-declared paths too.
        for entry in manifest["files"]:
            if _is_unsafe_arcname(entry["path"]):
                raise BundleValidationError(
                    f"Unsafe path in manifest.files: {entry['path']!r}"
                )

        # Rule 4: cycle_id alignment.
        if current_cycle_id is not None:
            if manifest.get("cycle_id") != current_cycle_id:
                raise BundleValidationError(
                    f"Bundle cycle_id {manifest.get('cycle_id')!r} does not match "
                    f"current cache cycle_id {current_cycle_id!r}"
                )

        # Rule 8: each manifest file present + hash + size match; no extraneous members.
        manifest_paths = {entry["path"] for entry in manifest["files"]}
        archive_paths = {info.filename for info in infolist} - {"manifest.json"}
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
            # Read by ZipInfo (not name) so a same-named decoy added after
            # dedup cannot be substituted mid-read.
            info = zf.getinfo(entry["path"])
            if info.file_size != entry["size_bytes"]:
                raise BundleValidationError(
                    f"Size mismatch for {entry['path']!r}: declared "
                    f"{entry['size_bytes']}, zip header {info.file_size}"
                )
            data = zf.read(info)
            if len(data) != entry["size_bytes"]:
                raise BundleValidationError(
                    f"Decompressed size mismatch for {entry['path']!r}: declared "
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
    list of role names written.

    Contract: exception-atomic. On any exception during Phase 3 (replace),
    all successfully replaced targets are restored from snapshot. Not
    crash-atomic — a process kill between phases can leave .tmp / .prior
    siblings on disk. To defend against pid reuse from a prior crashed
    run, this function refuses to start if ``.tmp.<pid>`` or
    ``.prior.<pid>`` siblings already exist for any target.

    Snapshots use ``os.link()`` (hardlink) rather than a bytes copy: it is
    instant, atomic, and fails loudly if the snapshot path already
    exists. Subsequent ``os.replace()`` on the live target replaces the
    directory entry's inode — the hardlink still references the prior
    inode until we unlink it on success.
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

    # Pre-check: refuse to run if any pid-tagged sibling already exists.
    # Protects against a crashed prior invocation whose process used the
    # same pid (pid reuse is uncommon but possible on long-lived hosts).
    for _role, _target, tmp, prior, _data in targets:
        if tmp.exists() or prior.exists():
            raise BundleValidationError(
                f"Refusing to start: leftover pid-tagged sibling {tmp if tmp.exists() else prior}. "
                f"Inspect state_dir for crashed-run artifacts and remove them manually."
            )

    # Phase 1: write tmps.
    for _role, _target, tmp, _prior, data in targets:
        tmp.write_bytes(data)

    # Phase 2: snapshot existing targets via hardlink (atomic; fails if
    # prior already exists).
    for _role, target, _tmp, prior, _data in targets:
        if target.exists():
            os.link(target, prior)

    # Phase 3: atomic replace, with rollback on any failure.
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

    # Success cleanup.
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


def _detect_input_type(path: Path) -> str:
    """Return ``"zip"`` or ``"json"`` based on extension + magic-byte probe.

    Raises ``BundleValidationError`` for unsupported extensions or when the
    file's first bytes contradict its extension (``.zip`` without a PK
    signature, ``.json`` without a leading ``{`` or ``[``). Called before
    any parse/validate work so obviously-wrong inputs fail fast.
    """
    suffix = path.suffix.lower()
    if not path.exists():
        raise FileNotFoundError(f"Inbound file not found: {path}")

    # Read only the bytes needed for the magic probe. A full read_bytes()
    # would slurp up to MAX_TOTAL_DECOMPRESSED_BYTES for a legitimate zip
    # just to check the 4-byte PK signature.
    match suffix:
        case ".zip":
            with open(path, "rb") as f:
                head = f.read(4)
            if not head.startswith(b"PK"):
                raise BundleValidationError(
                    f"{path.name} has .zip extension but content is not a zip archive "
                    f"(magic bytes {head!r})"
                )
            return "zip"
        case ".json":
            with open(path, "rb") as f:
                head = f.read(64).lstrip()
            if not head or head[:1] not in (b"{", b"["):
                raise BundleValidationError(
                    f"{path.name} has .json extension but content does not look like "
                    f"JSON (first non-whitespace bytes: {head[:16]!r})"
                )
            return "json"
        case _:
            raise BundleValidationError(
                f"Unsupported input extension {suffix!r}; expected .zip or .json "
                f"(path: {path})"
            )


def _strategy_output_to_role_bytes(payload: dict[str, Any]) -> dict[str, bytes]:
    """Turn a validated strategy_output payload into role→bytes for the
    atomic writer. Skips any decision section that is null.

    Each non-null decision becomes one file entry. ``config_updates``
    expands: each non-null sub-config becomes its own entry. Every payload
    is emitted as indent=2 JSON with a trailing newline (matching
    grailzee-eval's write conventions for state files).
    """
    decisions = payload["decisions"]
    role_to_bytes: dict[str, bytes] = {}

    def _emit(role: str, content: Any) -> None:
        role_to_bytes[role] = (json.dumps(content, indent=2) + "\n").encode("utf-8")

    if decisions["cycle_focus"] is not None:
        _emit("cycle_focus", decisions["cycle_focus"])
    if decisions["monthly_goals"] is not None:
        _emit("monthly_goals", decisions["monthly_goals"])
    if decisions["quarterly_allocation"] is not None:
        _emit("quarterly_allocation", decisions["quarterly_allocation"])
    if decisions["config_updates"] is not None:
        for sub_key in _CONFIG_SUB_FILES:
            sub_payload = decisions["config_updates"][sub_key]
            if sub_payload is not None:
                _emit(sub_key, sub_payload)

    return role_to_bytes


def _write_strategy_archive(
    payload: dict[str, Any], briefs_dir: Path
) -> tuple[list[str], list[dict[str, str]]]:
    """Best-effort write of the three archive artifacts to ``briefs_dir``.

    Files produced (names prefixed with the payload's ``cycle_id``):
      - ``<cycle_id>_strategy_output.json`` — indent=2 JSON of the
        validated payload (re-read later to audit what the strategy
        session actually handed off).
      - ``<cycle_id>_strategy_brief.xlsx`` — rendered via
        ``build_strategy_xlsx``.
      - ``<cycle_id>_strategy_brief.md`` — raw markdown from
        ``session_artifacts.cycle_brief_md``.

    Writes are independent. Any single failure is captured in the
    returned errors list (with the target file's basename) and the
    remaining writes still proceed. State writes are already committed
    upstream — the archive is an operator convenience and must never
    block or roll back the primary apply. Callers surface the error
    list to the operator so they can retry or fix the filesystem.
    """
    from grailzee_bundle.build_strategy_xlsx import build_strategy_xlsx

    cycle_id = payload["cycle_id"]
    files_written: list[str] = []
    errors: list[dict[str, str]] = []

    try:
        briefs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # If we can't even create the directory, no write can succeed.
        # Report a single directory-level failure and bail — three
        # identical "parent not found" errors would be noise.
        errors.append({"file": str(briefs_dir), "error": str(exc)})
        return files_written, errors

    json_path = briefs_dir / f"{cycle_id}_strategy_output.json"
    try:
        json_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        files_written.append(json_path.name)
    except OSError as exc:
        errors.append({"file": json_path.name, "error": str(exc)})

    xlsx_path = briefs_dir / f"{cycle_id}_strategy_brief.xlsx"
    try:
        build_strategy_xlsx(payload, xlsx_path)
        files_written.append(xlsx_path.name)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Best-effort archive: OSError (disk full / permission), plus
        # ValueError/KeyError/TypeError that openpyxl can surface on
        # malformed workbook state. State commit already landed
        # upstream — the operator sees this via archive_errors.
        errors.append({"file": xlsx_path.name, "error": str(exc)})

    md_path = briefs_dir / f"{cycle_id}_strategy_brief.md"
    try:
        md_path.write_text(
            payload["session_artifacts"]["cycle_brief_md"], encoding="utf-8"
        )
        files_written.append(md_path.name)
    except OSError as exc:
        errors.append({"file": md_path.name, "error": str(exc)})

    return files_written, errors


def apply_strategy_output(
    json_path: Path,
    grailzee_root: Path,
    *,
    strict_cycle_id: bool = True,
    write_archive: bool = True,
) -> dict[str, Any]:
    """Validate and apply a strategy_output.json payload.

    Pipeline:
    1. Read + parse JSON (fail-loud on syntax error).
    2. Hand-rolled schema validation.
    3. cycle_id gate (same rule #4 as .zip path; toggle via ``strict_cycle_id``).
    4. Build role→bytes from decisions; every non-null decision section
       becomes one ``state/<name>.json`` write. Empty writes (all decisions
       null) are blocked upstream by the validator.
    5. Atomic two-phase commit via ``_atomic_write_targets``.
    6. Best-effort archive writes (XLSX + MD + JSON) to
       ``<grailzee_root>/output/briefs/``. Archive failures do NOT
       roll back state writes — the archive is an operator-facing
       convenience; state is the source of truth.

    Returns a summary dict: ``{cycle_id, session_mode, roles_written,
    source, archive_files_written, archive_errors, payload}``.
    ``payload`` is the validated dict, returned so callers (e.g. CLI)
    can avoid re-reading the file.

    Raises
    ------
    StrategyOutputValidationError
        Schema failed.
    BundleValidationError
        cycle_id mismatch.
    FileNotFoundError
        ``json_path`` missing.
    """
    from grailzee_bundle.strategy_schema import (
        StrategyOutputValidationError,
        validate_strategy_output,
    )

    grailzee_root = Path(grailzee_root)
    state_dir = grailzee_root / "state"
    briefs_dir = grailzee_root / "output" / "briefs"
    json_path = Path(json_path)

    if not json_path.exists():
        raise FileNotFoundError(f"strategy_output.json not found: {json_path}")

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BundleValidationError(
            f"strategy_output.json is not valid JSON: {exc}"
        ) from exc

    try:
        validate_strategy_output(payload)
    except StrategyOutputValidationError as exc:
        # Normalize to BundleValidationError so callers can catch a single
        # exception type across .zip and .json paths.
        raise BundleValidationError(f"strategy_output schema: {exc}") from exc

    if strict_cycle_id:
        current_cycle_id = _load_current_cycle_id(state_dir)
        if payload["cycle_id"] != current_cycle_id:
            raise BundleValidationError(
                f"Bundle cycle_id {payload['cycle_id']!r} does not match "
                f"current cache cycle_id {current_cycle_id!r}"
            )

    role_to_bytes = _strategy_output_to_role_bytes(payload)
    roles_written = _atomic_write_targets(state_dir, role_to_bytes)

    archive_files_written: list[str] = []
    archive_errors: list[dict[str, str]] = []
    if write_archive:
        archive_files_written, archive_errors = _write_strategy_archive(
            payload, briefs_dir
        )

    return {
        "cycle_id": payload["cycle_id"],
        "session_mode": payload["session_mode"],
        "roles_written": sorted(roles_written),
        "source": payload["produced_by"],
        "archive_files_written": archive_files_written,
        "archive_errors": archive_errors,
        "payload": payload,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply an INBOUND Grailzee strategy handoff into state/. "
            "Accepts either a .zip bundle (Phase 24a) or a "
            "strategy_output.json payload (Phase 24b)."
        )
    )
    parser.add_argument(
        "bundle",
        help="Path to the inbound .zip OR strategy_output .json.",
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
    bundle_path = Path(args.bundle)
    try:
        kind = _detect_input_type(bundle_path)
        match kind:
            case "zip":
                result = unpack_inbound_bundle(
                    bundle_path,
                    Path(args.grailzee_root),
                    strict_cycle_id=not args.allow_cycle_mismatch,
                )
            case "json":
                result = apply_strategy_output(
                    bundle_path,
                    Path(args.grailzee_root),
                    strict_cycle_id=not args.allow_cycle_mismatch,
                )
                # Don't print the full payload back on the CLI; it's already on disk.
                result = {k: v for k, v in result.items() if k != "payload"}
            case _:
                # _detect_input_type only returns "zip" | "json"; this is
                # a defensive arm that would fire only if that contract drifts.
                raise BundleValidationError(
                    f"Internal: unhandled input kind {kind!r}"
                )
    except (BundleValidationError, FileNotFoundError) as exc:
        print(f"Unpack failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
