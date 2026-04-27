"""Tests for the installed state/cycle_focus.json file itself.

Validates the Phase A.5 starter file against v1.1 §3 starter-values
rules and the v1-shape schema (Drive-backed; schema_version 1). Every
strategy-tunable non-managed path must appear in ``defaulted_fields``
with ``cycle_date_range`` collapsed to a single parent path. Sentinel
values (``cycle_id="starter"``, epoch dates) must be present so
``is_cycle_focus_current`` never matches a real cycle before strategy
commits.

Skips when the file is not installed (run install_cycle_focus.py first).
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import read_config, schema_version_or_fail
from scripts.grailzee_common import STATE_PATH

INSTALLED_PATH = f"{STATE_PATH}/cycle_focus.json"

pytestmark = pytest.mark.skip(
    reason="cycle-focus-starter: sentinel state "
           "superseded by INBOUND apply; "
           "starter-shape invariants covered by "
           "test_install_cycle_focus.py"
)


EXPECTED_DEFAULTED_FIELDS = sorted(
    [
        "brand_emphasis",
        "brand_pullback",
        "capital_target",
        "cycle_date_range",
        "cycle_id",
        "notes",
        "target_margin_fraction",
        "targets",
        "volume_target",
    ]
)


class TestInstalledCycleFocus:
    def test_readable(self):
        cfg = read_config(INSTALLED_PATH)
        assert isinstance(cfg, dict)

    def test_schema_version_1(self):
        cfg = read_config(INSTALLED_PATH)
        assert schema_version_or_fail(cfg, 1) == 1

    def test_updated_by_phase_a_install(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["updated_by"] == "phase_a_install"

    def test_last_updated_is_iso_utc(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["last_updated"].endswith("Z")
        assert "T" in cfg["last_updated"]

    def test_no_top_level_nulls(self):
        cfg = read_config(INSTALLED_PATH)
        for key, value in cfg.items():
            assert value is not None, f"top-level field {key!r} is None"

    def test_defaulted_fields_exact_nine_paths(self):
        """Exactly nine strategy-tunable paths, alphabetized, with
        cycle_date_range collapsed to parent (not start/end)."""
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == EXPECTED_DEFAULTED_FIELDS
        assert len(cfg["defaulted_fields"]) == 9

    def test_cycle_date_range_not_enumerated(self):
        """cycle_date_range is a single strategic unit; start/end must
        NOT appear as separate defaulted paths."""
        cfg = read_config(INSTALLED_PATH)
        for p in cfg["defaulted_fields"]:
            assert p != "cycle_date_range.start"
            assert p != "cycle_date_range.end"

    def test_starter_cycle_id_sentinel(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["cycle_id"] == "starter"

    def test_epoch_date_range_sentinel(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["cycle_date_range"] == {"start": "1970-01-01", "end": "1970-01-01"}

    def test_capital_target_starter_value(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["capital_target"] == 15000

    def test_volume_target_starter_value(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["volume_target"] == 4

    def test_target_margin_fraction_carry_forward(self):
        """Matches analyzer_config's per_trade_target_margin_fraction
        (v1.1 §2 carry-forward rule)."""
        cfg = read_config(INSTALLED_PATH)
        assert cfg["target_margin_fraction"] == 0.05

    def test_targets_empty_array(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["targets"] == []

    def test_brand_emphasis_empty_array(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brand_emphasis"] == []

    def test_brand_pullback_empty_array(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brand_pullback"] == []

    def test_notes_non_empty(self):
        cfg = read_config(INSTALLED_PATH)
        assert isinstance(cfg["notes"], str)
        assert cfg["notes"].strip()

    def test_all_expected_fields_present(self):
        cfg = read_config(INSTALLED_PATH)
        for key in [
            "cycle_id",
            "cycle_date_range",
            "capital_target",
            "volume_target",
            "target_margin_fraction",
            "targets",
            "brand_emphasis",
            "brand_pullback",
            "notes",
        ]:
            assert key in cfg, f"missing expected field {key!r}"
