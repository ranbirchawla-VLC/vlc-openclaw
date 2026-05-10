"""LLM tests for capability user_id parameter passing.

4 fixtures at temperature=0, claude-sonnet-4-6, 3x require-all-pass via run_llm_3x.py.
Picked up automatically by make test-gtd-llm.

Uses real capability files from gtd-workspace/capabilities/ (not the LLM test stubs).

What is under test:
  The capability prompts for calendar_write and contacts instruct the LLM to
  pass sender_id as user_id when calling cancel_event, update_event,
  search_contacts, and create_contact. Prior to the instructions in this
  branch, those four tools had no mention of user_id in their workflow steps;
  the LLM consistently omitted the parameter in production.

Gate report answers:
  1. Each test reproduces the production failure mode named in its docstring.
  2. RED confirmed before capability fixes: reverted calendar_write.md /
     contacts.md to pre-branch state; all four tests failed with
     "user_id missing from <tool> call" within the first run.
  3. Model: claude-sonnet-4-6. Temperature: 0. Matches production GTD agent
     config (mnemo/claude-sonnet-4-6 in ~/.openclaw/openclaw.json).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths resolved relative to this file; no env-var dependency.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2])   # gtd-workspace/scripts/
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_CAPABILITIES_DIR = Path(__file__).resolve().parents[3] / "capabilities"       # gtd-workspace/capabilities/
_TOOLS_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "plugins" / "gtd-tools" / "tools.schema.json"

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0
_MAX_TOKENS = 512
_TEST_USER_ID = "8712103657"

# Simulated gateway conversation metadata as the agent receives it.
_METADATA_BLOCK = f'{{"sender_id": "{_TEST_USER_ID}", "chat_type": "private"}}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_capability(name: str) -> str:
    return (_CAPABILITIES_DIR / f"{name}.md").read_text(encoding="utf-8")


def _anthropic_tool(tool_name: str) -> dict:
    """Load tool definition from committed tools.schema.json; map inputSchema -> input_schema."""
    data = json.loads(_TOOLS_SCHEMA_PATH.read_text(encoding="utf-8"))
    entry = next(t for t in data["tools"] if t["name"] == tool_name)
    return {
        "name": entry["name"],
        "description": entry["description"],
        "input_schema": entry["inputSchema"],
    }


def _call_tool(capability_name: str, tool_name: str, user_message: str) -> dict:
    """Invoke the LLM with the real capability as system prompt and a single tool.

    Returns the tool_use input dict. Skips if no API key is available.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("no API key")

    capability = _load_capability(capability_name)
    tool = _anthropic_tool(tool_name)

    # System prompt: real capability content only.
    # Sender identity comes from the user message metadata block (mirrors gateway format).
    system = capability

    client = anthropic.Anthropic(api_key=api_key, base_url="https://api.anthropic.com")
    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        system=system,
        messages=[
            {
                "role": "user",
                "content": f"[Conversation metadata: {_METADATA_BLOCK}]\n\n{user_message}",
            }
        ],
        tools=[tool],
    )

    tool_use = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    assert tool_use is not None, (
        f"LLM did not call {tool_name}. Stop reason: {response.stop_reason}. "
        f"Content: {[b.type for b in response.content]}"
    )
    return tool_use.input


# ---------------------------------------------------------------------------
# Test 1: cancel_event passes user_id
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_cancel_event_passes_user_id() -> None:
    """cancel_event workflow in calendar_write.md instructs LLM to include user_id.

    Production failure: LLM omits user_id from cancel_event call; span attribute
    user.id is always empty; cancellations are unattributable in Honeycomb.
    """
    params = _call_tool(
        capability_name="calendar_write",
        tool_name="cancel_event",
        user_message="Cancel the event with ID 'cal-evt-abc123'.",
    )
    assert "user_id" in params, f"user_id missing from cancel_event call. Params: {params}"
    assert params["user_id"] == _TEST_USER_ID, (
        f"user_id wrong: expected {_TEST_USER_ID!r}, got {params['user_id']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: update_event passes user_id
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_update_event_passes_user_id() -> None:
    """update_event workflow in calendar_write.md instructs LLM to include user_id.

    Production failure: LLM omits user_id from update_event call; span attribute
    user.id is always empty; updates are unattributable in Honeycomb.
    """
    params = _call_tool(
        capability_name="calendar_write",
        tool_name="update_event",
        user_message="Update event ID 'cal-evt-xyz789' — change the title to 'Project Kickoff'.",
    )
    assert "user_id" in params, f"user_id missing from update_event call. Params: {params}"
    assert params["user_id"] == _TEST_USER_ID, (
        f"user_id wrong: expected {_TEST_USER_ID!r}, got {params['user_id']!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: search_contacts passes user_id
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_search_contacts_passes_user_id() -> None:
    """search_contacts workflow in contacts.md instructs LLM to include user_id.

    Production failure: LLM omits user_id from search_contacts call; span
    attribute user.id is always empty; contact lookups are unattributable.
    """
    params = _call_tool(
        capability_name="contacts",
        tool_name="search_contacts",
        user_message="Find Heather's email address.",
    )
    assert "user_id" in params, f"user_id missing from search_contacts call. Params: {params}"
    assert params["user_id"] == _TEST_USER_ID, (
        f"user_id wrong: expected {_TEST_USER_ID!r}, got {params['user_id']!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: create_contact passes user_id
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_create_contact_passes_user_id() -> None:
    """create_contact workflow in contacts.md instructs LLM to include user_id.

    Production failure: LLM omits user_id from create_contact call; span
    attribute user.id is always empty; contact creations are unattributable.
    """
    params = _call_tool(
        capability_name="contacts",
        tool_name="create_contact",
        user_message="Add Sarah Chen, email sarah@chen.com, to my contacts.",
    )
    assert "user_id" in params, f"user_id missing from create_contact call. Params: {params}"
    assert params["user_id"] == _TEST_USER_ID, (
        f"user_id wrong: expected {_TEST_USER_ID!r}, got {params['user_id']!r}"
    )
