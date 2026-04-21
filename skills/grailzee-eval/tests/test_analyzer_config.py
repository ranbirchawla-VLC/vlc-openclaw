"""Tests for the installed state/analyzer_config.json file itself.

Validates the file's content against the Phase A.2 schema and the
factory defaults. Each field in the schema (dotted-path form) must
appear in ``defaulted_fields``, since strategy has not set any values
yet at Phase A install time.

These tests read the real file at workspace state path. If the file
is not present, they skip — the installer has not been run on that
machine yet.
"""

from __future__ import annotations

import json
import os

import pytest

from scripts.config_helper import leaf_paths, read_config, schema_version_or_fail
from scripts.grailzee_common import (
    ANALYZER_CONFIG_FACTORY_DEFAULTS,
    ANALYZER_CONFIG_NAME,
    ANALYZER_CONFIG_SCHEMA_VERSION,
    config_path,
)


INSTALLED_PATH = config_path(ANALYZER_CONFIG_NAME)


pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=f"{INSTALLED_PATH} not installed; run install_analyzer_config.py first",
)


class TestInstalledAnalyzerConfig:
    def test_readable(self):
        cfg = read_config(INSTALLED_PATH)
        assert isinstance(cfg, dict)

    def test_schema_version_1(self):
        cfg = read_config(INSTALLED_PATH)
        assert schema_version_or_fail(cfg, ANALYZER_CONFIG_SCHEMA_VERSION) == 1

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

    def test_defaulted_fields_covers_every_leaf(self):
        """Every leaf dotted path in the schema must be listed as
        defaulted at install — strategy has not committed any values."""
        cfg = read_config(INSTALLED_PATH)
        expected = sorted(leaf_paths(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        assert cfg["defaulted_fields"] == expected

    def test_values_match_factory_defaults(self):
        """Every value in the installed file matches the factory default."""
        cfg = read_config(INSTALLED_PATH)

        def walk(expected: dict, actual: dict, trail: str = "") -> None:
            for k, v in expected.items():
                here = f"{trail}.{k}" if trail else k
                assert k in actual, f"missing key {here}"
                if isinstance(v, dict):
                    walk(v, actual[k], here)
                else:
                    assert actual[k] == v, f"{here}: expected {v}, got {actual[k]}"

        walk(ANALYZER_CONFIG_FACTORY_DEFAULTS, cfg)

    def test_section_coverage(self):
        """All required §2.1 sections are present."""
        cfg = read_config(INSTALLED_PATH)
        for section in ("windows", "margin", "labor", "premium_model", "scoring"):
            assert section in cfg

    def test_signal_thresholds_are_strictly_ascending(self):
        cfg = read_config(INSTALLED_PATH)
        st = cfg["scoring"]["signal_thresholds"]
        assert (
            st["strong_max_risk_pct"]
            < st["normal_max_risk_pct"]
            < st["reserve_max_risk_pct"]
            < st["careful_max_risk_pct"]
        )

    def test_fractions_are_in_zero_one(self):
        cfg = read_config(INSTALLED_PATH)
        for path, val in [
            ("margin.per_trade_target_margin_fraction",
             cfg["margin"]["per_trade_target_margin_fraction"]),
            ("margin.monthly_return_target_fraction",
             cfg["margin"]["monthly_return_target_fraction"]),
            ("scoring.risk_reserve_threshold_fraction",
             cfg["scoring"]["risk_reserve_threshold_fraction"]),
        ]:
            assert 0 < val < 1, f"{path} = {val} is not a fraction in (0,1)"
