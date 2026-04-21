"""Tests for scripts.install_quarterly_allocation.

Mirrors test_install_sourcing_rules patterns plus coverage for the
empty-dict parent-path injection (leaf_paths alone drops empty dicts;
the installer's custom walker adds them back). Drive-backed (STATE_PATH)
default target.
"""

from __future__ import annotations

import json

from scripts.config_helper import read_config
from scripts.grailzee_common import STATE_PATH
from scripts.install_quarterly_allocation import (
    QUARTERLY_ALLOCATION_FACTORY_CONTENT,
    QUARTERLY_ALLOCATION_NAME,
    _defaulted_fields_for_quarterly,
    install,
)


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_exact_four_paths(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == [
            "brand_allocations",
            "category_allocations",
            "quarter",
            "total_capital",
        ]

    def test_empty_dicts_present_as_parent_paths(self, tmp_path):
        """The two empty-dict allocation fields must surface as parent
        paths in defaulted_fields. leaf_paths alone drops them."""
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "brand_allocations" in parsed["defaulted_fields"]
        assert "category_allocations" in parsed["defaulted_fields"]

    def test_defaulted_helper_includes_empty_dicts(self):
        """Unit test of the defaulted-fields helper: verifies the empty-
        dict injection step works without installer scaffolding."""
        fake = {
            "schema_version": 1,
            "quarter": "x",
            "total_capital": 1,
            "brand_allocations": {},
            "category_allocations": {},
        }
        result = _defaulted_fields_for_quarterly(fake)
        assert "brand_allocations" in result
        assert "category_allocations" in result
        assert "quarter" in result
        assert "total_capital" in result
        assert len(result) == 4

    def test_starter_values_match_spec(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["quarter"] == "starter"
        assert parsed["total_capital"] == 45000
        assert parsed["brand_allocations"] == {}
        assert parsed["category_allocations"] == {}

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["quarter"] = "2026-Q2"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        after = json.loads(target.read_text())
        assert after["quarter"] == "2026-Q2"

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["quarter"] = "2026-Q2"
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["quarter"] == "starter"

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_round_trip_via_config_helper(self, tmp_path):
        target = tmp_path / "quarterly_allocation.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "schema_version" in parsed
        assert "quarter" in parsed
        assert isinstance(parsed["defaulted_fields"], list)

    def test_default_target_resolves_to_state_path(self):
        """Default target is STATE_PATH/quarterly_allocation.json (Drive),
        NOT workspace state."""
        expected = f"{STATE_PATH}/{QUARTERLY_ALLOCATION_NAME}"
        assert expected.endswith("/quarterly_allocation.json")
        assert "GrailzeeData/state" in expected

    def test_factory_content_has_no_managed_keys(self):
        for key in ("last_updated", "updated_by", "defaulted_fields"):
            assert key not in QUARTERLY_ALLOCATION_FACTORY_CONTENT
