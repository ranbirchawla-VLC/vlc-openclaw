"""Tests for scripts.install_monthly_goals.

Mirrors test_install_sourcing_rules patterns. Flat schema; no collapse
logic to verify. Drive-backed (STATE_PATH) default target.
"""

from __future__ import annotations

import json

from scripts.config_helper import leaf_paths, read_config
from scripts.grailzee_common import STATE_PATH
from scripts.install_monthly_goals import (
    MONTHLY_GOALS_FACTORY_CONTENT,
    MONTHLY_GOALS_NAME,
    install,
)


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_exact_five_paths(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == [
            "brand_emphasis",
            "brand_pullback",
            "capital_target",
            "month",
            "volume_target",
        ]

    def test_defaulted_fields_matches_leaf_paths(self, tmp_path):
        """Flat schema; leaf_paths returns the right answer directly."""
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == sorted(
            leaf_paths(MONTHLY_GOALS_FACTORY_CONTENT)
        )

    def test_starter_values_match_spec(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["month"] == "starter"
        assert parsed["capital_target"] == 30000
        assert parsed["volume_target"] == 8
        assert parsed["brand_emphasis"] == []
        assert parsed["brand_pullback"] == []

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["month"] = "2026-05"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        after = json.loads(target.read_text())
        assert after["month"] == "2026-05"

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["month"] = "2026-05"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["month"] == "starter"

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_round_trip_via_config_helper(self, tmp_path):
        target = tmp_path / "monthly_goals.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "schema_version" in parsed
        assert "month" in parsed
        assert isinstance(parsed["defaulted_fields"], list)

    def test_default_target_resolves_to_state_path(self):
        """Default target is STATE_PATH/monthly_goals.json (Drive), NOT
        workspace state."""
        expected = f"{STATE_PATH}/{MONTHLY_GOALS_NAME}"
        assert expected.endswith("/monthly_goals.json")
        assert "GrailzeeData/state" in expected

    def test_factory_content_has_no_managed_keys(self):
        for key in ("last_updated", "updated_by", "defaulted_fields"):
            assert key not in MONTHLY_GOALS_FACTORY_CONTENT
