"""context_builder — assemble the structured context block for system prompt injection.

Every turn, this script produces a snapshot of the user's current state:
- Current date + day name (from system clock; never derived by LLM)
- Active mesocycle: name, week, today's macro targets (pre-computed by Python)
- Full recipe list from recipes.json
- Today's consumed totals (reconciled from meal_log.jsonl)
- User profile text (from USER.md)

Usage: python3 context_builder.py '<json_args>'
Args: {user_id: int, active_timezone: str}
Returns: {date, mesocycle, recipes, totals, user_profile}
"""

from __future__ import annotations
import json
import os
import sys
from datetime import date as date_type, datetime
import zoneinfo

sys.path.insert(0, os.path.dirname(__file__))
from common import AGENT_TZ, DATA_ROOT, CorruptStateError, err, ok
from get_active_mesocycle import run_get_active_mesocycle
from list_recipes import run_list_recipes
from models import MealLog

from pydantic import BaseModel, ConfigDict

_DEFAULT_USER_PROFILE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "USER.md")
)


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    active_timezone: str


def _load_today_totals(
    user_id: int,
    today_date: date_type,
    tz: zoneinfo.ZoneInfo,
    data_root: str,
) -> dict:
    path = os.path.join(data_root, str(user_id), "meal_log.jsonl")
    if not os.path.exists(path):
        return {"calories": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0}
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
    today_logs = [
        log for log in logs
        if datetime.fromisoformat(log.timestamp_utc.replace("Z", "+00:00")).astimezone(tz).date() == today_date
    ]
    superseded: set[int] = {log.supersedes for log in today_logs if log.supersedes is not None}
    surviving = [log for log in today_logs if log.log_id not in superseded]
    return {
        "calories": sum(log.macros.calories for log in surviving),
        "protein_g": sum(log.macros.protein_g for log in surviving),
        "fat_g": sum(log.macros.fat_g for log in surviving),
        "carbs_g": sum(log.macros.carbs_g for log in surviving),
    }


def run_context_builder(
    user_id: int,
    active_timezone: str = AGENT_TZ,
    data_root: str = DATA_ROOT,
    user_profile_path: str = _DEFAULT_USER_PROFILE_PATH,
    today: date_type | None = None,
) -> dict:
    tz = zoneinfo.ZoneInfo(active_timezone)
    if today is None:
        today = datetime.now(tz).date()
    today_iso = today.isoformat()
    day_name = today.strftime("%A")

    cycle_data = run_get_active_mesocycle(user_id, data_root=data_root)
    mesocycle_ctx: dict | None = None
    if cycle_data is not None:
        start = date_type.fromisoformat(cycle_data["start_date"])
        end = date_type.fromisoformat(cycle_data["end_date"])
        raw_week = (today - start).days // 7 + 1
        if raw_week < 1:
            print(json.dumps({"tool": "context_builder", "warn": "future_dated_cycle",
                              "today": today_iso, "start_date": str(start)}), file=sys.stderr)
        # clamp to 1: a future-dated active cycle would otherwise produce week=0
        week = max(1, raw_week)
        is_expired = today >= end
        dose_offset = (today.weekday() - cycle_data["dose_weekday"]) % 7
        row = cycle_data["macro_table"][dose_offset]
        mesocycle_ctx = {
            "name": cycle_data["name"],
            "week": week,
            "is_expired": is_expired,
            "targets": {
                "calories": row["calories"],
                "protein_g": row["protein_g"],
                "fat_g": row["fat_g"],
                "carbs_g": row["carbs_g"],
                "restrictions": row["restrictions"],
            },
        }

    recipes_result = run_list_recipes(user_id, data_root=data_root)
    totals = _load_today_totals(user_id, today, tz, data_root)

    user_profile = ""
    if user_profile_path and os.path.exists(user_profile_path):
        with open(user_profile_path) as f:
            user_profile = f.read()

    return {
        "date": {"iso": today_iso, "day_name": day_name},
        "mesocycle": mesocycle_ctx,
        "recipes": recipes_result["recipes"],
        "totals": totals,
        "user_profile": user_profile,
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
    try:
        result = run_context_builder(inp.user_id, inp.active_timezone)
    except CorruptStateError as e:
        err(str(e))
        return
    except Exception as e:
        err(str(e))
        return
    ok(result)


if __name__ == "__main__":
    main()
