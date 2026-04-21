"""Shared helpers for the installer main()/argparse tests.

Underscore-prefixed so pytest does not auto-collect it as a test module.
Used by test_installers_main_cli.py to parametrize across all six
Phase A installers without duplicating setup per file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


# Each spec describes one installer. ``default_root`` determines how
# the installer resolves its default target when --target is absent:
#   - "workspace": via scripts.grailzee_common.config_path(), which
#     reads WORKSPACE_STATE_PATH at call time.
#   - "drive": via the installer's own imported STATE_PATH constant
#     (bound at the installer's module-load time).
INSTALLER_SPECS: list[dict] = [
    {
        "id": "install_analyzer_config",
        "module": "scripts.install_analyzer_config",
        "default_name": "analyzer_config.json",
        "default_root": "workspace",
    },
    {
        "id": "install_brand_floors",
        "module": "scripts.install_brand_floors",
        "default_name": "brand_floors.json",
        "default_root": "workspace",
    },
    {
        "id": "install_sourcing_rules",
        "module": "scripts.install_sourcing_rules",
        "default_name": "sourcing_rules.json",
        "default_root": "workspace",
    },
    {
        "id": "install_cycle_focus",
        "module": "scripts.install_cycle_focus",
        "default_name": "cycle_focus.json",
        "default_root": "drive",
    },
    {
        "id": "install_monthly_goals",
        "module": "scripts.install_monthly_goals",
        "default_name": "monthly_goals.json",
        "default_root": "drive",
    },
    {
        "id": "install_quarterly_allocation",
        "module": "scripts.install_quarterly_allocation",
        "default_name": "quarterly_allocation.json",
        "default_root": "drive",
    },
]


def load_installer(module_path: str) -> ModuleType:
    return importlib.import_module(module_path)


def patch_default_root(monkeypatch, spec: dict, tmp_path: Path) -> Path:
    """Repoint the installer's default target resolution at tmp_path.

    Workspace installers read WORKSPACE_STATE_PATH from grailzee_common
    at call time; Drive installers bound STATE_PATH into their own
    module at import. Patch whichever the installer actually uses.

    Returns the default target path the installer will resolve when
    --target is absent.
    """
    mod = load_installer(spec["module"])
    if spec["default_root"] == "workspace":
        gc = importlib.import_module("scripts.grailzee_common")
        monkeypatch.setattr(gc, "WORKSPACE_STATE_PATH", str(tmp_path))
    else:
        monkeypatch.setattr(mod, "STATE_PATH", str(tmp_path))
    return tmp_path / spec["default_name"]


def run_main(monkeypatch, module_path: str, argv: list[str]) -> int:
    """Invoke the installer's main() with a spoofed sys.argv.

    Returns the int exit code from main(). argparse-raised SystemExit
    propagates to the caller (so --help / unknown-flag tests can
    introspect the exit code).
    """
    mod = load_installer(module_path)
    monkeypatch.setattr(sys, "argv", [module_path] + list(argv))
    return mod.main()
