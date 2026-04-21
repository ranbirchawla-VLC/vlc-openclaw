"""Tests for the installed state/brand_floors.json file itself.

Validates the file's content against the Phase A.3 schema and v1.1
§1 Item 1 confirmed factory content. Every ``brands.<Name>.floor_pct``
path must appear in ``defaulted_fields``; ``tradeable`` and
``asset_class`` paths must not (structural declarations, not defaults).

Skips when the file is not installed — installer has not been run on
that machine yet.
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import read_config, schema_version_or_fail
from scripts.grailzee_common import config_path
from scripts.install_brand_floors import (
    BRAND_FLOORS_FACTORY_CONTENT,
    BRAND_FLOORS_NAME,
    BRAND_FLOORS_SCHEMA_VERSION,
)


INSTALLED_PATH = config_path(BRAND_FLOORS_NAME)


pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=f"{INSTALLED_PATH} not installed; run install_brand_floors.py first",
)


EXPECTED_BRANDS = {"Rolex", "Tudor", "Breitling", "Cartier", "Omega"}
EXPECTED_FLOOR_PCT = {
    "Rolex": 5.0,
    "Tudor": 10.0,
    "Breitling": 10.0,
    "Cartier": 10.0,
    "Omega": 8.0,
}
EXPECTED_DEFAULTED_FIELDS = sorted(
    f"brands.{b}.floor_pct" for b in EXPECTED_BRANDS
)


class TestInstalledBrandFloors:
    def test_readable(self):
        cfg = read_config(INSTALLED_PATH)
        assert isinstance(cfg, dict)

    def test_schema_version_1(self):
        cfg = read_config(INSTALLED_PATH)
        assert (
            schema_version_or_fail(cfg, BRAND_FLOORS_SCHEMA_VERSION) == 1
        )

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

    def test_defaulted_fields_exact_floor_pct_paths(self):
        """Exactly the five floor_pct paths, alphabetically sorted."""
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == EXPECTED_DEFAULTED_FIELDS

    def test_defaulted_fields_excludes_tradeable(self):
        cfg = read_config(INSTALLED_PATH)
        for path in cfg["defaulted_fields"]:
            assert not path.endswith(".tradeable"), (
                f"tradeable is structural, not a strategy-set default: {path}"
            )

    def test_defaulted_fields_excludes_asset_class(self):
        cfg = read_config(INSTALLED_PATH)
        for path in cfg["defaulted_fields"]:
            assert not path.endswith(".asset_class"), (
                f"asset_class is structural, not a strategy-set default: {path}"
            )

    def test_brand_universe_exact(self):
        cfg = read_config(INSTALLED_PATH)
        assert set(cfg["brands"].keys()) == EXPECTED_BRANDS

    def test_per_brand_floor_pct_matches_v1_1(self):
        cfg = read_config(INSTALLED_PATH)
        for name, expected in EXPECTED_FLOOR_PCT.items():
            assert cfg["brands"][name]["floor_pct"] == expected

    def test_all_brands_tradeable_true(self):
        cfg = read_config(INSTALLED_PATH)
        for name in EXPECTED_BRANDS:
            assert cfg["brands"][name]["tradeable"] is True

    def test_all_brands_asset_class_watch(self):
        cfg = read_config(INSTALLED_PATH)
        for name in EXPECTED_BRANDS:
            assert cfg["brands"][name]["asset_class"] == "watch"

    def test_matches_factory_content_verbatim(self):
        """brands subtree matches the installer's factory content exactly."""
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brands"] == BRAND_FLOORS_FACTORY_CONTENT["brands"]
