"""LLM test fixtures — loads real agent config and capability prompt."""

from __future__ import annotations
import json
import os
from pathlib import Path

import anthropic
import pytest

_WORKSPACE = Path(__file__).parent.parent.parent.parent  # skills/nutriosv2/
_OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def _load_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    if _OPENCLAW_CONFIG.exists():
        config = json.loads(_OPENCLAW_CONFIG.read_text())
        try:
            return config["models"]["providers"]["mnemo"]["apiKey"]
        except KeyError:
            pass
    pytest.skip(
        "ANTHROPIC_API_KEY not set and no key found at ~/.openclaw/openclaw.json — LLM tests cannot run"
    )


def _build_system_prompt() -> str:
    parts = []
    for fname in ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md", "USER.md", "SKILL.md"]:
        p = _WORKSPACE / fname
        if p.exists():
            parts.append(p.read_text())
    capability = _WORKSPACE / "capabilities" / "mesocycle_setup.md"
    if capability.exists():
        parts.append(capability.read_text())
    return "\n\n---\n\n".join(parts)


def _build_tools() -> list[dict]:
    config = json.loads((_WORKSPACE / "openclaw.json").read_text())
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["inputSchema"],
        }
        for t in config.get("tools", [])
    ]


@pytest.fixture(scope="session")
def llm_client() -> anthropic.Anthropic:
    key = _load_api_key()
    # Use real Anthropic API — mnemo proxy has a body-read bug that blocks test calls
    return anthropic.Anthropic(api_key=key)


@pytest.fixture(scope="session")
def agent_system_prompt() -> str:
    return _build_system_prompt()


@pytest.fixture(scope="session")
def agent_tools() -> list[dict]:
    return _build_tools()
