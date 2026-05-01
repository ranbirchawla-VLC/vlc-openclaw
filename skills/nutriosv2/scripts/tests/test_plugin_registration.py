"""Registration tests for the nutriosv2-tools plugin and tools.allow surface.

Tests read two canonical artifacts:
- plugins/nutriosv2-tools/tools.schema.json (committed; single source of truth for tool schemas)
- ~/.openclaw/openclaw.json (runtime config; nutriosv2 tools.allow list)

No mocking of the plugin JS layer. Assertions are on file content only.
"""

from __future__ import annotations
import json
from pathlib import Path

import pytest

_WORKSPACE = Path(__file__).parent.parent.parent.parent.parent  # workspace root
_TOOLS_SCHEMA = _WORKSPACE / "plugins" / "nutriosv2-tools" / "tools.schema.json"
_OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def _load_schema_tools() -> list[dict]:
    return json.loads(_TOOLS_SCHEMA.read_text())["tools"]


def _load_allow_list() -> list[str]:
    config = json.loads(_OPENCLAW_CONFIG.read_text())
    agents = config["agents"]["list"]
    for agent in agents:
        if isinstance(agent, dict) and agent.get("id") == "nutriosv2":
            return agent.get("tools", {}).get("allow", [])
    pytest.fail("nutriosv2 agent not found in ~/.openclaw/openclaw.json")


def _find_tool(tools: list[dict], name: str) -> dict | None:
    return next((t for t in tools if t["name"] == name), None)


# ---------------------------------------------------------------------------
# log_meal_items: manifest presence and schema
# ---------------------------------------------------------------------------


def test_log_meal_items_in_plugin_manifest() -> None:
    """log_meal_items appears in tools.schema.json."""
    tools = _load_schema_tools()
    assert _find_tool(tools, "log_meal_items") is not None, (
        "log_meal_items not found in tools.schema.json"
    )


def test_log_meal_items_schema_required_fields() -> None:
    """log_meal_items inputSchema requires user_id (integer) and items."""
    tools = _load_schema_tools()
    tool = _find_tool(tools, "log_meal_items")
    assert tool is not None
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert "user_id" in schema["properties"]
    assert schema["properties"]["user_id"]["type"] == "integer"
    assert "items" in schema["properties"]
    assert set(schema["required"]) == {"user_id", "items"}


def test_log_meal_items_items_property_schema() -> None:
    """log_meal_items items property is an array; each element has description and portion required."""
    tools = _load_schema_tools()
    tool = _find_tool(tools, "log_meal_items")
    assert tool is not None
    items_prop = tool["inputSchema"]["properties"]["items"]
    assert items_prop["type"] == "array"
    item_schema = items_prop["items"]
    assert "description" in item_schema["properties"]
    assert "portion" in item_schema["properties"]
    assert set(item_schema["required"]) == {"description", "portion"}
    assert item_schema["properties"]["description"]["type"] == "string"
    assert item_schema["properties"]["portion"]["type"] == "number"


def test_log_meal_items_in_tools_allow() -> None:
    """log_meal_items appears in the nutriosv2 tools.allow list."""
    allow = _load_allow_list()
    assert "log_meal_items" in allow, (
        f"log_meal_items not in tools.allow; current list: {allow}"
    )


# ---------------------------------------------------------------------------
# Preservation: estimate_macros_from_description and calculate_macros
# ---------------------------------------------------------------------------


def test_estimate_macros_from_description_remains_in_manifest() -> None:
    """estimate_macros_from_description still present in tools.schema.json after log_meal_items registration."""
    tools = _load_schema_tools()
    assert _find_tool(tools, "estimate_macros_from_description") is not None


def test_estimate_macros_from_description_remains_in_tools_allow() -> None:
    """estimate_macros_from_description still in tools.allow after log_meal_items registration."""
    allow = _load_allow_list()
    assert "estimate_macros_from_description" in allow


def test_calculate_macros_remains_in_manifest() -> None:
    """calculate_macros still present in tools.schema.json after log_meal_items registration."""
    tools = _load_schema_tools()
    assert _find_tool(tools, "calculate_macros") is not None


def test_calculate_macros_remains_in_tools_allow() -> None:
    """calculate_macros still in tools.allow after log_meal_items registration."""
    allow = _load_allow_list()
    assert "calculate_macros" in allow


# ---------------------------------------------------------------------------
# get_today_date: manifest presence, schema, and allowlist
# ---------------------------------------------------------------------------


def test_get_today_date_in_plugin_manifest() -> None:
    """get_today_date appears in tools.schema.json."""
    tools = _load_schema_tools()
    assert _find_tool(tools, "get_today_date") is not None, (
        "get_today_date not found in tools.schema.json"
    )


def test_get_today_date_schema_empty_required() -> None:
    """get_today_date inputSchema has no required fields (tool takes no input)."""
    tools = _load_schema_tools()
    tool = _find_tool(tools, "get_today_date")
    assert tool is not None
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert schema.get("required", []) == []


def test_get_today_date_in_tools_allow() -> None:
    """get_today_date appears in the nutriosv2 tools.allow list."""
    allow = _load_allow_list()
    assert "get_today_date" in allow, (
        f"get_today_date not in tools.allow; current list: {allow}"
    )


def test_get_today_date_in_tool_schemas_js() -> None:
    """get_today_date entry exists in tool-schemas.js with _spawn: argv."""
    schemas_js = _WORKSPACE / "plugins" / "nutriosv2-tools" / "tool-schemas.js"
    content = schemas_js.read_text()
    assert '"get_today_date"' in content, (
        "get_today_date not found in tool-schemas.js"
    )
    # _spawn drives execution; verify it is present alongside the tool name.
    assert '_spawn: "argv"' in content, (
        "_spawn: argv not found in tool-schemas.js"
    )


# ---------------------------------------------------------------------------
# Preservation: log_meal_items still present after get_today_date registration
# ---------------------------------------------------------------------------


def test_log_meal_items_remains_in_manifest() -> None:
    """log_meal_items still present in tools.schema.json after get_today_date registration."""
    tools = _load_schema_tools()
    assert _find_tool(tools, "log_meal_items") is not None


def test_log_meal_items_remains_in_tools_allow() -> None:
    """log_meal_items still in tools.allow after get_today_date registration."""
    allow = _load_allow_list()
    assert "log_meal_items" in allow
