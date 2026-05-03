"""Root config surface validation for grailzee-eval agent.

Validates the grailzee-eval entry in ~/.openclaw/openclaw.json after G:
- tools.allow: evaluate_deal, report_pipeline, message
- no tools.deny block
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT_OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"

_1C_TOOLS_ALLOW = frozenset({"evaluate_deal", "report_pipeline", "message"})


@pytest.mark.skipif(
    not _ROOT_OPENCLAW_JSON.exists(),
    reason="~/.openclaw/openclaw.json not present on this machine",
)
class TestRootOpenclawGrailzeeEvalEntry:
    def test_root_openclaw_grailzee_eval_entry(self):
        """Root openclaw.json grailzee-eval entry has narrowed tools.allow and no deny block."""
        data = json.loads(_ROOT_OPENCLAW_JSON.read_text())

        agents = data.get("agents", {}).get("list", [])
        entry = next((a for a in agents if a.get("id") == "grailzee-eval"), None)
        assert entry is not None, (
            "grailzee-eval agent entry not found in root openclaw.json agents.list"
        )
        assert entry["id"] == "grailzee-eval"

        tools_allow = set(entry.get("tools", {}).get("allow", []))
        assert tools_allow == _1C_TOOLS_ALLOW, (
            f"tools.allow mismatch: expected {_1C_TOOLS_ALLOW}, got {tools_allow}"
        )
        assert len(entry.get("tools", {}).get("allow", [])) == len(_1C_TOOLS_ALLOW), (
            f"tools.allow has duplicate entries: {entry.get('tools', {}).get('allow', [])}"
        )

        assert "deny" not in entry.get("tools", {}), (
            "grailzee-eval must not have a tools.deny block (allowlist-only)"
        )
