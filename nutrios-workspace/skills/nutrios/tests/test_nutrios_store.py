"""Tests for nutrios_store — TDD, one function cluster at a time.

Tests use a tmp_path fixture for all file I/O; NUTRIOS_DATA_ROOT is
monkeypatched via the environment so data_root() returns the temp dir.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import json
import os
import pytest
from datetime import date, datetime, timezone

import nutrios_store as store
from nutrios_models import (
    WeighIn, MedNote, FoodLogEntry, DoseLogEntry,
    NeedsSetup, State, Profile,
)


# ---------------------------------------------------------------------------
# data_root()
# ---------------------------------------------------------------------------

def test_data_root_raises_when_unset(monkeypatch):
    monkeypatch.delenv("NUTRIOS_DATA_ROOT", raising=False)
    with pytest.raises(EnvironmentError):
        store.data_root()

def test_data_root_returns_path(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    assert store.data_root() == tmp_path


# ---------------------------------------------------------------------------
# user_dir()
# ---------------------------------------------------------------------------

def test_user_dir_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    d = store.user_dir("alice")
    assert d == tmp_path / "users" / "alice"

def test_user_dir_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.user_dir("../etc")

def test_user_dir_rejects_slash_in_id(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.user_dir("a/b")

def test_user_dir_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.user_dir("")

def test_user_dir_rejects_whitespace(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.user_dir("with space")


# ---------------------------------------------------------------------------
# append_jsonl / tail_jsonl
# ---------------------------------------------------------------------------

def _make_weigh_in(uid: int) -> WeighIn:
    return WeighIn(id=uid, ts_iso="2026-04-24T12:00:00Z", weight_lbs=218.0)


def test_append_jsonl_single_line(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(1))
    path = tmp_path / "users" / "alice" / "weigh_ins.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == 1


def test_append_jsonl_ten_sequential(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    for i in range(1, 11):
        store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(i))
    path = tmp_path / "users" / "alice" / "weigh_ins.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) == 10
    ids = [json.loads(l)["id"] for l in lines]
    assert ids == list(range(1, 11))


def test_append_jsonl_atomic_on_interrupt(monkeypatch, tmp_path):
    """If write fails mid-way, original file must be unchanged."""
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    # Write one entry first
    store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(1))
    path = tmp_path / "users" / "alice" / "weigh_ins.jsonl"
    original_content = path.read_text()

    # Patch os.replace to raise so the temp→dest swap fails
    import unittest.mock as mock
    with mock.patch("nutrios_store.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(2))

    assert path.read_text() == original_content


def test_append_jsonl_rejects_bad_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.append_jsonl("alice", "../../secrets.jsonl", _make_weigh_in(1))


def test_tail_jsonl_returns_last_n(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    for i in range(1, 11):
        store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(i))
    tail = store.tail_jsonl("alice", "weigh_ins.jsonl", 3)
    assert len(tail) == 3
    assert [r["id"] for r in tail] == [8, 9, 10]
