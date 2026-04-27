"""Tests for GRAILZEE_ROOT env-var override in grailzee_common.

Three cases: default fall-through, override, and derived-path inheritance.
"""

from __future__ import annotations

import importlib
import os

import pytest

_DEFAULT_GRAILZEE_ROOT = (
    "/Users/ranbirchawla/Library/CloudStorage/"
    "GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/"
    "Vardalux Shared Drive/GrailzeeData"
)


class TestGrailzeeRootEnvVar:
    @pytest.fixture(autouse=True)
    def _restore_module(self):
        """Reload grailzee_common after each test.

        Monkeypatch reverts GRAILZEE_ROOT before this teardown runs (LIFO
        fixture order), so the pop is a no-op in normal operation. The
        try/finally ensures the env var is restored even if the reload
        itself throws; without it a failed reload would leave saved unset.
        """
        yield
        import scripts.grailzee_common as mod
        saved = os.environ.pop("GRAILZEE_ROOT", None)
        try:
            importlib.reload(mod)
        finally:
            if saved is not None:
                os.environ["GRAILZEE_ROOT"] = saved

    def test_grailzee_root_default(self, monkeypatch):
        """With GRAILZEE_ROOT unset, GRAILZEE_ROOT equals the hardcoded default."""
        monkeypatch.delenv("GRAILZEE_ROOT", raising=False)
        import scripts.grailzee_common as mod
        importlib.reload(mod)
        assert mod.GRAILZEE_ROOT == _DEFAULT_GRAILZEE_ROOT

    def test_grailzee_root_override(self, monkeypatch, tmp_path):
        """With GRAILZEE_ROOT set, the module constant reflects the override."""
        override = str(tmp_path / "test-grailzee-root")
        monkeypatch.setenv("GRAILZEE_ROOT", override)
        import scripts.grailzee_common as mod
        importlib.reload(mod)
        assert mod.GRAILZEE_ROOT == override
        assert mod.STATE_PATH == f"{override}/state"

    def test_derived_paths_inherit_override(self, monkeypatch, tmp_path):
        """REPORTS_PATH, STATE_PATH, and CACHE_PATH all anchor off the override."""
        override = str(tmp_path / "test-grailzee-root")
        monkeypatch.setenv("GRAILZEE_ROOT", override)
        import scripts.grailzee_common as mod
        importlib.reload(mod)
        assert mod.REPORTS_PATH.startswith(override)
        assert mod.STATE_PATH.startswith(override)
        assert mod.CACHE_PATH.startswith(override)
