"""nutrios_event.py — events lifecycle entrypoint (7/10).

Three actions:
    add     — append a new Event, write the full events.json
    list    — engine.event_next + render_event_list
    remove  — soft-delete (removed=True) via full events.json rewrite (D3)

events.json is a JSON-list-in-wrapper, not JSONL — the wrapped format from
store.read_events / write_events is the contract. Removal is a value flip
on Event.removed plus a full rewrite. Engine event_next / event_today /
advisory_flags already filter removed=True.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import date as date_type, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nutrios_models import Event, ToolResult
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store


_EVENT_TYPES = Literal[
    "surgery",
    "medication_change",
    "medication_stop",
    "medication_restart",
    "appointment",
    "milestone",
    "other",
]


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    action: Literal["add", "list", "remove"]
    now: datetime
    tz: str
    # add fields
    event_date: date_type | None = None
    event_type: _EVENT_TYPES | None = None
    title: str | None = None
    notes: str | None = None
    # list fields
    n: int = 2
    # remove fields
    id: int | None = None


def _add(inp: EventInput) -> ToolResult:
    if inp.event_date is None or inp.event_type is None or inp.title is None:
        raise ValueError(
            "action=add requires event_date, event_type, and title fields"
        )
    new_id = store.next_id(inp.user_id, "last_event_id")
    event = Event(
        id=new_id,
        date=inp.event_date,
        title=inp.title,
        event_type=inp.event_type,
        notes=inp.notes,
    )
    existing = store.read_events(inp.user_id)
    existing.append(event)
    store.write_events(inp.user_id, existing)
    return ToolResult(
        display_text=render.render_event_added(event),
        state_delta={"last_event_id": new_id},
    )


def _list(inp: EventInput) -> ToolResult:
    events = store.read_events(inp.user_id)
    upcoming = engine.event_next(events, inp.now, inp.tz, n=inp.n)
    return ToolResult(display_text=render.render_event_list(upcoming))


def _remove(inp: EventInput) -> ToolResult:
    if inp.id is None:
        raise ValueError("action=remove requires the 'id' field")
    events = store.read_events(inp.user_id)
    target_idx = next((i for i, e in enumerate(events) if e.id == inp.id), None)
    if target_idx is None:
        return ToolResult(
            display_text=render.render_supersedes_not_found(target_id=inp.id, kind="event")
        )
    target = events[target_idx]
    if target.removed:
        # Idempotent: the user already removed this. Return the same confirm.
        return ToolResult(display_text=render.render_event_removed_confirm(target))
    flipped = target.model_copy(update={"removed": True})
    events[target_idx] = flipped
    store.write_events(inp.user_id, events)
    return ToolResult(display_text=render.render_event_removed_confirm(flipped))


def main(argv_json: str) -> ToolResult:
    inp = EventInput.model_validate_json(argv_json)
    match inp.action:
        case "add":
            return _add(inp)
        case "list":
            return _list(inp)
        case "remove":
            return _remove(inp)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_event '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
