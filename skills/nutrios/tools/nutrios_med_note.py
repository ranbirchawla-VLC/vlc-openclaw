"""nutrios_med_note.py — append a med note or view protocol+recent notes (6/10).

Two actions:
    add  — append MedNote to med_notes.jsonl, return render_med_note_confirm
    view — return render_protocol_view with the last 3 notes appended
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nutrios_models import MedNote, Protocol, ToolResult
import nutrios_render as render
import nutrios_store as store


class MedNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    action: Literal["add", "view"]
    note_text: str | None = None
    source: Literal["doctor", "dietitian", "nurse", "self", "other"] = "self"
    now: datetime
    tz: str


def _add(inp: MedNoteInput) -> ToolResult:
    if not inp.note_text or not inp.note_text.strip():
        # Empty-text add is a true input error — the LLM should not have called
        # this without text. Raise rather than render: this is an internal
        # invariant violation, not a user-facing scenario.
        raise ValueError("note_text is required and must be non-empty for action=add")

    new_id = store.next_id(inp.user_id, "last_med_note_id")
    ts_iso = inp.now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    note = MedNote(
        id=new_id,
        ts_iso=ts_iso,
        source=inp.source,
        note=inp.note_text.strip(),
    )
    store.append_jsonl(inp.user_id, "med_notes.jsonl", note)
    return ToolResult(
        display_text=render.render_med_note_confirm(note),
        state_delta={"last_med_note_id": new_id},
    )


def _view(inp: MedNoteInput) -> ToolResult:
    protocol = store.read_json(inp.user_id, "protocol.json", Protocol)
    if protocol is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())
    raw = store.read_jsonl_all(inp.user_id, "med_notes.jsonl")
    notes = [MedNote.model_validate(r) for r in raw]
    recent = notes[-3:] if notes else []
    return ToolResult(display_text=render.render_protocol_view(protocol, recent))


def main(argv_json: str) -> ToolResult:
    inp = MedNoteInput.model_validate_json(argv_json)
    match inp.action:
        case "add":
            return _add(inp)
        case "view":
            return _view(inp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_med_note '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
