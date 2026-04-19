"""Tests for grailzee_bundle.unpack_bundle (INBOUND)."""

from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from grailzee_bundle.unpack_bundle import (
    BundleValidationError,
    _is_symlink_entry,
    _is_unsafe_arcname,
    unpack_inbound_bundle,
)
from _fixtures import (
    FAKE_CYCLE_ID,
    FAKE_PRIOR_CYCLE_ID,
    build_fake_grailzee_tree,
    build_inbound_bundle_zip,
)

# ─── happy path ──────────────────────────────────────────────────────


def test_happy_path_writes_all_three_roles(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "inbound.zip",
        cycle_id=FAKE_CYCLE_ID,
        payloads={
            "cycle_focus": {"cycle_id": FAKE_CYCLE_ID, "focus_refs": ["X"], "v": 2},
            "monthly_goals": {"month": "2026-04", "revenue_target": 50000},
            "quarterly_allocation": {"quarter": "2026-Q2", "allocations": {"Tudor": 0.5}},
        },
    )

    result = unpack_inbound_bundle(bundle, tmp_path)

    assert result["cycle_id"] == FAKE_CYCLE_ID
    assert result["roles_written"] == [
        "cycle_focus",
        "monthly_goals",
        "quarterly_allocation",
    ]

    assert json.loads(paths["cycle_focus"].read_text())["v"] == 2
    assert json.loads(paths["monthly_goals"].read_text())["revenue_target"] == 50000
    assert (
        json.loads(paths["quarterly_allocation"].read_text())["allocations"]["Tudor"]
        == 0.5
    )


def test_partial_payload_subset_roles_writes_only_those(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    # Only cycle_focus present in bundle; other two state files untouched.
    monthly_before = paths["monthly_goals"].read_bytes()
    quarterly_before = paths["quarterly_allocation"].read_bytes()

    bundle = build_inbound_bundle_zip(
        tmp_path / "inbound.zip",
        payloads={"cycle_focus": {"cycle_id": FAKE_CYCLE_ID, "v": 99}},
    )

    result = unpack_inbound_bundle(bundle, tmp_path)
    assert result["roles_written"] == ["cycle_focus"]
    assert paths["monthly_goals"].read_bytes() == monthly_before
    assert paths["quarterly_allocation"].read_bytes() == quarterly_before
    assert json.loads(paths["cycle_focus"].read_text())["v"] == 99


# ─── validation rules ──────────────────────────────────────────────


def test_manifest_missing_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip", omit_manifest=True
    )
    with pytest.raises(BundleValidationError, match="manifest.json missing"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_manifest_version_mismatch_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        manifest_override={
            "manifest_version": 2,
            "bundle_kind": "inbound",
            "cycle_id": FAKE_CYCLE_ID,
            "files": [],
        },
    )
    with pytest.raises(BundleValidationError, match="manifest_version"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_bundle_kind_wrong_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        manifest_override={
            "manifest_version": 1,
            "bundle_kind": "outbound",
            "cycle_id": FAKE_CYCLE_ID,
            "files": [],
        },
    )
    with pytest.raises(BundleValidationError, match="bundle_kind"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_cycle_id_mismatch_rejected_by_default(tmp_path):
    build_fake_grailzee_tree(tmp_path, cycle_id=FAKE_CYCLE_ID)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip", cycle_id=FAKE_PRIOR_CYCLE_ID
    )
    with pytest.raises(BundleValidationError, match="cycle_id"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_cycle_id_mismatch_allowed_when_strict_disabled(tmp_path):
    build_fake_grailzee_tree(tmp_path, cycle_id=FAKE_CYCLE_ID)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip", cycle_id=FAKE_PRIOR_CYCLE_ID
    )
    result = unpack_inbound_bundle(bundle, tmp_path, strict_cycle_id=False)
    assert result["cycle_id"] == FAKE_PRIOR_CYCLE_ID


def test_role_not_in_whitelist_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    # Include an off-whitelist role like 'analysis_cache'
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        payloads={
            "analysis_cache": {"dangerous": True},
            "cycle_focus": {"v": 1},
        },
    )
    with pytest.raises(BundleValidationError, match="non-whitelisted role"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_symlink_entry_rejected(tmp_path):
    """Manually craft a ZipInfo with S_IFLNK mode bits and verify rejection."""
    build_fake_grailzee_tree(tmp_path)
    bundle_path = tmp_path / "malicious.zip"

    # Build a valid manifest + role payload first
    valid = build_inbound_bundle_zip(tmp_path / "staging.zip")
    # Now clone into a new zip with an extra symlink entry
    import shutil
    shutil.copy(valid, bundle_path)

    with zipfile.ZipFile(bundle_path, "a") as zf:
        info = zipfile.ZipInfo("evil_symlink")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")

    with pytest.raises(BundleValidationError, match="[Ss]ymlink"):
        unpack_inbound_bundle(bundle_path, tmp_path)


def test_path_traversal_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        extra_entries={"../evil.json": b"payload"},
    )
    with pytest.raises(BundleValidationError, match="arcname"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_absolute_path_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        extra_entries={"/etc/passwd": b"payload"},
    )
    with pytest.raises(BundleValidationError, match="arcname"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_extraneous_archive_member_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        extra_entries={"stowaway.json": b'{"x": 1}'},
    )
    with pytest.raises(BundleValidationError, match="not listed in manifest"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_sha256_mismatch_rejected(tmp_path):
    """Tamper with a payload byte after manifest computation."""
    build_fake_grailzee_tree(tmp_path)
    bundle_path = tmp_path / "bundle.zip"
    build_inbound_bundle_zip(bundle_path, cycle_id=FAKE_CYCLE_ID)

    # Rewrite the cycle_focus.json member with different bytes
    import tempfile
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle_path, "r") as src, zipfile.ZipFile(
        tampered, "w"
    ) as dst:
        for info in src.infolist():
            if info.filename == "cycle_focus.json":
                dst.writestr(info.filename, b'{"tampered": true}')
            else:
                dst.writestr(info, src.read(info.filename))

    with pytest.raises(BundleValidationError, match="sha256|[Ss]ize"):
        unpack_inbound_bundle(tampered, tmp_path)


