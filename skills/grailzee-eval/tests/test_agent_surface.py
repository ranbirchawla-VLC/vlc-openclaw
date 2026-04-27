"""Config-surface validation tests for grailzee-eval agent.

Validates structural shape of:
  - skills/grailzee-eval/openclaw.json (agent-level tool registry)
  - ~/.openclaw/openclaw.json (root config: grailzee-eval entry + tools.allow)
  - skills/grailzee-eval/AGENTS.md (required sections and hard rules)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Resolve paths relative to this test file.
# test file: skills/grailzee-eval/tests/test_agent_surface.py
# parents[0] = tests/
# parents[1] = grailzee-eval/
# parents[2] = skills/
# parents[3] = vlc-openclaw/ (repo root)
_WORKSPACE = Path(__file__).resolve().parents[1]
_AGENT_OPENCLAW_JSON = _WORKSPACE / "openclaw.json"
_AGENTS_MD = _WORKSPACE / "AGENTS.md"
_ROOT_OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"

_EXPECTED_TOOLS = frozenset(
    {"evaluate_deal", "report_pipeline", "ledger_manager", "message"}
)


class TestAgentOpenclawJson:
    def test_agent_openclaw_json_valid(self):
        """Workspace openclaw.json parses as valid JSON with exactly four tool entries."""
        assert _AGENT_OPENCLAW_JSON.exists(), f"{_AGENT_OPENCLAW_JSON} not found"
        data = json.loads(_AGENT_OPENCLAW_JSON.read_text())

        assert "tools" in data, "top-level 'tools' key missing"
        tools = data["tools"]
        assert isinstance(tools, list), "'tools' must be a list"
        assert len(tools) == 4, f"expected 4 tool entries, got {len(tools)}"

        for t in tools:
            assert "name" in t, f"tool entry missing 'name' field: {t}"

        tool_names = {t["name"] for t in tools}
        assert tool_names == _EXPECTED_TOOLS, (
            f"tool names mismatch: expected {_EXPECTED_TOOLS}, got {tool_names}"
        )


@pytest.mark.skipif(
    not _ROOT_OPENCLAW_JSON.exists(),
    reason="~/.openclaw/openclaw.json not present on this machine",
)
class TestRootOpenclawGrailzeeEvalEntry:
    def test_root_openclaw_grailzee_eval_entry(self):
        """Root openclaw.json grailzee-eval entry has tools.allow and env.GRAILZEE_ROOT."""
        data = json.loads(_ROOT_OPENCLAW_JSON.read_text())

        agents = data.get("agents", {}).get("list", [])
        entry = next((a for a in agents if a.get("id") == "grailzee-eval"), None)
        assert entry is not None, (
            "grailzee-eval agent entry not found in root openclaw.json agents.list"
        )
        assert entry["id"] == "grailzee-eval"

        tools_allow = entry.get("tools", {}).get("allow", [])
        assert set(tools_allow) == _EXPECTED_TOOLS, (
            f"tools.allow mismatch: expected {_EXPECTED_TOOLS}, got {set(tools_allow)}"
        )
        assert len(tools_allow) == len(_EXPECTED_TOOLS), (
            f"tools.allow has duplicate entries: {tools_allow}"
        )

        env = entry.get("env", {})
        assert "GRAILZEE_ROOT" in env, (
            "env.GRAILZEE_ROOT not declared in grailzee-eval root entry"
        )


class TestAgentsMd:
    def test_agents_md_required_sections(self):
        """AGENTS.md has required sections and Hard Rules content."""
        assert _AGENTS_MD.exists(), f"{_AGENTS_MD} not found"
        content = _AGENTS_MD.read_text()

        for header in ("## Identity", "## Tools Available", "## Hard Rules"):
            assert header in content, f"'{header}' section missing from AGENTS.md"

        assert "exec, read, write, edit, browser, canvas do not exist" in content, (
            "Hard Rules must state "
            "'exec, read, write, edit, browser, canvas do not exist'"
        )
