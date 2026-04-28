"""lock_mesocycle — end any active cycle and write a new active one.

Usage: python3 lock_mesocycle.py '<json_args>'

Failure mode: if the new cycle file is written (step 5) but active.txt update
fails (step 6), active.txt still points to the old (now-ended) cycle. On next
read, active.txt returns an ended cycle. Recovery: newest cycle by created_at
is the intended active one — operator must inspect and repair active.txt.
"""

# TODO(otel): span="mesocycle.lock" attrs={user_id, mesocycle_id, outcome}

from __future__ import annotations
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, active_txt_path, err, mesocycles_dir, now_utc, ok, read_json, write_json, write_text_atomic
from models import Intent, MacroRow, Mesocycle

from pydantic import BaseModel, ConfigDict, field_validator


class _MacroRowInput(BaseModel):
    model_config = ConfigDict(strict=True)
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    restrictions: list[str]


class _IntentInput(BaseModel):
    model_config = ConfigDict(strict=True)
    target_deficit_kcal: int | None = None
    protein_floor_g: int | None = None
    fat_ceiling_g: int | None = None
    rationale: str = ""


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    name: str
    weeks: int
    start_date: str
    dose_weekday: int
    macro_table: list[_MacroRowInput]
    intent: _IntentInput

    @field_validator("weeks")
    @classmethod
    def weeks_gte_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("weeks must be >= 1")
        return v

    @field_validator("dose_weekday")
    @classmethod
    def dose_weekday_valid(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("dose_weekday must be 0..6")
        return v

    @field_validator("macro_table")
    @classmethod
    def macro_table_seven_rows(cls, v: list) -> list:
        if len(v) != 7:
            raise ValueError(f"macro_table must have exactly 7 rows, got {len(v)}")
        return v


def _list_mesocycle_ids(user_id: int, data_root: str) -> list[int]:
    d = mesocycles_dir(user_id, data_root)
    if not os.path.isdir(d):
        return []
    ids = []
    for name in os.listdir(d):
        if name.endswith(".json"):
            try:
                ids.append(int(name[:-5]))
            except ValueError:
                pass
    return ids


def _read_mesocycle_file(user_id: int, mesocycle_id: int, data_root: str) -> Mesocycle:
    path = os.path.join(mesocycles_dir(user_id, data_root), f"{mesocycle_id}.json")
    try:
        data = read_json(path)
    except json.JSONDecodeError as e:
        raise CorruptStateError(path, e)
    if data is None:
        raise FileNotFoundError(f"mesocycle {mesocycle_id} not found at {path}")
    try:
        return Mesocycle(**data)
    except Exception as e:
        raise CorruptStateError(path, e)


def _write_mesocycle_file(user_id: int, cycle: Mesocycle, data_root: str) -> None:
    path = os.path.join(mesocycles_dir(user_id, data_root), f"{cycle.mesocycle_id}.json")
    write_json(path, cycle.model_dump())


def _read_active_id(user_id: int, data_root: str) -> int | None:
    path = active_txt_path(user_id, data_root)
    if not os.path.exists(path):
        return None
    content = open(path).read().strip()
    return int(content) if content else None


def run_lock_mesocycle(inp: _Input, data_root: str = DATA_ROOT) -> dict:
    # TODO(otel): child span="mesocycle.end_prior"
    active_id = _read_active_id(inp.user_id, data_root)
    if active_id is not None:
        prior = _read_mesocycle_file(inp.user_id, active_id, data_root)
        ended = prior.model_copy(update={"status": "ended", "ended_at": now_utc()})
        _write_mesocycle_file(inp.user_id, ended, data_root)

    existing_ids = _list_mesocycle_ids(inp.user_id, data_root)
    new_id = max(existing_ids) + 1 if existing_ids else 1

    end_date = (
        date.fromisoformat(inp.start_date) + timedelta(days=inp.weeks * 7)
    ).isoformat()

    cycle = Mesocycle(
        mesocycle_id=new_id,
        user_id=inp.user_id,
        name=inp.name,
        weeks=inp.weeks,
        start_date=inp.start_date,
        end_date=end_date,
        dose_weekday=inp.dose_weekday,
        macro_table=[MacroRow(**r.model_dump()) for r in inp.macro_table],
        intent=Intent(**inp.intent.model_dump()),
        status="active",
        created_at=now_utc(),
        ended_at=None,
    )

    # TODO(otel): child span="mesocycle.write_file"
    _write_mesocycle_file(inp.user_id, cycle, data_root)
    # TODO(otel): child span="mesocycle.write_active_txt"
    write_text_atomic(active_txt_path(inp.user_id, data_root), str(new_id))

    return {
        "mesocycle_id": new_id,
        "name": inp.name,
        "start_date": inp.start_date,
        "end_date": end_date,
    }


def main() -> None:
    if len(sys.argv) < 2:
        err("missing args: expected JSON string as sys.argv[1]")
        return
    try:
        raw = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        err(f"invalid JSON args: {e}")
        return
    try:
        inp = _Input(**raw)
    except Exception as e:
        err(f"invalid input: {e}")
        return
    # TODO(otel): span="mesocycle.lock" start
    print(json.dumps({"tool": "lock_mesocycle", "phase": "input", "args": inp.model_dump()}), file=sys.stderr)
    result = run_lock_mesocycle(inp)
    print(json.dumps({"tool": "lock_mesocycle", "phase": "output", "result": result}), file=sys.stderr)
    ok(result)


if __name__ == "__main__":
    main()
