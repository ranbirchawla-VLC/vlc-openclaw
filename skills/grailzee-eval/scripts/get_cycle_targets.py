"""get_cycle_targets — return the current cycle buying list.

Loads cycle_focus.json and returns the targets array plus cycle-level
metadata. No side effects.

Usage (plugin / JSON argv):
    python3 scripts/get_cycle_targets.py '{}'

Returns:
    {"ok": true,  "data": {"targets": [...], "capital_target": N, ...}}
    {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
V2_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(V2_ROOT))

from scripts.grailzee_common import attach_parent_trace_context, get_tracer, load_cycle_focus

tracer = get_tracer(__name__)


def get_cycle_targets(cycle_focus_path: str | None = None) -> dict:
    with attach_parent_trace_context(), tracer.start_as_current_span("get_cycle_targets.run") as span:
        focus = load_cycle_focus(cycle_focus_path)
        if focus is None:
            span.set_attribute("outcome", "missing")
            return {"ok": False, "error": "cycle_focus.json not found; run /report to generate it"}

        targets = focus.get("targets", [])
        span.set_attribute("targets_count", len(targets))
        span.set_attribute("outcome", "ok")

        return {
            "ok": True,
            "data": {
                "targets": targets,
                "capital_target": focus.get("capital_target"),
                "volume_target": focus.get("volume_target"),
                "brand_emphasis": focus.get("brand_emphasis", []),
                "brand_pullback": focus.get("brand_pullback", []),
                "notes": focus.get("notes", ""),
            },
        }


def main() -> None:
    try:
        raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
        json.loads(raw)  # validate; params unused
    except (IndexError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": f"Invalid argv: {e}"}))
        sys.exit(1)

    result = get_cycle_targets()
    print(json.dumps(result))
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
