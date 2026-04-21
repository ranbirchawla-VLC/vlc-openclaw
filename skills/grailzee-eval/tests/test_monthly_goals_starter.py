"""Tests for the installed state/monthly_goals.json file itself.

Validates the Phase A.5 starter file against v1.1 §3 starter-values
rules. Flat schema; every non-managed leaf path must appear in
``defaulted_fields``. Sentinel ``month="starter"`` is the placeholder
until strategy commits a real month.

Skips when the file is not installed (run install_monthly_goals.py first).
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import leaf_paths, read_config, schema_version_or_fail
from scripts.grailzee_common import STATE_PATH

INSTALLED_PATH = f"{STATE_PATH}/monthly_goals.json"

pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=f"{INSTALLED_PATH} not installed; run install_monthly_goals.py first",
)


EXPECTED_DEFAULTED_FIELDS = sorted(
    [
        "brand_emphasis",
        "brand_pullback",
        "capital_target",
        "month",
        "volume_target",
    ]
)


class TestInstalledMonthlyGoals:
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

    def test_defaulted_fields_exact_five_paths(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == EXPECTED_DEFAULTED_FIELDS
        assert len(cfg["defaulted_fields"]) == 5

    def test_starter_month_sentinel(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["month"] == "starter"

    def test_capital_target_starter_value(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["capital_target"] == 30000

    def test_volume_target_starter_value(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["volume_target"] == 8

    def test_brand_emphasis_empty_array(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brand_emphasis"] == []

    def test_brand_pullback_empty_array(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["brand_pullback"] == []

    def test_all_expected_fields_present(self):
        cfg = read_config(INSTALLED_PATH)
        for key in [
            "month",
            "capital_target",
            "volume_target",
            "brand_emphasis",
            "brand_pullback",
        ]:
            assert key in cfg, f"missing expected field {key!r}"
