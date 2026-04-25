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
