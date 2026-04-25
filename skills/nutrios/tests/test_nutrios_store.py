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
    NeedsSetup, State, Profile, Event,
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


def test_read_jsonl_all_returns_every_line(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    for i in range(1, 6):
        store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(i))
    rows = store.read_jsonl_all("alice", "weigh_ins.jsonl")
    assert [r["id"] for r in rows] == [1, 2, 3, 4, 5]


def test_read_jsonl_all_empty_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    assert store.read_jsonl_all("alice", "weigh_ins.jsonl") == []


def test_read_jsonl_all_rejects_bad_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        store.read_jsonl_all("alice", "../../secrets.jsonl")


# ---------------------------------------------------------------------------
# next_id()
# ---------------------------------------------------------------------------

def test_next_id_monotonic(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    ids = [store.next_id("alice", "last_entry_id") for _ in range(100)]
    assert ids == list(range(1, 101))


def test_next_id_independent_counters(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    e1 = store.next_id("alice", "last_entry_id")
    w1 = store.next_id("alice", "last_weigh_in_id")
    e2 = store.next_id("alice", "last_entry_id")
    w2 = store.next_id("alice", "last_weigh_in_id")
    assert (e1, e2) == (1, 2)
    assert (w1, w2) == (1, 2)


def test_next_id_last_recipe_id_counter(monkeypatch, tmp_path):
    """last_recipe_id is a new counter on State; must increment independently."""
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    r1 = store.next_id("alice", "last_recipe_id")
    e1 = store.next_id("alice", "last_entry_id")
    r2 = store.next_id("alice", "last_recipe_id")
    assert r1 == 1
    assert r2 == 2
    assert e1 == 1


# ---------------------------------------------------------------------------
# read_needs_setup() / clear_needs_setup_marker()
# ---------------------------------------------------------------------------

def test_read_needs_setup_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    ns = store.read_needs_setup("alice")
    assert ns == NeedsSetup()
    assert ns.tdee is False

def test_clear_needs_setup_marker_tdee_only(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    # Write a setup file with all markers true
    all_true = NeedsSetup(
        gallbladder=True, tdee=True, carbs_shape=True, deficits=True, nominal_deficit=True
    )
    store.write_json("alice", "_needs_setup.json", all_true)
    store.clear_needs_setup_marker("alice", "tdee")
    result = store.read_needs_setup("alice")
    assert result.tdee is False
    # All others still True
    assert result.gallbladder is True
    assert result.carbs_shape is True
    assert result.deficits is True
    assert result.nominal_deficit is True


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# resolve_user_id_from_peer()
# ---------------------------------------------------------------------------

def _write_index(tmp_path: Path, data: object) -> None:
    index_dir = tmp_path / "_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "users.json").write_text(
        json.dumps(data) if not isinstance(data, str) else data
    )

def test_resolve_user_id_happy_path(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    _write_index(tmp_path, {"telegram:12345": "alice"})
    assert store.resolve_user_id_from_peer("telegram:12345") == "alice"

def test_resolve_user_id_missing_peer(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    _write_index(tmp_path, {"telegram:12345": "alice"})
    with pytest.raises(store.StoreError, match="not in user index"):
        store.resolve_user_id_from_peer("telegram:99999")

def test_resolve_user_id_missing_index_file(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    # No _index/users.json written
    with pytest.raises(store.StoreError, match="not initialized"):
        store.resolve_user_id_from_peer("telegram:12345")

def test_resolve_user_id_malformed_json(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    _write_index(tmp_path, "not valid json at all {{{{")
    with pytest.raises(store.StoreError, match="parse"):
        store.resolve_user_id_from_peer("telegram:12345")

def test_resolve_user_id_value_not_string_raises(monkeypatch, tmp_path):
    """Index entry with a non-string value (e.g. int) must raise StoreError."""
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    _write_index(tmp_path, {"telegram:12345": 12345})
    with pytest.raises(store.StoreError, match="telegram:12345"):
        store.resolve_user_id_from_peer("telegram:12345")


def test_resolve_user_id_path_traversal_relies_on_user_dir(monkeypatch, tmp_path):
    """A peer string that is a path-traversal key in the index returns the mapped user_id.
    Defense-in-depth: user_dir() rejects the resolved value if it contains path separators.
    resolve_user_id_from_peer itself does not validate the peer string."""
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    _write_index(tmp_path, {"../../../etc/passwd": "alice"})
    # The lookup succeeds — it just returns the mapped user_id "alice"
    # (which is a valid user_id; the hostile key is the peer, not the value)
    result = store.resolve_user_id_from_peer("../../../etc/passwd")
    assert result == "alice"


# ---------------------------------------------------------------------------
# read_events() / write_events() — wrapped format only
# ---------------------------------------------------------------------------

def _sample_event() -> Event:
    return Event(id=1, date=date(2026, 5, 1), title="surgery", event_type="surgery")

def test_write_events_produces_wrapped_format(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    store.write_events("alice", [_sample_event()])
    path = tmp_path / "users" / "alice" / "events.json"
    raw = json.loads(path.read_text())
    assert "events" in raw
    assert "version" in raw
    assert raw["version"] == 1
    assert isinstance(raw["events"], list)

def test_read_events_wrapped_format(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    store.write_events("alice", [_sample_event()])
    events = store.read_events("alice")
    assert len(events) == 1
    assert events[0].id == 1

def test_read_events_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    events = store.read_events("alice")
    assert events == []

def test_read_events_raw_list_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    path = tmp_path / "users" / "alice"
    path.mkdir(parents=True, exist_ok=True)
    (path / "events.json").write_text(json.dumps([{"id": 1, "date": "2026-05-01"}]))
    with pytest.raises((ValueError, store.StoreError), match="wrapped format"):
        store.read_events("alice")

def test_read_write_events_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    events_in = [_sample_event(), Event(id=2, date=date(2026, 6, 1), title="appt", event_type="appointment")]
    store.write_events("alice", events_in)
    events_out = store.read_events("alice")
    assert len(events_out) == 2
    assert events_out[0].id == 1
    assert events_out[1].id == 2


def test_user_isolation(monkeypatch, tmp_path):
    monkeypatch.setenv("NUTRIOS_DATA_ROOT", str(tmp_path))
    store.append_jsonl("alice", "weigh_ins.jsonl", _make_weigh_in(1))
    # Bob has no weigh_ins
    assert store.tail_jsonl("bob", "weigh_ins.jsonl", 10) == []
    # Alice's file is unmodified
    tail = store.tail_jsonl("alice", "weigh_ins.jsonl", 10)
    assert len(tail) == 1
