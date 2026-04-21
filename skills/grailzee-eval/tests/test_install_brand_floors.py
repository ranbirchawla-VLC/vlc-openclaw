"""Tests for scripts.install_brand_floors.

Covers the installer's guardrails (refuse-overwrite, --force, --dry-run)
and the purpose-built floor_pct-only defaulted_fields walker. Installs
into tmp_path to stay hermetic.
"""

from __future__ import annotations

import json

from scripts.config_helper import read_config
from scripts.install_brand_floors import (
    BRAND_FLOORS_FACTORY_CONTENT,
    _floor_pct_paths,
    install,
)


EXPECTED_BRANDS = {"Rolex", "Tudor", "Breitling", "Cartier", "Omega"}
EXPECTED_FLOOR_PCT_PATHS = sorted(
    f"brands.{b}.floor_pct" for b in EXPECTED_BRANDS
)


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_is_floor_pct_only(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["defaulted_fields"] == EXPECTED_FLOOR_PCT_PATHS

    def test_defaulted_fields_excludes_tradeable(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        for path in parsed["defaulted_fields"]:
            assert ".tradeable" not in path

    def test_defaulted_fields_excludes_asset_class(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        for path in parsed["defaulted_fields"]:
            assert ".asset_class" not in path

    def test_brands_subtree_matches_factory(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert parsed["brands"] == BRAND_FLOORS_FACTORY_CONTENT["brands"]

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        # Mutate the file so we can tell if it got clobbered
        sentinel = json.loads(target.read_text())
        sentinel["brands"]["Rolex"]["floor_pct"] = 99.9
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        after = json.loads(target.read_text())
        assert after["brands"]["Rolex"]["floor_pct"] == 99.9

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["brands"]["Rolex"]["floor_pct"] = 99.9
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["brands"]["Rolex"]["floor_pct"] == 5.0

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_round_trip_via_config_helper(self, tmp_path):
        """Installed file loads back without errors via the canonical helper."""
        target = tmp_path / "brand_floors.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        assert "schema_version" in parsed
        assert "brands" in parsed
        assert isinstance(parsed["defaulted_fields"], list)


class TestFloorPctPathsHelper:
    """Unit tests for the purpose-built walker."""

    def test_picks_up_every_floor_pct(self):
        paths = _floor_pct_paths(BRAND_FLOORS_FACTORY_CONTENT)
        assert paths == EXPECTED_FLOOR_PCT_PATHS

    def test_excludes_tradeable_and_asset_class(self):
        paths = _floor_pct_paths(BRAND_FLOORS_FACTORY_CONTENT)
        assert not any(".tradeable" in p for p in paths)
        assert not any(".asset_class" in p for p in paths)

    def test_returns_empty_on_missing_brands(self):
        assert _floor_pct_paths({"schema_version": 1}) == []

    def test_returns_empty_when_brands_not_a_dict(self):
        assert _floor_pct_paths({"brands": None}) == []
        assert _floor_pct_paths({"brands": []}) == []
        assert _floor_pct_paths({"brands": "nope"}) == []

    def test_skips_non_dict_brand_entries(self):
        content = {
            "brands": {
                "Rolex": {"floor_pct": 5.0},
                "Tudor": "not a dict",
                "Omega": {"floor_pct": 8.0},
            }
        }
        paths = _floor_pct_paths(content)
        assert paths == ["brands.Omega.floor_pct", "brands.Rolex.floor_pct"]

    def test_skips_brand_without_floor_pct(self):
        content = {
            "brands": {
                "Rolex": {"floor_pct": 5.0},
                "Unknown": {"tradeable": False, "asset_class": "watch"},
            }
        }
        paths = _floor_pct_paths(content)
        assert paths == ["brands.Rolex.floor_pct"]

    def test_output_is_sorted(self):
        content = {
            "brands": {
                "Zed": {"floor_pct": 1.0},
                "Alpha": {"floor_pct": 2.0},
                "Mike": {"floor_pct": 3.0},
            }
        }
        paths = _floor_pct_paths(content)
        assert paths == sorted(paths)
