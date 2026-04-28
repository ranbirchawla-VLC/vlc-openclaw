"""Plugin package shape, Path A absence, and root config shape tests for 1c.

Covers:
- grailzee-eval-tools plugin package structure (package.json, openclaw.plugin.json, index.js)
- Path A absence (workspace openclaw.json deleted, specific test functions deleted)
- Root openclaw.json grailzee-eval entry shape post-1c (tools.allow narrowed, plugin wired)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent
_SKILLS_DIR = _SKILL_DIR.parent
_REPO_ROOT = _SKILLS_DIR.parent

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "grailzee-eval-tools"
_PLUGIN_PATH_STR = str(_PLUGIN_DIR)
_ROOT_OPENCLAW = Path.home() / ".openclaw" / "openclaw.json"

_AGENT_SURFACE_TEST = _SKILL_DIR / "tests" / "test_agent_surface.py"

_1C_TOOLS_ALLOW = frozenset({"evaluate_deal", "message"})


# ─── Plugin package shape ────────────────────────────────────────────


class TestPluginPackageShape:
    def test_package_json_parses_type_module(self):
        pkg_path = _PLUGIN_DIR / "package.json"
        assert pkg_path.exists(), f"{pkg_path} not found"
        pkg = json.loads(pkg_path.read_text())
        assert pkg.get("type") == "module", "package.json must declare 'type': 'module'"

    def test_package_json_openclaw_compat_block(self):
        pkg = json.loads((_PLUGIN_DIR / "package.json").read_text())
        oc = pkg.get("openclaw", {})
        assert "compat" in oc, "package.json missing openclaw.compat block"
        compat = oc["compat"]
        assert "pluginApi" in compat, "openclaw.compat missing pluginApi"
        assert "minGatewayVersion" in compat, "openclaw.compat missing minGatewayVersion"

    def test_openclaw_plugin_json_id(self):
        opj_path = _PLUGIN_DIR / "openclaw.plugin.json"
        assert opj_path.exists(), f"{opj_path} not found"
        opj = json.loads(opj_path.read_text())
        assert opj.get("id") == "grailzee-eval-tools", (
            f"openclaw.plugin.json id must be 'grailzee-eval-tools', got {opj.get('id')!r}"
        )

    def test_index_js_exists_nonempty(self):
        js_path = _PLUGIN_DIR / "index.js"
        assert js_path.exists(), f"{js_path} not found"
        assert js_path.stat().st_size > 0, "index.js is empty"

    def test_index_js_exports_define_plugin_entry(self):
        content = (_PLUGIN_DIR / "index.js").read_text()
        assert "definePluginEntry" in content, (
            "index.js must export via definePluginEntry"
        )

    def test_index_js_registers_evaluate_deal(self):
        content = (_PLUGIN_DIR / "index.js").read_text()
        assert "evaluate_deal" in content, (
            "index.js must register evaluate_deal tool"
        )


# ─── Plugin dispatch method ───────────────────────────────────────────


class TestIndexJsDispatch:
    """Verify evaluate_deal uses spawnArgv (not spawnStdin) after 1c.5."""

    def test_evaluate_deal_uses_spawnargv(self):
        content = (_PLUGIN_DIR / "index.js").read_text()
        assert 'spawnArgv("evaluate_deal.py"' in content, (
            "evaluate_deal registration must use spawnArgv (1c.5 fixup)"
        )

    def test_evaluate_deal_not_spawntdin(self):
        content = (_PLUGIN_DIR / "index.js").read_text()
        assert 'spawnStdin("evaluate_deal.py"' not in content, (
            "evaluate_deal registration must not use spawnStdin after 1c.5"
        )


# ─── Path A absence ──────────────────────────────────────────────────


class TestPathAAbsence:
    def test_workspace_openclaw_json_deleted(self):
        workspace_openclaw = _SKILL_DIR / "openclaw.json"
        assert not workspace_openclaw.exists(), (
            f"{workspace_openclaw} must be deleted in 1c (Path A removal)"
        )

    def test_test_agent_openclaw_json_valid_removed(self):
        content = _AGENT_SURFACE_TEST.read_text()
        assert "def test_agent_openclaw_json_valid" not in content, (
            "test_agent_openclaw_json_valid must be removed from test_agent_surface.py"
        )

    def test_test_agents_md_required_sections_removed(self):
        content = _AGENT_SURFACE_TEST.read_text()
        assert "def test_agents_md_required_sections" not in content, (
            "test_agents_md_required_sections must be removed from test_agent_surface.py"
        )

    def test_root_openclaw_grailzee_eval_entry_still_present(self):
        content = _AGENT_SURFACE_TEST.read_text()
        assert "test_root_openclaw_grailzee_eval_entry" in content, (
            "test_root_openclaw_grailzee_eval_entry must remain in test_agent_surface.py"
        )


# ─── Root config shape ────────────────────────────────────────────────


@pytest.mark.skipif(
    not _ROOT_OPENCLAW.exists(),
    reason="~/.openclaw/openclaw.json not present on this machine",
)
class TestRootConfigShape:
    def _grailzee_entry(self) -> dict:
        data = json.loads(_ROOT_OPENCLAW.read_text())
        agents = data.get("agents", {}).get("list", [])
        entry = next((a for a in agents if a.get("id") == "grailzee-eval"), None)
        assert entry is not None, "grailzee-eval entry not found in root openclaw.json"
        return entry

    def test_tools_allow_exact(self):
        entry = self._grailzee_entry()
        tools_allow = set(entry.get("tools", {}).get("allow", []))
        assert tools_allow == _1C_TOOLS_ALLOW, (
            f"tools.allow must be exactly {_1C_TOOLS_ALLOW}, got {tools_allow}"
        )

    def test_no_tools_deny(self):
        entry = self._grailzee_entry()
        assert "deny" not in entry.get("tools", {}), (
            "grailzee-eval tools must not have a deny block (allowlist-only per §4.7)"
        )

    def test_plugins_entries_contains_grailzee_eval_tools(self):
        data = json.loads(_ROOT_OPENCLAW.read_text())
        entries = data.get("plugins", {}).get("entries", {})
        assert "grailzee-eval-tools" in entries, (
            "plugins.entries must contain 'grailzee-eval-tools'"
        )

    def test_plugins_load_paths_contains_plugin_dir(self):
        data = json.loads(_ROOT_OPENCLAW.read_text())
        paths = data.get("plugins", {}).get("load", {}).get("paths", [])
        assert _PLUGIN_PATH_STR in paths, (
            f"plugins.load.paths must contain {_PLUGIN_PATH_STR!r}"
        )
