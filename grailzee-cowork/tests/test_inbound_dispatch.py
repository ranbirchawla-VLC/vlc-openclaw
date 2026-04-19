"""Tests for INBOUND dual-input dispatch (.zip vs .json).

The dispatch layer inspects extension + magic bytes BEFORE any parse/
validate work happens, so obviously-wrong inputs fail fast without the
user chasing a misleading downstream error. Existing Phase 24a .zip
behavior must not regress.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _fixtures import (
    FAKE_CYCLE_ID,
    build_fake_grailzee_tree,
    build_inbound_bundle_zip,
    make_strategy_output,
    write_strategy_output,
)

from grailzee_bundle.unpack_bundle import (
    BundleValidationError,
    _detect_input_type,
    main,
)


# ─── _detect_input_type ──────────────────────────────────────────────

def test_detects_zip_with_pk_magic(tmp_path: Path) -> None:
    zip_path = tmp_path / "inbound.zip"
    build_inbound_bundle_zip(zip_path)
    assert _detect_input_type(zip_path) == "zip"


def test_rejects_zip_extension_without_pk_magic(tmp_path: Path) -> None:
    """A .zip file whose contents aren't actually a zip archive is
    rejected before any zipfile.ZipFile call errors cryptically."""
    fake = tmp_path / "not_really.zip"
    fake.write_text("this is not a zip file")
    with pytest.raises(BundleValidationError, match="not a zip archive"):
        _detect_input_type(fake)


def test_detects_json_with_leading_brace(tmp_path: Path) -> None:
    json_path = tmp_path / "output.json"
    json_path.write_text('{"strategy_output_version": 1}')
    assert _detect_input_type(json_path) == "json"


def test_detects_json_with_leading_whitespace(tmp_path: Path) -> None:
    """Permit leading whitespace (editors often add it)."""
    json_path = tmp_path / "output.json"
    json_path.write_text('\n  {"strategy_output_version": 1}')
    assert _detect_input_type(json_path) == "json"


def test_detects_json_with_leading_bracket(tmp_path: Path) -> None:
    """Top-level is an object per the schema, but arrays must still pass
    the magic-byte probe (actual validation catches the shape mismatch)."""
    json_path = tmp_path / "output.json"
    json_path.write_text("[]")
    assert _detect_input_type(json_path) == "json"


def test_rejects_json_extension_with_non_json_content(tmp_path: Path) -> None:
    fake = tmp_path / "not_json.json"
    fake.write_text("this is plain text, not JSON")
    with pytest.raises(BundleValidationError, match="does not look like"):
        _detect_input_type(fake)


def test_rejects_json_extension_with_empty_file(tmp_path: Path) -> None:
    fake = tmp_path / "empty.json"
    fake.write_text("")
    with pytest.raises(BundleValidationError, match="does not look like"):
        _detect_input_type(fake)


def test_rejects_unknown_extension(tmp_path: Path) -> None:
    fake = tmp_path / "payload.txt"
    fake.write_text("{}")
    with pytest.raises(BundleValidationError, match="Unsupported input extension"):
        _detect_input_type(fake)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _detect_input_type(tmp_path / "does_not_exist.zip")


def test_extension_case_insensitive(tmp_path: Path) -> None:
    """Operators on macOS sometimes get .ZIP extensions from Chat downloads."""
    zip_path = tmp_path / "inbound.ZIP"
    build_inbound_bundle_zip(zip_path)
    assert _detect_input_type(zip_path) == "zip"


# ─── main() dispatch ──────────────────────────────────────────────────

def test_main_with_zip_invokes_unpack_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Phase 24a contract regression check: .zip path still works end to end."""
    paths = build_fake_grailzee_tree(tmp_path)
    zip_path = tmp_path / "inbound.zip"
    build_inbound_bundle_zip(zip_path, cycle_id=FAKE_CYCLE_ID)

    rc = main([str(zip_path), "--grailzee-root", str(paths["root"])])
    assert rc == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["cycle_id"] == FAKE_CYCLE_ID
    assert set(summary["roles_written"]) == {
        "cycle_focus",
        "monthly_goals",
        "quarterly_allocation",
    }
    # Summary from the .zip path must not carry a "session_mode" key —
    # that's the Phase 24b JSON-path addition.
    assert "session_mode" not in summary


def test_main_with_json_invokes_apply_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    write_strategy_output(json_path, make_strategy_output(cycle_id=FAKE_CYCLE_ID))

    rc = main([str(json_path), "--grailzee-root", str(paths["root"])])
    assert rc == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["cycle_id"] == FAKE_CYCLE_ID
    assert summary["session_mode"] == "cycle_planning"
    assert summary["roles_written"] == ["cycle_focus"]
    # payload is stripped from CLI output (already on disk as the input file)
    assert "payload" not in summary


def test_main_with_bad_extension_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    fake = tmp_path / "mystery.dat"
    fake.write_text("{}")
    rc = main([str(fake), "--grailzee-root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Unsupported input extension" in err
