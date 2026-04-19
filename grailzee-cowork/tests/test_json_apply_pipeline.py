"""Tests for apply_strategy_output — the Phase 24b JSON apply pipeline.

Validates:
- Happy paths across all four decision sections (cycle_focus,
  monthly_goals, quarterly_allocation, config_updates)
- Correct state files are written, others untouched
- Payload contents round-trip byte-for-byte (indent=2 JSON + trailing \n)
- cycle_id gate enforced; override works
- Invalid JSON / invalid schema / missing file rejected cleanly
- Role-map extension accepts all six D5 config file names
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _fixtures import (
    FAKE_CYCLE_ID,
    build_fake_grailzee_tree,
    make_strategy_cycle_focus,
    make_strategy_output,
    write_strategy_output,
)

from grailzee_bundle.unpack_bundle import (
    BundleValidationError,
    apply_strategy_output,
)


# ─── happy paths ──────────────────────────────────────────────────────

def test_cycle_focus_only_writes_single_state_file(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id=FAKE_CYCLE_ID)
    write_strategy_output(json_path, payload)

    # Capture original monthly_goals/quarterly_allocation contents so we
    # can confirm they're UNTOUCHED by a cycle_focus-only apply.
    monthly_before = paths["monthly_goals"].read_text()
    quarterly_before = paths["quarterly_allocation"].read_text()

    result = apply_strategy_output(json_path, paths["root"])

    assert result["cycle_id"] == FAKE_CYCLE_ID
    assert result["session_mode"] == "cycle_planning"
    assert result["roles_written"] == ["cycle_focus"]
    assert result["source"] == "grailzee-strategy/0.1.0"

    # cycle_focus.json was overwritten with the new contents
    written = json.loads(paths["cycle_focus"].read_text())
    assert written == payload["decisions"]["cycle_focus"]

    # Other state files untouched
    assert paths["monthly_goals"].read_text() == monthly_before
    assert paths["quarterly_allocation"].read_text() == quarterly_before


def test_all_four_decisions_populated_writes_expected_files(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(
        cycle_id=FAKE_CYCLE_ID,
        include_monthly=True,
        include_quarterly=True,
        include_configs=("signal_thresholds", "margin_config"),
    )
    write_strategy_output(json_path, payload)

    result = apply_strategy_output(json_path, paths["root"])

    assert set(result["roles_written"]) == {
        "cycle_focus",
        "monthly_goals",
        "quarterly_allocation",
        "signal_thresholds",
        "margin_config",
    }
    # config file writes land at state/<name>.json
    signal_path = paths["state"] / "signal_thresholds.json"
    margin_path = paths["state"] / "margin_config.json"
    assert signal_path.exists()
    assert margin_path.exists()
    assert json.loads(signal_path.read_text()) == (
        payload["decisions"]["config_updates"]["signal_thresholds"]
    )
    assert json.loads(margin_path.read_text()) == (
        payload["decisions"]["config_updates"]["margin_config"]
    )
    # Non-selected config files were NOT written (they don't exist at all
    # since the fake tree doesn't seed them).
    assert not (paths["state"] / "scoring_thresholds.json").exists()
    assert not (paths["state"] / "momentum_thresholds.json").exists()


def test_all_six_config_roles_accepted(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    all_six = (
        "signal_thresholds",
        "scoring_thresholds",
        "momentum_thresholds",
        "window_config",
        "premium_config",
        "margin_config",
    )
    payload = make_strategy_output(
        cycle_id=FAKE_CYCLE_ID,
        include_configs=all_six,
    )
    write_strategy_output(json_path, payload)
    result = apply_strategy_output(json_path, paths["root"])
    assert set(result["roles_written"]) == {"cycle_focus"} | set(all_six)
    for name in all_six:
        assert (paths["state"] / f"{name}.json").exists()


def test_written_state_file_has_indent2_and_trailing_newline(tmp_path: Path) -> None:
    """State writes use indent=2 + trailing newline (grailzee-eval convention)."""
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id=FAKE_CYCLE_ID)
    write_strategy_output(json_path, payload)
    apply_strategy_output(json_path, paths["root"])

    written = paths["cycle_focus"].read_text()
    assert written.endswith("\n")
    # indent=2 → nested keys have "  " prefix
    assert '\n  "targets":' in written


def test_cycle_focus_only_but_decisions_section_stored_alongside(tmp_path: Path) -> None:
    """Only populated decision sections trigger writes. A cycle_focus-only
    payload must NOT blank out pre-existing monthly_goals.json."""
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id=FAKE_CYCLE_ID)
    write_strategy_output(json_path, payload)

    pre_contents = paths["monthly_goals"].read_text()
    apply_strategy_output(json_path, paths["root"])
    assert paths["monthly_goals"].read_text() == pre_contents


# ─── cycle_id gate ────────────────────────────────────────────────────

def test_cycle_id_mismatch_strict_rejected(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path, cycle_id="cycle_2026-04")
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id="cycle_2026-05")  # different
    write_strategy_output(json_path, payload)

    pre_focus = paths["cycle_focus"].read_text()
    with pytest.raises(BundleValidationError, match="cycle_id"):
        apply_strategy_output(json_path, paths["root"])
    # No writes on reject
    assert paths["cycle_focus"].read_text() == pre_focus


def test_cycle_id_mismatch_override_accepted(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path, cycle_id="cycle_2026-04")
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id="cycle_2026-05")
    write_strategy_output(json_path, payload)

    result = apply_strategy_output(json_path, paths["root"], strict_cycle_id=False)
    assert result["cycle_id"] == "cycle_2026-05"


# ─── parse / validation failures ──────────────────────────────────────

def test_invalid_json_syntax_rejected(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "bad.json"
    json_path.write_text("{not valid json")
    with pytest.raises(BundleValidationError, match="not valid JSON"):
        apply_strategy_output(json_path, paths["root"])


def test_schema_violation_rejected_before_write(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "bad.json"
    payload = make_strategy_output(cycle_id=FAKE_CYCLE_ID)
    payload["strategy_output_version"] = 999  # invalid
    write_strategy_output(json_path, payload)

    pre_focus = paths["cycle_focus"].read_text()
    with pytest.raises(BundleValidationError, match="strategy_output schema"):
        apply_strategy_output(json_path, paths["root"])
    # Atomic guarantee: no partial writes on schema failure
    assert paths["cycle_focus"].read_text() == pre_focus


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    paths = build_fake_grailzee_tree(tmp_path)
    with pytest.raises(FileNotFoundError):
        apply_strategy_output(tmp_path / "nonexistent.json", paths["root"])


# ─── return value ────────────────────────────────────────────────────

def test_returns_validated_payload_for_downstream_archiving(tmp_path: Path) -> None:
    """Caller-facing contract: the summary dict includes the validated
    payload so archive-writing doesn't need to re-read/re-validate."""
    paths = build_fake_grailzee_tree(tmp_path)
    json_path = tmp_path / "strategy_output.json"
    payload = make_strategy_output(cycle_id=FAKE_CYCLE_ID)
    write_strategy_output(json_path, payload)
    result = apply_strategy_output(json_path, paths["root"])
    assert result["payload"] == payload
