"""Tests for scripts.install_sourcing_rules.

Mirrors test_install_brand_floors and test_install_analyzer_config
patterns: refuse-overwrite, --force, --dry-run, exit codes, installed
content structure. Uses tmp_path for hermeticity.
"""

from __future__ import annotations

import json

from scripts.config_helper import leaf_paths, read_config
from scripts.grailzee_common import SOURCING_RULES_FACTORY_DEFAULTS
from scripts.install_sourcing_rules import install


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_covers_every_leaf(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        expected = sorted(leaf_paths(SOURCING_RULES_FACTORY_DEFAULTS))
        assert parsed["defaulted_fields"] == expected

    def test_defaulted_fields_exact_four_paths(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == [
            "condition_minimum",
            "keyword_filters.exclude",
            "keyword_filters.include",
            "papers_required",
        ]

    def test_keyword_lists_not_enumerated(self, tmp_path):
        """include/exclude are listed as parent paths, not per-entry."""
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        for path in parsed["defaulted_fields"]:
            assert "[" not in path, f"list element path leaked: {path}"

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["condition_minimum"] = "Fair"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        after = json.loads(target.read_text())
        assert after["condition_minimum"] == "Fair"

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["condition_minimum"] = "Fair"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["condition_minimum"] == "Very Good"

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_round_trip_via_config_helper(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "schema_version" in parsed
        assert "condition_minimum" in parsed
        assert "keyword_filters" in parsed
        assert isinstance(parsed["defaulted_fields"], list)

    def test_no_build_brief_internal_fields_in_install(self, tmp_path):
        target = tmp_path / "sourcing_rules.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        # Sanity: installer does not leak build_brief's S2-protected fields.
        assert "platform_priority" not in parsed
        assert "us_inventory_only" not in parsed
        assert "never_exceed_max_buy" not in parsed
