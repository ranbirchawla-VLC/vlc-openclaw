"""nutrios_dose.py — log a dose for today (5/10).

Reject if today is not the dose day → render_dose_not_due.
Reject if a dose is already logged today → render_dose_already_logged.
Otherwise append a DoseLogEntry with dose_mg+brand snapshotted from the
current protocol. The dose entry shares the last_entry_id counter with
food entries (LogEntry is a discriminated union).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import date as date_type, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nutrios_models import (
    DoseLogEntry, FoodLogEntry, LogEntryAdapter, Protocol, ToolResult,
)
import nutrios_render as render
import nutrios_store as store


_LARGE_N = 10_000

_WEEKDAY_ORDER = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


class DoseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    now: datetime
    tz: str


def _today_doses(uid: str, target_date: date_type) -> list[DoseLogEntry]:
    raw = store.tail_jsonl(uid, f"log/{target_date}.jsonl", _LARGE_N)
    out: list[DoseLogEntry] = []
    for r in raw:
        entry = LogEntryAdapter.validate_python(r)
        if isinstance(entry, DoseLogEntry):
            out.append(entry)
    return out


def _next_dose_date(today: date_type, target_weekday: str) -> date_type:
    """Compute the next occurrence of target_weekday strictly AFTER today.

    If today's weekday equals target_weekday, returns today + 7 days
    (next week's dose day).
    """
    target_idx = _WEEKDAY_ORDER.index(target_weekday.lower())
    today_idx = today.weekday()  # Monday = 0
    delta = (target_idx - today_idx) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def main(argv_json: str) -> ToolResult:
    inp = DoseInput.model_validate_json(argv_json)

    protocol = store.read_json(inp.user_id, "protocol.json", Protocol)
    if protocol is None:
        return ToolResult(display_text=render.render_protocol_not_initialized())

    local_today = inp.now.astimezone(ZoneInfo(inp.tz)).date()
    today_weekday = local_today.strftime("%A").lower()
    target_weekday = protocol.treatment.dose_day_of_week.lower()

    if today_weekday != target_weekday:
        next_date = _next_dose_date(local_today, target_weekday)
        return ToolResult(
            display_text=render.render_dose_not_due(target_weekday, next_date)
        )

    today_doses = _today_doses(inp.user_id, local_today)
    if today_doses:
        return ToolResult(display_text=render.render_dose_already_logged())

    new_id = store.next_id(inp.user_id, "last_entry_id")
    ts_iso = inp.now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    dose_entry = DoseLogEntry(
        kind="dose",
        id=new_id,
        ts_iso=ts_iso,
        dose_mg=protocol.treatment.dose_mg,
        brand=protocol.treatment.brand,
    )
    store.append_jsonl(inp.user_id, f"log/{local_today}.jsonl", dose_entry)

    return ToolResult(
        display_text=render.render_dose_confirm(dose_entry),
        state_delta={"last_entry_id": new_id},
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_dose '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
