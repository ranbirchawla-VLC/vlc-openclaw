"""nutrios_weigh_in.py — add or supersedes-edit a weigh-in (4/10).

Append-only via store.append_jsonl. Edits write a new line referencing the
prior id via supersedes — never an in-place rewrite.

Failure modes (rendered, not raised):
- weight out of (0, 1000) → render_invalid_weight
- supersedes target id not found in weigh_ins.jsonl → render_supersedes_not_found
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
from datetime import date as date_type, datetime, time, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nutrios_models import ToolResult, WeighIn
import nutrios_engine as engine
import nutrios_render as render
import nutrios_store as store


_LARGE_N = 10_000


class WeighInInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    weight_lbs: float
    weigh_in_date: date_type | None = None  # named to avoid shadowing date type
    supersedes: int | None = None
    now: datetime
    tz: str


def _ts_iso_for_date(target: date_type, tz: str) -> str:
    """Noon-local on the target date → UTC ISO8601 with 'Z' suffix.

    Weigh-ins don't carry a meaningful time-of-day, so we anchor to noon
    local. Stored UTC; the same target date renders consistently regardless
    of TZ swings.
    """
    local_noon = datetime.combine(target, time(12, 0), tzinfo=ZoneInfo(tz))
    return local_noon.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv_json: str) -> ToolResult:
    inp = WeighInInput.model_validate_json(argv_json)

    # Weight bounds — rendered rejection, not Pydantic raise
    if not (0 < inp.weight_lbs < 1000):
        return ToolResult(display_text=render.render_invalid_weight(inp.weight_lbs))

    target_date = inp.weigh_in_date if inp.weigh_in_date is not None else (
        inp.now.astimezone(ZoneInfo(inp.tz)).date()
    )

    # supersedes target must exist on disk
    if inp.supersedes is not None:
        existing_ids = {
            r["id"] for r in store.tail_jsonl(inp.user_id, "weigh_ins.jsonl", _LARGE_N)
        }
        if inp.supersedes not in existing_ids:
            return ToolResult(
                display_text=render.render_supersedes_not_found(
                    target_id=inp.supersedes, kind="weigh-in",
                )
            )

    new_id = store.next_id(inp.user_id, "last_weigh_in_id")
    weigh_in = WeighIn(
        id=new_id,
        ts_iso=_ts_iso_for_date(target_date, inp.tz),
        weight_lbs=inp.weight_lbs,
        supersedes=inp.supersedes,
    )
    store.append_jsonl(inp.user_id, "weigh_ins.jsonl", weigh_in)

    # Active weigh-ins for trend math, post-write
    all_raw = store.tail_jsonl(inp.user_id, "weigh_ins.jsonl", _LARGE_N)
    all_weigh_ins = [WeighIn.model_validate(r) for r in all_raw]
    change = engine.weight_change(all_weigh_ins, inp.now, since_days=7)

    return ToolResult(
        display_text=render.render_weigh_in_confirm(weigh_in, change, progress=None),
        state_delta={"last_weigh_in_id": new_id},
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: nutrios_weigh_in '<json_argv>'"}), file=sys.stderr)
        sys.exit(2)
    result = main(sys.argv[1])
    print(result.model_dump_json())
