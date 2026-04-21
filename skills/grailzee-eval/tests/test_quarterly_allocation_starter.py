"""Tests for the installed state/quarterly_allocation.json file itself.

Validates the Phase A.5 starter file against v1.1 §3 starter-values
rules. Empty-object leaves (brand_allocations, category_allocations)
must appear in ``defaulted_fields`` as parent paths; the installer's
custom walker injects them because `leaf_paths` alone drops empty dicts.
Sentinel ``quarter="starter"`` is the placeholder until strategy
commits a real quarter.

Skips when the file is not installed (run install_quarterly_allocation.py
first).
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import read_config, schema_version_or_fail
from scripts.grailzee_common import STATE_PATH

INSTALLED_PATH = f"{STATE_PATH}/quarterly_allocation.json"

pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=(
        f"{INSTALLED_PATH} not installed; run install_quarterly_allocation.py first"
    ),
)


EXPECTED_DEFAULTED_FIELDS = sorted(
    [
        "brand_allocations",
        "category_allocations",
        "quarter",
        "total_capital",
    ]
)


class TestInstalledQuarterlyAllocation:
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

    def test_defaulted_fields_exact_four_paths(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == EXPECTED_DEFAULTED_FIELDS
        assert len(cfg["defaulted_fields"]) == 4

    def test_empty_dicts_surface_as_parent_paths(self):
        """brand_allocations and category_allocations must appear as
        parent paths in defaulted_fields even though they're empty
        dicts. leaf_paths alone would drop them (recurses into nothing);
        installer injects them explicitly."""
        cfg = read_config(INSTALLED_PATH)
        assert "brand_allocations" in cfg["defaulted_fields"]
        assert "category_allocations" in cfg["defaulted_fields"]

    def test_starter_quarter_sentinel(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["quarter"] == "starter"

    def test_total_capital_starter_value(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["total_capital"] == 45000

    def test_brand_allocations_empty_dict(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brand_allocations"] == {}

    def test_category_allocations_empty_dict(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["category_allocations"] == {}

    def test_all_expected_fields_present(self):
        cfg = read_config(INSTALLED_PATH)
        for key in [
            "quarter",
            "total_capital",
            "brand_allocations",
            "category_allocations",
        ]:
            assert key in cfg, f"missing expected field {key!r}"
