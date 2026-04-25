"""nutrios_protocol_edit.py — gated protocol edits (9/10).

Same gating posture as nutrios_write's protocol scope: routes through
engine.protected_gate_protocol with the confirm phrase. Edits to non-
protected fields (e.g. clinical.gallbladder_status) pass through without
a phrase. Edits to protected fields (dose_mg, dose_day_of_week) require
the exact "confirm protocol change" phrase.

Used directly by setup_resume's gallbladder marker (non-protected pass-
through) and by orchestrator routing for any standalone protocol edit.

This tool keeps its own copy of the gate-and-write flow rather than
delegating to nutrios_write — both surfaces are first-class entry points
for the orchestrator and the duplication is two short functions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from nutrios_models import Protocol, ToolResult
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store


class ProtocolEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    payload: Protocol
    confirm: str | None = None
    now: datetime
    tz: str


def apply_protocol_edit(user_id: str, proposed: Protocol, confirm: str | None) -> ToolResult:
    """Pure helper: gate-then-write. Both main() and setup_resume call this.

    Exposed so nutrios_setup_resume can route the gallbladder marker
    through the same gate path without going through JSON argv parsing.
    """
    current = store.read_json(user_id, "protocol.json", Protocol)
    if current is None:
        store.write_json(user_id, "protocol.json", proposed)
        return ToolResult(display_text=render.render_write_confirm("protocol"))

    gate = engine.protected_gate_protocol(current, proposed, confirm or "")
    if not gate.ok:
        return ToolResult(
            display_text=render.render_gate_error(gate),
            needs_followup=True,
        )
    store.write_json(user_id, "protocol.json", proposed)
    return ToolResult(display_text=render.render_write_confirm("protocol"))


def main(argv_json: str) -> ToolResult:
    inp = ProtocolEditInput.model_validate_json(argv_json)
    return apply_protocol_edit(inp.user_id, inp.payload, inp.confirm)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_protocol_edit '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
