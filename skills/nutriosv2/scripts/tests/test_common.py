"""Tests for scripts/common.py."""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime as _datetime
from unittest.mock import patch
import zoneinfo as _zoneinfo

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import (
    CorruptStateError,
    DATA_ROOT,
    User,
    active_txt_path,
    append_jsonl,
    dose_offset_to_weekday,
    err,
    mesocycles_dir,
    ok,
    read_json,
    read_user,
    today_str,
    write_json,
    write_user,
)


def _user(user_id: int = 111) -> User:
    return User(
        user_id=user_id,
        created_at="2026-04-25T00:00:00Z",
        name="Test",
        gender="other",
        home_timezone="America/Denver",
    )


# ── User model ────────────────────────────────────────────────────────────────

def test_user_model_valid():
    u = _user()
    assert u.user_id == 111
    assert u.name == "Test"
    assert u.home_timezone == "America/Denver"


def test_user_model_missing_required_fields():
    with pytest.raises(ValidationError):
        User(user_id=1, created_at="2026-04-25T00:00:00Z", name="X")


def test_user_model_strict_rejects_string_user_id():
    # NB-3 fixed: strict=True means "123" no longer coerces to 123
    with pytest.raises(ValidationError):
        User(
            user_id="123",
            created_at="2026-04-25T00:00:00Z",
            name="X",
            gender="m",
            home_timezone="UTC",
        )


def test_user_model_wrong_type_for_user_id():
    with pytest.raises(ValidationError):
        User(
            user_id="not_an_int",
            created_at="2026-04-25T00:00:00Z",
            name="X",
            gender="m",
            home_timezone="UTC",
        )


# ── write_user / read_user ────────────────────────────────────────────────────

def test_write_read_user_roundtrip(tmp_path):
    u = _user(222)
    write_user(u, data_root=str(tmp_path))
    u2 = read_user(222, data_root=str(tmp_path))
    assert u2 == u


def test_per_user_dir_created_on_first_write(tmp_path):
    u = _user(333)
    user_dir = tmp_path / "333"
    assert not user_dir.exists()
    write_user(u, data_root=str(tmp_path))
    assert user_dir.exists()
    assert (user_dir / "user.json").exists()


def test_read_user_missing_returns_none(tmp_path):
    assert read_user(999, data_root=str(tmp_path)) is None


def test_read_user_corrupt_json_raises(tmp_path):
    # NB-4 fixed: corrupt state is loud
    path = tmp_path / "444" / "user.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not valid json }")
    with pytest.raises(CorruptStateError) as exc_info:
        read_user(444, data_root=str(tmp_path))
    assert "corrupt state" in str(exc_info.value)


def test_read_user_invalid_schema_raises(tmp_path):
    path = tmp_path / "555" / "user.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"user_id": 555}))  # missing required fields
    with pytest.raises(CorruptStateError):
        read_user(555, data_root=str(tmp_path))


# ── write_json ────────────────────────────────────────────────────────────────

def test_atomic_write_bak_on_overwrite(tmp_path):
    path = str(tmp_path / "data.json")
    write_json(path, {"v": 1})
    write_json(path, {"v": 2})
    assert os.path.exists(path + ".bak")
    with open(path + ".bak") as f:
        assert json.load(f) == {"v": 1}
    with open(path) as f:
        assert json.load(f) == {"v": 2}


def test_atomic_write_no_bak_on_first_write(tmp_path):
    path = str(tmp_path / "first.json")
    write_json(path, {"v": 1})
    assert not os.path.exists(path + ".bak")


def test_write_json_path_never_absent_on_replace_failure(tmp_path):
    # NB-1 fixed: if os.replace(tmp, path) raises, original is still readable
    path = str(tmp_path / "data.json")
    write_json(path, {"v": 1})

    import common as common_mod
    original_replace = os.replace

    call_count = {"n": 0}

    def failing_replace(src: str, dst: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("simulated crash")
        return original_replace(src, dst)

    with patch.object(common_mod.os, "replace", failing_replace):
        with pytest.raises(OSError):
            write_json(path, {"v": 2})

    result = read_json(path)
    assert result == {"v": 1}


def test_write_json_flat_path_no_makedirs_error(tmp_path):
    # NB-2 fixed: flat path (no dir component) must not raise
    original_dir = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        write_json("flat.json", {"v": 1})
        assert os.path.exists(str(tmp_path / "flat.json"))
    finally:
        os.chdir(original_dir)


# ── append_jsonl ──────────────────────────────────────────────────────────────

def test_append_jsonl_grows_and_preserves_records(tmp_path):
    path = str(tmp_path / "log.jsonl")
    append_jsonl(path, {"a": 1})
    size1 = os.path.getsize(path)
    append_jsonl(path, {"b": 2})
    size2 = os.path.getsize(path)
    assert size2 > size1
    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}


