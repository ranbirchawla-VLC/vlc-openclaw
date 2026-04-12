"""Tests for common.py — JSONL I/O, path resolution, isolation guard, enums."""

import re
import sys
from pathlib import Path

import pytest

from common import (
    Source, TaskStatus, IdeaStatus, Priority, Energy,
    ReviewCadence, PromotionState, ParkingLotReason,
    append_jsonl, read_jsonl, user_path, assert_user_match,
    new_id, now_iso,
)


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def test_read_missing_file_returns_empty(tmp_path: Path) -> None:
    result = read_jsonl(tmp_path / "nonexistent.jsonl")
    assert result == []


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    records = [{"id": "1", "title": "one"}, {"id": "2", "title": "two"}]
    for r in records:
        append_jsonl(path, r)
    assert read_jsonl(path) == records


def test_append_creates_file_and_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "tasks.jsonl"
    assert not path.exists()
    append_jsonl(path, {"x": 1})
    assert path.exists()
    assert read_jsonl(path) == [{"x": 1}]


def test_append_is_additive(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    append_jsonl(path, {"n": 1})
    append_jsonl(path, {"n": 2})
    append_jsonl(path, {"n": 3})
    result = read_jsonl(path)
    assert len(result) == 3
    assert [r["n"] for r in result] == [1, 2, 3]


def test_jsonl_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    append_jsonl(path, {"title": "café résumé"})
    result = read_jsonl(path)
    assert result[0]["title"] == "café résumé"


# ---------------------------------------------------------------------------
# User path resolution
# ---------------------------------------------------------------------------

def test_user_path_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    p = user_path("user123")
    assert p == tmp_path / "gtd-agent" / "users" / "user123"
    assert p.exists()


def test_user_path_creates_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    p = user_path("newuser")
    assert p.is_dir()


def test_user_path_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        user_path("")


def test_user_path_rejects_whitespace() -> None:
    with pytest.raises(ValueError):
        user_path("   ")


def test_user_path_different_users_separate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTD_STORAGE_ROOT", str(tmp_path))
    p1 = user_path("alice")
    p2 = user_path("bob")
    assert p1 != p2


# ---------------------------------------------------------------------------
# Isolation guard
# ---------------------------------------------------------------------------

def test_isolation_guard_passes() -> None:
    assert_user_match("user1", "user1")  # must not raise


def test_isolation_guard_raises_on_mismatch() -> None:
    with pytest.raises(ValueError, match="isolation violation"):
        assert_user_match("user1", "user2")


def test_isolation_guard_case_sensitive() -> None:
    with pytest.raises(ValueError):
        assert_user_match("User1", "user1")


# ---------------------------------------------------------------------------
# ID and timestamp helpers
# ---------------------------------------------------------------------------

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_new_id_is_uuid4_format() -> None:
    assert _UUID4_RE.match(new_id())


def test_new_id_is_unique() -> None:
    ids = {new_id() for _ in range(200)}
    assert len(ids) == 200


def test_now_iso_is_iso8601() -> None:
    ts = now_iso()
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)


def test_now_iso_is_utc() -> None:
    ts = now_iso()
    assert "+00:00" in ts or ts.endswith("Z")


# ---------------------------------------------------------------------------
# Enum values match spec exactly
# ---------------------------------------------------------------------------

def test_source_values() -> None:
    assert {m.value for m in Source} == {
        "telegram_text", "telegram_voice", "alexa", "manual", "import"
    }


def test_task_status_values() -> None:
    assert {m.value for m in TaskStatus} == {
        "active", "waiting", "delegated", "done", "cancelled", "archived"
    }


def test_idea_status_values() -> None:
    assert {m.value for m in IdeaStatus} == {
        "active", "on_hold", "archived", "promoted"
    }


def test_priority_values() -> None:
    assert {m.value for m in Priority} == {"low", "normal", "high", "critical"}


def test_energy_values() -> None:
    assert {m.value for m in Energy} == {"low", "medium", "high"}


def test_review_cadence_values() -> None:
    assert {m.value for m in ReviewCadence} == {"weekly", "monthly", "quarterly"}


def test_promotion_state_values() -> None:
    assert {m.value for m in PromotionState} == {
        "raw", "incubating", "promoted_to_task", "promoted_to_project", "archived"
    }


def test_parking_lot_reason_values() -> None:
    assert {m.value for m in ParkingLotReason} == {
        "ambiguous_capture", "missing_required_context", "low_confidence_parse"
    }
