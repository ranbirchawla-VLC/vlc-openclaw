"""get_active_mesocycle — return the current active mesocycle or null.

Usage: python3 get_active_mesocycle.py '<json_args>'

Args JSON schema:
  user_id: int
"""

# TODO(otel): span="mesocycle.get_active" attrs={user_id, found, outcome}

from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, active_txt_path, err, mesocycles_dir, ok, read_json
from models import Mesocycle

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int


def run_get_active_mesocycle(user_id: int, data_root: str = DATA_ROOT) -> dict | None:
    path = active_txt_path(user_id, data_root)
    if not os.path.exists(path):
        return None
    content = open(path).read().strip()
    if not content:
        return None
    active_id = int(content)
    cycle_path = os.path.join(mesocycles_dir(user_id, data_root), f"{active_id}.json")
    try:
        data = read_json(cycle_path)
    except json.JSONDecodeError as e:
        raise CorruptStateError(cycle_path, e)
    if data is None:
        return None
    try:
        cycle = Mesocycle(**data)
    except Exception as e:
        raise CorruptStateError(cycle_path, e)
    return cycle.model_dump()


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
    # TODO(otel): span="mesocycle.get_active" start
    result = run_get_active_mesocycle(inp.user_id)
    ok(result)


if __name__ == "__main__":
    main()