# ── read_json ─────────────────────────────────────────────────────────────────

def test_read_json_missing_returns_none(tmp_path):
    assert read_json(str(tmp_path / "nonexistent.json")) is None


# ── NB-1: promoted path helpers ───────────────────────────────────────────────

def test_mesocycles_dir_returns_correct_path():
    result = mesocycles_dir(user_id=42, data_root="/tmp/root")
    assert result == "/tmp/root/42/mesocycles"


def test_mesocycles_dir_uses_data_root_default():
    result = mesocycles_dir(user_id=1)
    assert result == os.path.join(DATA_ROOT, "1", "mesocycles")


def test_active_txt_path_returns_correct_path():
    result = active_txt_path(user_id=42, data_root="/tmp/root")
    assert result == "/tmp/root/42/mesocycles/active.txt"


def test_active_txt_path_uses_data_root_default():
    result = active_txt_path(user_id=1)
    assert result == os.path.join(DATA_ROOT, "1", "mesocycles", "active.txt")


# ── NB-5 (sub-step 0): ok/err ─────────────────────────────────────────────────

def test_ok_exits_zero_and_prints_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        ok({"mesocycle_id": 7})
    assert exc_info.value.code == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured == {"ok": True, "data": {"mesocycle_id": 7}}


def test_ok_accepts_list(capsys):
    with pytest.raises(SystemExit) as exc_info:
        ok([1, 2, 3])
    assert exc_info.value.code == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured == {"ok": True, "data": [1, 2, 3]}


def test_err_exits_one_and_prints_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        err("something went wrong")
    assert exc_info.value.code == 1
    captured = json.loads(capsys.readouterr().out)
    assert captured == {"ok": False, "error": "something went wrong"}


# ── NB-6 (sub-step 0): today_str ─────────────────────────────────────────────

def test_today_str_returns_iso_date_format():
    result = today_str()
    parts = result.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # YYYY
    assert len(parts[1]) == 2  # MM
    assert len(parts[2]) == 2  # DD


# ── dose_offset_to_weekday ────────────────────────────────────────────────────

def test_dose_offset_sunday_offset_0():
    assert dose_offset_to_weekday(6, 0) == "Sunday"


def test_dose_offset_sunday_offset_1():
    assert dose_offset_to_weekday(6, 1) == "Monday"


def test_dose_offset_sunday_offset_2():
    assert dose_offset_to_weekday(6, 2) == "Tuesday"


def test_dose_offset_sunday_offset_3():
    assert dose_offset_to_weekday(6, 3) == "Wednesday"


def test_dose_offset_sunday_offset_4():
    assert dose_offset_to_weekday(6, 4) == "Thursday"


def test_dose_offset_sunday_offset_5():
    assert dose_offset_to_weekday(6, 5) == "Friday"


def test_dose_offset_sunday_offset_6():
    assert dose_offset_to_weekday(6, 6) == "Saturday"


def test_dose_offset_thursday_offset_4():
    # off-cycle case: Thursday dose (3), offset 4 → Monday ((3+4)%7 = 0)
    assert dose_offset_to_weekday(3, 4) == "Monday"


def test_today_str_timezone_affects_date():
    # Freeze the clock at 2026-04-25 05:30 UTC.
    # In UTC that is 2026-04-25.
    # In America/Denver (MDT = UTC-6) that is 2026-04-24 23:30 — a different date.
    frozen_utc = _datetime(2026, 4, 25, 5, 30, 0, tzinfo=_zoneinfo.ZoneInfo("UTC"))

    import common as common_mod

    def mock_now(tz=None):
        return frozen_utc.astimezone(tz) if tz is not None else frozen_utc

    with patch.object(common_mod, "datetime") as mock_dt:
        mock_dt.now.side_effect = mock_now
        result_utc = today_str(tz="UTC")
        result_denver = today_str(tz="America/Denver")

    assert result_utc == "2026-04-25"
    assert result_denver == "2026-04-24"