def test_size_mismatch_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip",
        payloads={"cycle_focus": {"cycle_id": FAKE_CYCLE_ID}},
        manifest_override={
            "manifest_version": 1,
            "bundle_kind": "inbound",
            "cycle_id": FAKE_CYCLE_ID,
            "files": [
                {
                    "path": "cycle_focus.json",
                    "role": "cycle_focus",
                    "sha256": "0" * 64,
                    "size_bytes": 9999,
                }
            ],
        },
    )
    with pytest.raises(BundleValidationError, match="[Ss]ize"):
        unpack_inbound_bundle(bundle, tmp_path)


def test_malformed_manifest_json_rejected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    bundle_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("manifest.json", "not json {")
    with pytest.raises(BundleValidationError, match="valid JSON"):
        unpack_inbound_bundle(bundle_path, tmp_path)


def test_missing_cache_when_strict_rejected(tmp_path):
    """No current cache + strict mode → validation fails before read."""
    # tree without cache
    state = tmp_path / "state"
    state.mkdir()
    # intentionally skip analysis_cache.json
    bundle_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({}))
    with pytest.raises(BundleValidationError, match="[Cc]ache"):
        unpack_inbound_bundle(bundle_path, tmp_path)


# ─── atomic write semantics ───────────────────────────────────────


def test_no_files_written_on_validation_failure(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    before = {
        "cycle_focus": paths["cycle_focus"].read_bytes(),
        "monthly_goals": paths["monthly_goals"].read_bytes(),
        "quarterly_allocation": paths["quarterly_allocation"].read_bytes(),
    }
    bundle = build_inbound_bundle_zip(
        tmp_path / "bundle.zip", cycle_id=FAKE_PRIOR_CYCLE_ID  # cycle_id mismatch
    )
    with pytest.raises(BundleValidationError):
        unpack_inbound_bundle(bundle, tmp_path)

    assert paths["cycle_focus"].read_bytes() == before["cycle_focus"]
    assert paths["monthly_goals"].read_bytes() == before["monthly_goals"]
    assert paths["quarterly_allocation"].read_bytes() == before["quarterly_allocation"]


def test_no_tmp_or_prior_files_left_behind(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    bundle = build_inbound_bundle_zip(tmp_path / "bundle.zip")
    unpack_inbound_bundle(bundle, tmp_path)

    leftovers = (
        list(paths["state"].glob("*.tmp.*"))
        + list(paths["state"].glob("*.prior.*"))
    )
    assert leftovers == []


def test_atomic_rollback_restores_prior_on_mid_write_failure(tmp_path, monkeypatch):
    """Simulate a failure during the atomic-replace phase. Verify all state
    files return to their pre-unpack contents."""
    paths = build_fake_grailzee_tree(tmp_path)
    before = {
        "cycle_focus": paths["cycle_focus"].read_bytes(),
        "monthly_goals": paths["monthly_goals"].read_bytes(),
        "quarterly_allocation": paths["quarterly_allocation"].read_bytes(),
    }

    bundle = build_inbound_bundle_zip(tmp_path / "bundle.zip")

    # Patch Path.replace so that the SECOND call raises. First replace completes;
    # rollback must undo it.
    original_replace = Path.replace
    calls = {"n": 0}

    def flaky_replace(self, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated mid-commit failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with pytest.raises(OSError, match="simulated"):
        unpack_inbound_bundle(bundle, tmp_path)

    # All three state files restored to pre-unpack state.
    assert paths["cycle_focus"].read_bytes() == before["cycle_focus"]
    assert paths["monthly_goals"].read_bytes() == before["monthly_goals"]
    assert paths["quarterly_allocation"].read_bytes() == before["quarterly_allocation"]


# ─── helper unit tests ────────────────────────────────────────────


def test_is_symlink_entry_detects_lnk_bit():
    info = zipfile.ZipInfo("x")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert _is_symlink_entry(info) is True


def test_is_symlink_entry_ignores_regular_file():
    info = zipfile.ZipInfo("x")
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    assert _is_symlink_entry(info) is False


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.json",
        "\\windows_abs.json",
        "..\\escape.json",
        "../escape.json",
        "sub/../escape.json",
        "C:/drive.json",
        "",
    ],
)
def test_unsafe_arcnames_flagged(name):
    assert _is_unsafe_arcname(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "manifest.json",
        "cycle_focus.json",
        "sub/role.json",
    ],
)
def test_safe_arcnames_accepted(name):
    assert _is_unsafe_arcname(name) is False


def test_bundle_not_found_raises(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    with pytest.raises(FileNotFoundError, match="not found"):
        unpack_inbound_bundle(tmp_path / "missing.zip", tmp_path)
