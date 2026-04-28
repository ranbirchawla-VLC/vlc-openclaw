"""Tests for scripts/common.py — sub-step 0 baseline."""

from __future__ import annotations
import json
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import User, append_jsonl, read_json, read_user, write_json, write_user


def _user(user_id: int = 111) -> User:
    return User(
        user_id=user_id,
        created_at="2026-04-25T00:00:00Z",
        name="Test",
        gender="other",
        home_timezone="America/Denver",
    )


def test_user_model_valid():
    u = _user()
    assert u.user_id == 111
    assert u.name == "Test"
    assert u.home_timezone == "America/Denver"


def test_user_model_missing_required_fields():
    with pytest.raises(ValidationError):
        User(user_id=1, created_at="2026-04-25T00:00:00Z", name="X")


def test_user_model_wrong_type_for_user_id():
    with pytest.raises(ValidationError):
        User(
            user_id="not_an_int",
            created_at="2026-04-25T00:00:00Z",
            name="X",
            gender="m",
            home_timezone="UTC",
        )


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


def test_read_json_missing_returns_none(tmp_path):
    result = read_json(str(tmp_path / "nonexistent.json"))
    assert result is None


def test_read_user_missing_returns_none(tmp_path):
    result = read_user(999, data_root=str(tmp_path))
    assert result is None
