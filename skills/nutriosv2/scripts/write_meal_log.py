"""write_meal_log: append a meal log entry for a user.

Usage: python3 write_meal_log.py '<json_args>'
"""

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, append_jsonl, err, now_utc, ok
from models import MealLog, Macros

from pydantic import BaseModel, ConfigDict, model_validator
from typing import Literal


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    food_description: str
    macros: Macros
    source: Literal["recipe", "ad_hoc"]
    recipe_id: int | None = None
    recipe_name_snapshot: str | None = None
    supersedes_log_id: int | None = None
    active_timezone: str

    @model_validator(mode="after")
    def recipe_id_consistency(self) -> "_Input":
        match self.source:
            case "recipe":
                if self.recipe_id is None:
                    raise ValueError("recipe_id required when source is 'recipe'")
            case "ad_hoc":
                if self.recipe_id is not None:
                    raise ValueError("recipe_id forbidden when source is 'ad_hoc'")
            case _:
                raise ValueError(f"unknown source: {self.source}")
        return self


def _meal_log_path(user_id: int, data_root: str) -> str:
    return os.path.join(data_root, str(user_id), "meal_log.jsonl")


def _next_log_id(user_id: int, data_root: str) -> int:
    path = _meal_log_path(user_id, data_root)
    if not os.path.exists(path):
        return 1
    max_id = 0
    with open(path) as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise CorruptStateError(path, Exception(f"line {lineno}: {e}"))
            log_id = record.get("log_id", 0)
            if isinstance(log_id, int) and log_id > max_id:
                max_id = log_id
    return max_id + 1


def run_write_meal_log(inp: _Input, data_root: str = DATA_ROOT) -> dict:
    print(json.dumps({"tool": "write_meal_log", "phase": "input", "args": inp.model_dump()}), file=sys.stderr)

    log_id = _next_log_id(inp.user_id, data_root)
    entry = MealLog(
        log_id=log_id,
        user_id=inp.user_id,
        timestamp_utc=now_utc(),
        timezone_at_log=inp.active_timezone,
        food_description=inp.food_description,
        macros=inp.macros,
        source=inp.source,
        recipe_id=inp.recipe_id,
        recipe_name_snapshot=inp.recipe_name_snapshot,
        supersedes=inp.supersedes_log_id,
    )
    path = _meal_log_path(inp.user_id, data_root)
    append_jsonl(path, entry.model_dump())

    result = {"log_id": log_id}
    print(json.dumps({"tool": "write_meal_log", "phase": "output", "result": result}), file=sys.stderr)
    return result


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
    result = run_write_meal_log(inp)
    ok(result)


if __name__ == "__main__":
    main()
