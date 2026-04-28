"""Shared constants and utilities for NutriOS."""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime
import zoneinfo

from pydantic import BaseModel

DATA_ROOT = os.environ.get(
    "NUTRIOS_DATA_ROOT",
    "/Users/ranbirchawla/agent_data/nutriosv2"
)

AGENT_TZ = os.environ.get("NUTRIOS_TZ", "America/Denver")


def today_str(tz: str = AGENT_TZ) -> str:
    return datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: dict, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    bak = path + ".bak"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        os.replace(path, bak)
    os.replace(tmp, path)


def append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def ok(data: dict | list | str) -> None:
    print(json.dumps({"ok": True, "data": data}))
    sys.exit(0)


def err(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(1)


class User(BaseModel):
    user_id: int
    created_at: str
    name: str
    gender: str
    home_timezone: str


def read_user(user_id: int, data_root: str = DATA_ROOT) -> User | None:
    path = os.path.join(data_root, str(user_id), "user.json")
    data = read_json(path)
    if data is None:
        return None
    return User(**data)


def write_user(user: User, data_root: str = DATA_ROOT) -> None:
    path = os.path.join(data_root, str(user.user_id), "user.json")
    write_json(path, user.model_dump())
