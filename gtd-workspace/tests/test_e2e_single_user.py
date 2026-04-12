"""End-to-end tests for single-user flows through gtd_router."""

import pytest
from common import append_jsonl, read_jsonl, user_path
from gtd_router import route


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tasks(user_id: str) -> list[dict]:
    return read_jsonl(user_path(user_id) / "tasks.jsonl")


def _ideas(user_id: str) -> list[dict]:
    return read_jsonl(user_path(user_id) / "ideas.jsonl")


def _section(result: dict, name: str) -> dict:
    return next(s for s in result["result"]["sections"] if s["name"] == name)


# ---------------------------------------------------------------------------
# 1. Task capture persists to tasks.jsonl
# ---------------------------------------------------------------------------

def test_task_capture_persists(storage, user_a, chat_a):
    result = route("/task call the customs broker @phone", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["result"]["status"] == "ok"
    tasks = _tasks(user_a)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "call the customs broker"
    assert tasks[0]["context"] == "@phone"
    assert tasks[0]["user_id"] == user_a


# ---------------------------------------------------------------------------
# 2. Captured task appears in /next retrieval
# ---------------------------------------------------------------------------

def test_captured_task_appears_in_next(storage, user_a, chat_a):
    route("/task review the watch listing @computer", user_a, chat_a)
    result = route("/next", user_a, chat_a)
    assert result["branch"] == "retrieval_next"
    titles = [t["title"] for t in result["result"]]
    assert "review the watch listing" in titles


# ---------------------------------------------------------------------------
# 3. Priority ordering is preserved through /next
# ---------------------------------------------------------------------------

def test_priority_ordering_in_next(storage, user_a, chat_a, make_task):
    normal = make_task(user_a, chat_a, title="Normal task", priority="normal")
    critical = make_task(user_a, chat_a, title="Critical task", priority="critical")
    append_jsonl(user_path(user_a) / "tasks.jsonl", normal)
    append_jsonl(user_path(user_a) / "tasks.jsonl", critical)
    result = route("/next", user_a, chat_a)
    assert result["result"][0]["title"] == "Critical task"


# ---------------------------------------------------------------------------
# 4. Idea capture persists to ideas.jsonl
# ---------------------------------------------------------------------------

def test_idea_capture_persists(storage, user_a, chat_a):
    result = route("/idea automate the listing workflow @ai-review", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["result"]["status"] == "ok"
    ideas = _ideas(user_a)
    assert len(ideas) == 1
    assert "automate" in ideas[0]["title"].lower()
    assert ideas[0]["domain"] == "ai-automation"
    assert ideas[0]["context"] == "@ai-review"


# ---------------------------------------------------------------------------
# 5. Task with no context triggers clarification — not written to storage
# ---------------------------------------------------------------------------

def test_task_without_context_triggers_clarification(storage, user_a, chat_a):
    result = route("/task sort out the paperwork", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is True
    assert result["result"]["status"] == "needs_clarification"
    assert "context" in result["result"]["missing_fields"]
    # Nothing written
    assert _tasks(user_a) == []


# ---------------------------------------------------------------------------
# 6. NL high-confidence task capture works end-to-end
# ---------------------------------------------------------------------------

def test_nl_task_capture_end_to_end(storage, user_a, chat_a):
    result = route("I need to send the invoice @computer", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is False
    assert result["result"]["status"] == "ok"
    tasks = _tasks(user_a)
    assert any("invoice" in t.get("title", "").lower() for t in tasks)


# ---------------------------------------------------------------------------
# 7. Review flags task with missing metadata
# ---------------------------------------------------------------------------

def test_review_flags_task_missing_metadata(storage, user_a, chat_a, make_task):
    task = make_task(user_a, chat_a, context="", area="")
    append_jsonl(user_path(user_a) / "tasks.jsonl", task)
    result = route("/review", user_a, chat_a)
    assert result["branch"] == "review"
    assert _section(result, "active_tasks_missing_metadata")["count"] == 1


# ---------------------------------------------------------------------------
# 8. Review is clean for tasks with full metadata
# ---------------------------------------------------------------------------

def test_review_clean_for_complete_metadata(storage, user_a, chat_a, make_task):
    task = make_task(user_a, chat_a, context="@computer", area="business")
    append_jsonl(user_path(user_a) / "tasks.jsonl", task)
    result = route("/review", user_a, chat_a)
    assert _section(result, "active_tasks_missing_metadata")["count"] == 0


# ---------------------------------------------------------------------------
# 9. Delegation listing groups by person
# ---------------------------------------------------------------------------

def test_delegation_listing_groups_by_person(storage, user_a, chat_a, make_task):
    delegated = make_task(
        user_a, chat_a,
        title="Chase invoice approval",
        status="delegated",
        delegate_to="Alice",
    )
    append_jsonl(user_path(user_a) / "tasks.jsonl", delegated)
    result = route("/waiting", user_a, chat_a)
    assert result["branch"] == "retrieval_waiting"
    people = [g["person"] for g in result["result"]["groups"]]
    assert "Alice" in people


# ---------------------------------------------------------------------------
# 10. Delegation capture without person returns clarification
# ---------------------------------------------------------------------------

def test_delegation_capture_without_person_needs_clarification(storage, user_a, chat_a):
    # "waiting for" matches delegation pattern; task needs waiting_for → clarification
    result = route("waiting for Alice to send the invoice", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is True
    assert result["result"]["status"] == "needs_clarification"
    assert "waiting_for" in result["result"]["missing_fields"]
    assert _tasks(user_a) == []
