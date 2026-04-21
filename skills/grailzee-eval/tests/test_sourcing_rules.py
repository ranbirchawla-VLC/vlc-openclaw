"""Tests for the installed state/sourcing_rules.json file itself.

Validates the file's content against the Phase A.4 schema (v1 §2.3)
and the factory defaults lifted from build_brief.SOURCING_RULES's
strategy-tunable fields. Every strategy-tunable leaf path must appear
in ``defaulted_fields``. Hardcoded build_brief-internal fields
(platform_priority, us_inventory_only, never_exceed_max_buy) must NOT
appear in this file.

Skips when the file is not installed.
"""

from __future__ import annotations

import os

import pytest

from scripts.config_helper import leaf_paths, read_config, schema_version_or_fail
from scripts.grailzee_common import (
    SOURCING_RULES_FACTORY_DEFAULTS,
    SOURCING_RULES_NAME,
    SOURCING_RULES_SCHEMA_VERSION,
    config_path,
)


INSTALLED_PATH = config_path(SOURCING_RULES_NAME)

pytestmark = pytest.mark.skipif(
    not os.path.exists(INSTALLED_PATH),
    reason=f"{INSTALLED_PATH} not installed; run install_sourcing_rules.py first",
)


EXPECTED_DEFAULTED_FIELDS = sorted(
    ["condition_minimum", "keyword_filters.exclude",
     "keyword_filters.include", "papers_required"]
)


class TestInstalledSourcingRules:
    def test_readable(self):
        cfg = read_config(INSTALLED_PATH)
        assert isinstance(cfg, dict)

    def test_schema_version_1(self):
        cfg = read_config(INSTALLED_PATH)
        assert schema_version_or_fail(cfg, SOURCING_RULES_SCHEMA_VERSION) == 1

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

    def test_defaulted_fields_exact(self):
        """Exactly the four strategy-tunable leaf paths, alphabetized."""
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == EXPECTED_DEFAULTED_FIELDS

    def test_defaulted_fields_matches_leaf_paths(self):
        """defaulted_fields == leaf_paths(content) for this file.

        sourcing_rules has no structural-vs-tunable split, so every
        non-managed leaf should be defaulted. Direct leaf_paths match
        validates the installer's no-exclusion logic.
        """
        cfg = read_config(INSTALLED_PATH)
        assert cfg["defaulted_fields"] == sorted(
            leaf_paths(SOURCING_RULES_FACTORY_DEFAULTS)
        )

    def test_condition_minimum(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["condition_minimum"] == "Very Good"

    def test_papers_required(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["papers_required"] is True

    def test_include_keywords_exact(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["keyword_filters"]["include"] == [
            "full set", "complete set", "box papers", "BNIB", "like new",
            "excellent", "very good", "AD", "authorized",
        ]

    def test_exclude_keywords_exact(self):
        cfg = read_config(INSTALLED_PATH)
        assert cfg["keyword_filters"]["exclude"] == [
            "watch only", "no papers", "head only", "international",
            "damaged", "for parts", "aftermarket", "rep", "homage",
        ]

    def test_no_build_brief_internal_fields_leaked(self):
        """platform_priority, us_inventory_only, never_exceed_max_buy
        must stay in build_brief per schema v1 S2 and §2.3. Their
        presence here would indicate a scope leak."""
        cfg = read_config(INSTALLED_PATH)
        assert "platform_priority" not in cfg
        assert "us_inventory_only" not in cfg
        assert "never_exceed_max_buy" not in cfg

    def test_matches_factory_verbatim(self):
        """Every schema §2.3 field matches the installer's factory constant."""
        cfg = read_config(INSTALLED_PATH)

        def walk(expected: dict, actual: dict, trail: str = "") -> None:
            for k, v in expected.items():
                here = f"{trail}.{k}" if trail else k
                assert k in actual, f"missing key {here}"
                if isinstance(v, dict):
                    walk(v, actual[k], here)
                else:
                    assert actual[k] == v, f"{here}: expected {v}, got {actual[k]}"

        walk(SOURCING_RULES_FACTORY_DEFAULTS, cfg)
