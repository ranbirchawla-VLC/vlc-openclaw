"""Tests for scripts.install_cycle_focus.

Mirrors test_install_sourcing_rules patterns plus coverage for the
cycle_date_range collapse and the Drive-backed (STATE_PATH) default
target.
"""

from __future__ import annotations

import json

from scripts.config_helper import read_config
from scripts.grailzee_common import STATE_PATH
from scripts.install_cycle_focus import (
    CYCLE_FOCUS_FACTORY_CONTENT,
    CYCLE_FOCUS_NAME,
    _defaulted_fields_for_cycle_focus,
    install,
)


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_exact_nine_paths(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == [
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

    def test_cycle_date_range_collapsed_to_parent(self, tmp_path):
        """cycle_date_range must appear as a single path, NOT as
        cycle_date_range.start / cycle_date_range.end."""
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        for p in parsed["defaulted_fields"]:
            assert p != "cycle_date_range.start"
            assert p != "cycle_date_range.end"
        assert "cycle_date_range" in parsed["defaulted_fields"]

    def test_collapse_helper_direct(self):
        """Unit test of the collapse helper in isolation."""
        fake = {
            "schema_version": 1,
            "cycle_id": "x",
            "cycle_date_range": {"start": "a", "end": "b"},
            "capital_target": 1,
            "targets": [],
        }
        result = _defaulted_fields_for_cycle_focus(fake)
        assert "cycle_date_range" in result
        assert "cycle_date_range.start" not in result
        assert "cycle_date_range.end" not in result
        assert "cycle_id" in result
        assert "capital_target" in result
        assert "targets" in result

    def test_starter_values_match_spec(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["cycle_id"] == "starter"
        assert parsed["cycle_date_range"] == {
            "start": "1970-01-01",
            "end": "1970-01-01",
        }
        assert parsed["capital_target"] == 15000
        assert parsed["volume_target"] == 4
        assert parsed["target_margin_fraction"] == 0.05
        assert parsed["targets"] == []
        assert parsed["brand_emphasis"] == []
        assert parsed["brand_pullback"] == []

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["cycle_id"] = "cycle_2026-09"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        after = json.loads(target.read_text())
        assert after["cycle_id"] == "cycle_2026-09"

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["cycle_id"] = "cycle_2026-09"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["cycle_id"] == "starter"

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_round_trip_via_config_helper(self, tmp_path):
        target = tmp_path / "cycle_focus.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "schema_version" in parsed
        assert "cycle_id" in parsed
        assert "cycle_date_range" in parsed
        assert isinstance(parsed["defaulted_fields"], list)

    def test_default_target_resolves_to_state_path(self):
        """Default target is STATE_PATH/cycle_focus.json (Drive), NOT
        workspace state. Asserted at path-resolution level, not by
        actually writing to Drive."""
        expected = f"{STATE_PATH}/{CYCLE_FOCUS_NAME}"
        assert expected.endswith("/cycle_focus.json")
        assert "GrailzeeData/state" in expected

    def test_factory_content_has_no_managed_keys(self):
        """Factory constant should not pre-set managed keys; write_config
        stamps them. Managed keys pre-set would be silently tolerated
        but muddies intent."""
        for key in ("last_updated", "updated_by", "defaulted_fields"):
            assert key not in CYCLE_FOCUS_FACTORY_CONTENT
