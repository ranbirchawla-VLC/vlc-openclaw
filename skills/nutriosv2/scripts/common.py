"""Shared constants and utilities for NutriOS."""

from __future__ import annotations
import json
import os
import shutil
import sys
from datetime import datetime
import zoneinfo

from pydantic import BaseModel, ConfigDict, ValidationError

DATA_ROOT = os.environ.get(
    "NUTRIOS_DATA_ROOT",
    "/Users/ranbirchawla/agent_data/nutriosv2"
)

AGENT_TZ = os.environ.get("NUTRIOS_TZ", "America/Denver")


class CorruptStateError(Exception):
    """Raised when a state file exists but cannot be parsed or validated."""

    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(f"corrupt state at {path}: {cause}")
        self.path = path
        self.cause = cause


def today_str(tz: str = AGENT_TZ) -> str:
    return datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def now_utc() -> str:
    return datetime.now(zoneinfo.ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: str, data: dict, indent: int = 2) -> None:
    # NB-2: guard against flat paths (no directory component)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    bak = path + ".bak"
    # NB-1: copy old file to .bak before writing tmp so path is never absent.
    # If we crash after copy but before os.replace, path still has old content.
    if os.path.exists(path):
        shutil.copy2(path, bak)
    with open(tmp, "w") as f:
        json.dump(data, f, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_text_atomic(path: str, content: str) -> None:
    """Write a text file atomically via tmp → fsync → os.replace."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_jsonl(path: str, record: dict) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
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


# NB-3: strict=True prevents silent str→int coercion on user_id
class User(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    created_at: str
    name: str
    gender: str
    home_timezone: str


def read_user(user_id: int, data_root: str = DATA_ROOT) -> User | None:
    path = os.path.join(data_root, str(user_id), "user.json")
    # NB-4: corrupt state is loud, never silent
    try:
        data = read_json(path)
    except json.JSONDecodeError as e:
        raise CorruptStateError(path, e)
    if data is None:
        return None
    try:
        return User(**data)
    except ValidationError as e:
        raise CorruptStateError(path, e)


def write_user(user: User, data_root: str = DATA_ROOT) -> None:
    path = os.path.join(data_root, str(user.user_id), "user.json")
    write_json(path, user.model_dump())


_WEEKDAY_NAMES: list[str] = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]


def dose_offset_to_weekday(dose_weekday: int, offset: int) -> str:
    """Return the weekday name for a given dose_weekday (0=Mon..6=Sun) and row offset."""
    return _WEEKDAY_NAMES[(dose_weekday + offset) % 7]


def mesocycles_dir(user_id: int, data_root: str = DATA_ROOT) -> str:
    return os.path.join(data_root, str(user_id), "mesocycles")


def active_txt_path(user_id: int, data_root: str = DATA_ROOT) -> str:
    return os.path.join(mesocycles_dir(user_id, data_root), "active.txt")
