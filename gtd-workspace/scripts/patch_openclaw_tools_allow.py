"""patch_openclaw_tools_allow.py

Operator one-shot: update GTD agent tools.allow in ~/.openclaw/openclaw.json.

Changes applied:
  "capture_gtd" -> "capture"
  "review_gtd"  -> "review"
  remove "delegation"

Confirmations (warn and exit 1 if absent after update):
  "trina_dispatch"  -- must be present (Phase 2)
  "get_today_date"  -- must be present (Phase 3a)

Usage:
  python patch_openclaw_tools_allow.py           # apply changes
  python patch_openclaw_tools_allow.py --dry-run  # preview; no write
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
GTD_AGENT_ID = "gtd"

RENAMES: dict[str, str] = {
    "capture_gtd": "capture",
    "review_gtd": "review",
}
REMOVE: frozenset[str] = frozenset({"delegation"})
# Tools that must be present; if absent they are ADDED (not just confirmed).
# trina_dispatch was added in Phase 2 and is already present.
# get_today_date was added in Phase 3a and may be missing from older allow lists.
ENSURE_PRESENT: tuple[str, ...] = ("trina_dispatch", "get_today_date")


# ---------------------------------------------------------------------------
# JSON navigation helpers
# ---------------------------------------------------------------------------

def _find_agent(config: dict) -> dict | None:
    """Return the GTD agent dict from any of three common OpenClaw structures.

      agents.list (nested):  config["agents"]["list"] = [{id: "gtd", ...}]
      agents as a list:      config["agents"] = [{id: "gtd", ...}]
      agents as a dict:      config["agents"] = {"gtd": {...}}
    """
    agents_raw = config.get("agents")
    if agents_raw is None:
        return None

    if isinstance(agents_raw, dict):
        # Check for the nested agents.list format first.
        agent_list = agents_raw.get("list")
        if isinstance(agent_list, list):
            return next((a for a in agent_list if a.get("id") == GTD_AGENT_ID), None)
        # Fall back to dict keyed by agent id.
        return agents_raw.get(GTD_AGENT_ID)

    if isinstance(agents_raw, list):
        return next((a for a in agents_raw if a.get("id") == GTD_AGENT_ID), None)

    return None


def _find_tools_allow(config: dict) -> list[str] | None:
    """Return the tools.allow list from the GTD agent entry."""
    agent = _find_agent(config)
    if agent is None:
        return None
    tools = agent.get("tools")
    if not isinstance(tools, dict):
        return None
    allow = tools.get("allow")
    if not isinstance(allow, list):
        return None
    return allow


def _set_tools_allow(config: dict, new_allow: list[str]) -> None:
    """Write new_allow back into the correct location in config (in-place)."""
    agent = _find_agent(config)
    assert agent is not None
    agent["tools"]["allow"] = new_allow


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_update(current: list[str]) -> tuple[list[str], list[str]]:
    """Return (updated_list, change_log_lines)."""
    updated: list[str] = []
    log: list[str] = []

    for tool in current:
        if tool in REMOVE:
            log.append(f"action=remove tool={tool!r}")
            continue
        if tool in RENAMES:
            new_name = RENAMES[tool]
            updated.append(new_name)
            log.append(f"action=rename tool={tool!r} new={new_name!r}")
        else:
            updated.append(tool)

    # Ensure required tools are present; add if missing.
    for required in ENSURE_PRESENT:
        if required in updated:
            log.append(f"action=confirm tool={required!r} status=present")
        else:
            updated.append(required)
            log.append(f"action=add tool={required!r} status=was_missing")

    return updated, log


def run(dry_run: bool) -> int:
    if not CONFIG_PATH.exists():
        print(f"error path={CONFIG_PATH} msg='file not found'", file=sys.stderr)
        return 1

    raw = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        config: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error path={CONFIG_PATH} msg='invalid JSON: {exc}'", file=sys.stderr)
        return 1

    current_allow = _find_tools_allow(config)
    if current_allow is None:
        print(
            f"error msg='could not locate agents[id={GTD_AGENT_ID!r}].tools.allow'",
            file=sys.stderr,
        )
        top_keys = list(config.keys())
        print(f"  hint: top-level keys={top_keys}", file=sys.stderr)
        return 1

    print(f"found agent={GTD_AGENT_ID!r} path={CONFIG_PATH}")
    print(f"  before: {current_allow}")

    updated, change_log = compute_update(current_allow)

    for line in change_log:
        print(f"  {line}")

    print(f"  after:  {updated}")

    if dry_run:
        print("dry-run: no changes written")
        return 0

    _set_tools_allow(config, updated)

    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, CONFIG_PATH)
    except OSError as exc:
        print(f"error msg='write failed: {exc}' tmp={tmp}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return 1

    print(f"ok written path={CONFIG_PATH}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    dry_run = "--dry-run" in sys.argv
    sys.exit(run(dry_run=dry_run))


if __name__ == "__main__":
    main()
