"""Tests for scripts.install_analyzer_config.

Covers the installer's two guardrails: refuse-overwrite and --force.
Installs into tmp_path to keep tests hermetic.
"""

from __future__ import annotations

import json

from scripts.config_helper import leaf_paths, read_config
from scripts.grailzee_common import ANALYZER_CONFIG_FACTORY_DEFAULTS
from scripts.install_analyzer_config import install


class TestInstall:
    def test_install_to_empty_path_succeeds(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        rc = install(str(target), force=False, dry_run=False)
        assert rc == 0
        assert target.exists()

        parsed = read_config(target)
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_defaulted_fields_covers_every_leaf(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        install(str(target), force=False, dry_run=False)
        parsed = read_config(target)
        expected = sorted(leaf_paths(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        assert parsed["defaulted_fields"] == expected

    def test_refuse_overwrite_by_default(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        install(str(target), force=False, dry_run=False)
        # Mutate the file so we can tell if it got clobbered
        original = json.loads(target.read_text())
        sentinel = json.loads(target.read_text())
        sentinel["margin"]["per_trade_target_margin_fraction"] = 0.99
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=False, dry_run=False)
        assert rc == 1

        # File preserved (not clobbered)
        after = json.loads(target.read_text())
        assert after["margin"]["per_trade_target_margin_fraction"] == 0.99
        # Not the factory value again
        assert (
            after["margin"]["per_trade_target_margin_fraction"]
            != original["margin"]["per_trade_target_margin_fraction"]
        )

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        install(str(target), force=False, dry_run=False)
        sentinel = json.loads(target.read_text())
        sentinel["margin"]["per_trade_target_margin_fraction"] = 0.99
        target.write_text(json.dumps(sentinel))

        rc = install(str(target), force=True, dry_run=False)
        assert rc == 0

        after = json.loads(target.read_text())
        assert after["margin"]["per_trade_target_margin_fraction"] == 0.05

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 0
        assert not target.exists()

    def test_dry_run_refuses_if_existing_without_force(self, tmp_path):
        target = tmp_path / "analyzer_config.json"
        install(str(target), force=False, dry_run=False)
        rc = install(str(target), force=False, dry_run=True)
        assert rc == 1

    def test_leaf_paths_excludes_managed_keys(self):
        d = {
            "schema_version": 1,
            "last_updated": "x",
            "updated_by": "y",
            "defaulted_fields": [],
            "margin": {"per_trade_target_margin_fraction": 0.05},
            "scoring": {
                "signal_thresholds": {"strong_max_risk_pct": 10},
            },
        }
        paths = leaf_paths(d)
        assert "margin.per_trade_target_margin_fraction" in paths
        assert "scoring.signal_thresholds.strong_max_risk_pct" in paths
        for managed in ("schema_version", "last_updated", "updated_by", "defaulted_fields"):
            assert managed not in paths
            assert not any(p.startswith(managed) for p in paths)
