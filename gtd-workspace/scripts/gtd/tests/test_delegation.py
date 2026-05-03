"""Tests for scripts/gtd/delegation.py."""

import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import GTDError
from delegation import delegation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tasks(storage: Path, user_id: str, records: list[dict]) -> None:
    path = storage / "gtd-agent" / "users" / user_id / "tasks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _t(title: str, waiting_for: str | None = None) -> dict:
    r = {"id": f"t-{title[:4]}", "record_type": "task", "title": title,
         "context": "@work", "created_at": "2026-04-01T00:00:00+00:00"}
    if waiting_for is not None:
        r["waiting_for"] = waiting_for
    return r


# ---------------------------------------------------------------------------
# 1. Empty file returns empty groups
# ---------------------------------------------------------------------------

def test_delegation_empty_returns_empty(storage: Path) -> None:
    result = delegation(requesting_user_id="user1")
    assert result["groups"] == []
    assert result["total_items"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# 2. Tasks without waiting_for are excluded
# ---------------------------------------------------------------------------

def test_delegation_excludes_tasks_without_waiting_for(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("No waiting"),
        _t("Also no waiting"),
    ])
    result = delegation(requesting_user_id="user1")
    assert result["groups"] == []
    assert result["total_items"] == 0


# ---------------------------------------------------------------------------
# 3. Groups tasks by waiting_for person
# ---------------------------------------------------------------------------

def test_delegation_groups_by_person(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Ask Alex A", "Alex"),
        _t("Ask Maria", "Maria"),
        _t("Ask Alex B", "Alex"),
    ])
    result = delegation(requesting_user_id="user1", limit=25)
    assert result["total_items"] == 3
    groups = {g["person"]: g for g in result["groups"]}
    assert groups["Alex"]["count"] == 2
    assert groups["Maria"]["count"] == 1


# ---------------------------------------------------------------------------
# 4. Person filter returns only matching group
# ---------------------------------------------------------------------------

def test_delegation_person_filter(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("Ask Alex", "Alex"),
        _t("Ask Maria", "Maria"),
    ])
    result = delegation(person="Alex", requesting_user_id="user1", limit=25)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["person"] == "Alex"
    assert result["total_items"] == 1


# ---------------------------------------------------------------------------
# 5. Person filter returns empty when no match
# ---------------------------------------------------------------------------

def test_delegation_person_filter_no_match(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t("Ask Alex", "Alex")])
    result = delegation(person="nobody", requesting_user_id="user1", limit=25)
    assert result["groups"] == []
    assert result["total_items"] == 0


# ---------------------------------------------------------------------------
# 6. Limit caps items per group; truncated=True when any group exceeds limit
# ---------------------------------------------------------------------------

def test_delegation_limit_per_group_and_truncated(storage: Path) -> None:
    _write_tasks(storage, "user1", [_t(f"Ask Alex {i}", "Alex") for i in range(5)])
    result = delegation(limit=3, requesting_user_id="user1")
    alex_group = result["groups"][0]
    assert len(alex_group["items"]) == 3
    assert alex_group["count"] == 5
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# 7. Groups returned in alphabetical order by person name
# ---------------------------------------------------------------------------

def test_delegation_groups_sorted_by_person(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("C task", "Charlie"),
        _t("A task", "Alice"),
        _t("B task", "Bob"),
    ])
    result = delegation(requesting_user_id="user1", limit=25)
    names = [g["person"] for g in result["groups"]]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# 8. total_items counts all waiting_for tasks across all persons
# ---------------------------------------------------------------------------

def test_delegation_total_items_across_persons(storage: Path) -> None:
    _write_tasks(storage, "user1", [
        _t("A1", "Alice"), _t("A2", "Alice"),
        _t("B1", "Bob"),
        _t("No wait"),
    ])
    result = delegation(requesting_user_id="user1", limit=25)
    assert result["total_items"] == 3


# ---------------------------------------------------------------------------
# 9. Empty requesting_user_id raises internal_error
# ---------------------------------------------------------------------------

def test_delegation_empty_user_id_raises(storage: Path) -> None:
    with pytest.raises(GTDError) as exc_info:
        delegation(requesting_user_id="")
    assert exc_info.value.code == "internal_error"


# ---------------------------------------------------------------------------
# 10. OTEL span emitted with result attributes
# ---------------------------------------------------------------------------

def test_delegation_emits_otel_span(storage: Path) -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    _write_tasks(storage, "user1", [
        _t("Ask Alex", "Alex"), _t("Ask Maria", "Maria"),
    ])
    delegation(requesting_user_id="user1", limit=25)

    spans = exporter.get_finished_spans()
    span = next((s for s in spans if s.name == "gtd.delegation"), None)
    assert span is not None
    attrs = dict(span.attributes)
    assert attrs.get("result.total_items") == 2
    assert attrs.get("result.group_count") == 2
