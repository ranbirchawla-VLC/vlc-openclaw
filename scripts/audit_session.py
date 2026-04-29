#!/usr/bin/env python3
"""audit_session.py — forensic tool-call audit for OpenClaw session JSONL files.

Usage:
    python3 audit_session.py <path-to-session.jsonl>
    python3 audit_session.py --latest <agent-name>

Examples:
    python3 audit_session.py ~/.openclaw/agents/nutriosv2/sessions/abc123.jsonl
    python3 audit_session.py --latest nutriosv2
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

AGENTS_DIR = Path.home() / ".openclaw" / "agents"

# Tools that should NEVER appear in a properly constrained agent
FORBIDDEN_TOOLS = {"exec", "read", "write", "edit", "browser", "canvas"}

# Registered tools for known agents (source of truth = openclaw.json)
REGISTERED_TOOLS = {
    "nutriosv2": {
        "turn_state",
        "compute_candidate_macros",
        "lock_mesocycle",
        "get_active_mesocycle",
        "recompute_macros_with_overrides",
        "estimate_macros_from_description",
        "write_meal_log",
        "get_daily_reconciled_view",
        "message",
    }
}


def find_latest_jsonl(agent_name: str) -> Path:
    sessions_dir = AGENTS_DIR / agent_name / "sessions"
    jsonl_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not jsonl_files:
        print(f"No active session found for agent: {agent_name}")
        sys.exit(1)
    return jsonl_files[0]


def parse_session(path: Path) -> list[dict]:
    events = []
    with open(path, "r") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [WARN] Line {i}: JSON parse error: {e}")
    return events


def extract_tool_calls(events: list[dict]) -> list[dict]:
    """Extract all tool calls and their results from session events."""
    calls = []
    result_map: dict[str, dict] = {}

    # First pass: collect all tool results keyed by toolCallId
    for event in events:
        msg = event.get("message", {})
        if msg.get("role") == "toolResult":
            call_id = msg.get("toolCallId", "")
            content = msg.get("content", [])
            text = ""
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    break
            result_map[call_id] = {
                "tool_name": msg.get("toolName", ""),
                "result_text": text[:300],
                "exit_code": msg.get("details", {}).get("exitCode"),
                "is_err": msg.get("isErr", False),
            }

    # Second pass: match tool calls to their results
    for event in events:
        msg = event.get("message", {})
        ts = event.get("timestamp", "")
        if msg.get("role") == "assistant":
            for block in msg.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "toolCall":
                    call_id = block.get("id", "")
                    tool_name = block.get("name", "")
                    args = block.get("arguments", {})
                    result = result_map.get(call_id, {})
                    calls.append({
                        "timestamp": ts,
                        "tool_name": tool_name,
                        "call_id": call_id,
                        "args": args,
                        "result_text": result.get("result_text", "[no result found]"),
                        "exit_code": result.get("exit_code"),
                        "is_err": result.get("is_err", False),
                    })

    return calls


def audit(path: Path, agent_name: str | None = None) -> None:
    registered = REGISTERED_TOOLS.get(agent_name, set()) if agent_name else set()

    print(f"\n{'='*70}")
    print(f"SESSION AUDIT: {path.name}")
    print(f"Agent:         {agent_name or 'unknown'}")
    print(f"Path:          {path}")
    print(f"{'='*70}\n")

    events = parse_session(path)
    calls = extract_tool_calls(events)

    if not calls:
        print("No tool calls found in session.\n")
        return

    forbidden_calls = []
    bypassed_calls = []
    registered_calls = []
    unknown_calls = []

    for call in calls:
        name = call["tool_name"]
        if name in FORBIDDEN_TOOLS:
            forbidden_calls.append(call)
        elif registered and name not in registered and name != "message":
            unknown_calls.append(call)
        else:
            registered_calls.append(call)

        # Detect exec bypass: exec calls that invoke python3 scripts
        if name == "exec":
            cmd = call["args"].get("command", "")
            if "python3" in cmd or "python" in cmd:
                bypassed_calls.append(call)

    # Summary
    print(f"SUMMARY")
    print(f"  Total tool calls:     {len(calls)}")
    print(f"  Registered tool calls: {len(registered_calls)}")
    print(f"  Forbidden tool calls:  {len(forbidden_calls)}  {'⚠️  VIOLATIONS' if forbidden_calls else '✅'}")
    print(f"  Exec→Python bypasses:  {len(bypassed_calls)}  {'⚠️  BYPASSES' if bypassed_calls else '✅'}")
    print(f"  Unknown tool calls:    {len(unknown_calls)}")
    print()

    # Forbidden / bypass violations
    if forbidden_calls:
        print(f"{'─'*70}")
        print(f"⚠️  FORBIDDEN TOOL CALLS ({len(forbidden_calls)})")
        print(f"{'─'*70}")
        for c in forbidden_calls:
            args_str = json.dumps(c["args"])[:120]
            result_preview = c["result_text"][:150].replace("\n", " ")
            exit_str = f"exit={c['exit_code']}" if c["exit_code"] is not None else ""
            err_flag = " ❌ ERROR" if c["is_err"] else ""
            print(f"  [{c['timestamp'][11:19]}] {c['tool_name']}{err_flag} {exit_str}")
            print(f"    args:   {args_str}")
            print(f"    result: {result_preview}")
            print()

    if bypassed_calls:
        print(f"{'─'*70}")
        print(f"⚠️  EXEC→PYTHON BYPASSES ({len(bypassed_calls)})")
        print(f"{'─'*70}")
        for c in bypassed_calls:
            cmd = c["args"].get("command", "")[:150]
            result_preview = c["result_text"][:150].replace("\n", " ")
            print(f"  [{c['timestamp'][11:19]}] exec → {cmd}")
            print(f"    result: {result_preview}")
            print()

    # All calls timeline
    print(f"{'─'*70}")
    print(f"FULL TOOL CALL TIMELINE ({len(calls)} calls)")
    print(f"{'─'*70}")
    for c in calls:
        name = c["tool_name"]
        ts = c["timestamp"][11:19] if c["timestamp"] else "??"
        flag = ""
        if name in FORBIDDEN_TOOLS:
            flag = " ⚠️ FORBIDDEN"
        elif registered and name not in registered and name != "message":
            flag = " ❓ UNKNOWN"
        err_flag = " ❌" if c["is_err"] else ""
        args_preview = json.dumps(c["args"])[:80]
        result_preview = c["result_text"][:100].replace("\n", " ")
        print(f"  [{ts}] {name}{flag}{err_flag}")
        print(f"    in:  {args_preview}")
        print(f"    out: {result_preview}")
        print()

    print(f"{'='*70}\n")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    agent_name = None

    if args[0] == "--latest":
        if len(args) < 2:
            print("Usage: audit_session.py --latest <agent-name>")
            sys.exit(1)
        agent_name = args[1]
        path = find_latest_jsonl(agent_name)
    else:
        path = Path(args[0]).expanduser()
        # Try to infer agent name from path
        parts = path.parts
        if "agents" in parts:
            idx = parts.index("agents")
            if idx + 1 < len(parts):
                agent_name = parts[idx + 1]

    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    audit(path, agent_name)


if __name__ == "__main__":
    main()
