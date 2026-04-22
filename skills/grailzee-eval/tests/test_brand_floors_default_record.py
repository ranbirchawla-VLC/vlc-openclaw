"""B.7 Phase 0: assertions on the live state/brand_floors.json after
the default-record edit (2026-04-22, b7_section_7_close).

Verifies:
- Top-level ``default`` key present.
- Default record shape matches operator-locked
  {floor_pct: 10.0, tradeable: true, asset_class: watch}.
- Five named brand floors unchanged from 2026-04-21 lock
  (Rolex 5%, Tudor 10%, Breitling 10%, Cartier 10%, Omega 8%).
- ``defaulted_fields`` includes ``default.floor_pct``.

Skips when the file is not installed (test machine without state/).
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import read_config
from scripts.grailzee_common import config_path

INSTALLED_PATH = config_path("brand_floors.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=f"{INSTALLED_PATH} not installed; run install_brand_floors.py first",
)


class TestDefaultRecord:
    def test_default_record_present(self):
        cfg = read_config(INSTALLED_PATH)
        assert "default" in cfg, "top-level 'default' key missing post B.7 Phase 0"

    def test_default_record_shape(self):
        cfg = read_config(INSTALLED_PATH)
        default = cfg["default"]
        assert default["floor_pct"] == 10.0
        assert default["tradeable"] is True
        assert default["asset_class"] == "watch"

    def test_default_floor_pct_in_defaulted_fields(self):
        cfg = read_config(INSTALLED_PATH)
        assert "default.floor_pct" in cfg["defaulted_fields"]


class TestNamedBrandsUnchanged:
    EXPECTED = {
        "Rolex": 5.0,
        "Tudor": 10.0,
        "Breitling": 10.0,
        "Cartier": 10.0,
        "Omega": 8.0,
    }

    def test_named_brands_floor_pct_unchanged(self):
        cfg = read_config(INSTALLED_PATH)
        for name, expected in self.EXPECTED.items():
            assert cfg["brands"][name]["floor_pct"] == expected

    def test_named_brands_set_unchanged(self):
        cfg = read_config(INSTALLED_PATH)
        assert set(cfg["brands"].keys()) == set(self.EXPECTED.keys())

    def test_named_brands_tradeable_true(self):
        cfg = read_config(INSTALLED_PATH)
        for name in self.EXPECTED:
            assert cfg["brands"][name]["tradeable"] is True
