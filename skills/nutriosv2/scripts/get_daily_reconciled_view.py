"""get_daily_reconciled_view — reconciled daily intake vs. target.

Usage: python3 get_daily_reconciled_view.py '<json_args>'
"""

from __future__ import annotations
import json
import os
import sys
from datetime import date as date_type, datetime
import zoneinfo

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA_ROOT, CorruptStateError, err, ok
from get_active_mesocycle import run_get_active_mesocycle
from models import MealLog

from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    date: str
    active_timezone: str


def _load_meal_logs(user_id: int, data_root: str) -> list[MealLog]:
    path = os.path.join(data_root, str(user_id), "meal_log.jsonl")
    if not os.path.exists(path):
        return []
    logs: list[MealLog] = []
    with open(path) as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                raise CorruptStateError(path, Exception(f"line {lineno}: {e}"))
            try:
                logs.append(MealLog(**data))
            except Exception as e:
                raise CorruptStateError(path, Exception(f"line {lineno}: {e}"))
    return logs


def _filter_by_date(logs: list[MealLog], target_date: date_type, tz: zoneinfo.ZoneInfo) -> list[MealLog]:
    result = []
    for log in logs:
        dt_utc = datetime.fromisoformat(log.timestamp_utc.replace("Z", "+00:00"))
        local_date = dt_utc.astimezone(tz).date()
        if local_date == target_date:
            result.append(log)
    return result


def _reconcile(logs: list[MealLog]) -> list[MealLog]:
    superseded: set[int] = set()
    for log in logs:
        if log.supersedes is not None:
            superseded.add(log.supersedes)
    return [log for log in logs if log.log_id not in superseded]


def _sum_macros(logs: list[MealLog]) -> dict[str, int]:
    return {
        "calories": sum(log.macros.calories for log in logs),
        "protein_g": sum(log.macros.protein_g for log in logs),
        "fat_g": sum(log.macros.fat_g for log in logs),
        "carbs_g": sum(log.macros.carbs_g for log in logs),
    }


def _dose_offset(target_date: date_type, dose_weekday: int) -> int:
    return (target_date.weekday() - dose_weekday) % 7


def run_get_daily_reconciled_view(inp: _Input, data_root: str = DATA_ROOT) -> dict:
    print(json.dumps({"tool": "get_daily_reconciled_view", "phase": "input", "args": inp.model_dump()}), file=sys.stderr)

    target_date = date_type.fromisoformat(inp.date)
    tz = zoneinfo.ZoneInfo(inp.active_timezone)

    all_logs = _load_meal_logs(inp.user_id, data_root)
    todays_logs = _filter_by_date(all_logs, target_date, tz)
    surviving = _reconcile(todays_logs)
    surviving_sorted = sorted(surviving, key=lambda l: l.timestamp_utc)

    consumed = _sum_macros(surviving)

    cycle_data = run_get_active_mesocycle(inp.user_id, data_root=data_root)
    target = None
    remaining = None
    is_expired = False

    if cycle_data is not None:
        end_date = date_type.fromisoformat(cycle_data["end_date"])
        is_expired = target_date >= end_date
        offset = _dose_offset(target_date, cycle_data["dose_weekday"])
        row = cycle_data["macro_table"][offset]
        target = {
            "calories": row["calories"],
            "protein_g": row["protein_g"],
            "fat_g": row["fat_g"],
            "carbs_g": row["carbs_g"],
            "restrictions": row["restrictions"],
        }
        remaining = {
            "calories": target["calories"] - consumed["calories"],
            "protein_g": target["protein_g"] - consumed["protein_g"],
            "fat_g": target["fat_g"] - consumed["fat_g"],
            "carbs_g": target["carbs_g"] - consumed["carbs_g"],
        }

    result = {
        "target": target,
        "consumed": consumed,
        "remaining": remaining,
        "is_expired": is_expired,
        "entries": [e.model_dump() for e in surviving_sorted],
    }

    print(json.dumps({"tool": "get_daily_reconciled_view", "phase": "output", "result": result}), file=sys.stderr)
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
    try:
        zoneinfo.ZoneInfo(inp.active_timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        err(f"unknown timezone: {inp.active_timezone}")
        return
    result = run_get_daily_reconciled_view(inp)
    ok(result)


if __name__ == "__main__":
    main()
