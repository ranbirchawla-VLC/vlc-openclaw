"""Add turn_state to grailzee-eval tools.allow in ~/.openclaw/openclaw.json.

Idempotent. Writes atomically via a temp file + os.rename.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"
AGENT_ID = "grailzee-eval"
TOOL_TO_ADD = "turn_state"


def main() -> None:
    if not OPENCLAW_JSON.exists():
        print(f"ERROR: {OPENCLAW_JSON} not found", file=sys.stderr)
        sys.exit(1)

    data = json.loads(OPENCLAW_JSON.read_text())

    agents = data.get("agents", {}).get("list", [])
    entry = next((a for a in agents if a.get("id") == AGENT_ID), None)
    if entry is None:
        print(f"ERROR: agent '{AGENT_ID}' not found in {OPENCLAW_JSON}", file=sys.stderr)
        sys.exit(1)

    allow: list[str] = entry.setdefault("tools", {}).setdefault("allow", [])

    if TOOL_TO_ADD in allow:
        print(f"No-op: '{TOOL_TO_ADD}' already in {AGENT_ID} tools.allow")
        print(f"Current allow: {allow}")
        return

    allow.append(TOOL_TO_ADD)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=OPENCLAW_JSON.parent, suffix=".json.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.rename(tmp_path, OPENCLAW_JSON)
    except Exception:
        os.unlink(tmp_path)
        raise

    print(f"Updated {OPENCLAW_JSON}")
    print(f"  {AGENT_ID} tools.allow: {allow}")


if __name__ == "__main__":
    main()
