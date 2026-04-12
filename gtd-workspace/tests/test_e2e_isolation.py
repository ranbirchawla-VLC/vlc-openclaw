"""End-to-end tests for multi-user isolation through gtd_router."""

import pytest
from common import append_jsonl, read_jsonl, user_path
from gtd_router import route
from gtd_write import write_record


# ---------------------------------------------------------------------------
# 1. User A's tasks are not visible to User B
# ---------------------------------------------------------------------------

def test_user_a_tasks_invisible_to_user_b(storage, user_a, chat_a, user_b, chat_b):
    route("/task call the customs broker @phone", user_a, chat_a)
    result = route("/next", user_b, chat_b)
    assert result["result"] == []


# ---------------------------------------------------------------------------
# 2. User B's tasks are not visible to User A
# ---------------------------------------------------------------------------

def test_user_b_tasks_invisible_to_user_a(storage, user_a, chat_a, user_b, chat_b):
    route("/task send the invoice @computer", user_b, chat_b)
    result = route("/next", user_a, chat_a)
    assert result["result"] == []


# ---------------------------------------------------------------------------
# 3. Each user sees only their own tasks
# ---------------------------------------------------------------------------

def test_users_see_only_their_own_tasks(storage, user_a, chat_a, user_b, chat_b):
    route("/task task for user A @phone", user_a, chat_a)
    route("/task task for user B @computer", user_b, chat_b)

    a_result = route("/next", user_a, chat_a)
    b_result = route("/next", user_b, chat_b)

    assert len(a_result["result"]) == 1
    assert "user A" in a_result["result"][0]["title"]
    assert len(b_result["result"]) == 1
    assert "user B" in b_result["result"][0]["title"]


# ---------------------------------------------------------------------------
# 4. Cross-user write attempt is rejected
# ---------------------------------------------------------------------------

def test_cross_user_write_rejected(storage, user_a, chat_a, user_b):
    record = {
        "record_type":      "task",
        "user_id":          user_a,      # record belongs to user_a
        "telegram_chat_id": chat_a,
        "title":            "Sneaky write",
        "context":          "@computer",
        "area":             "business",
        "priority":         "normal",
        "energy":           "medium",
        "status":           "active",
        "source":           "telegram_text",
        "duration_minutes": None,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "completed_at":     None,
    }
    result = write_record(record, "task", user_b)   # user_b attempts to write
    assert result["status"] == "error"
    assert any(e["field"] == "user_id" for e in result["errors"])
    # user_a's storage must remain empty
    assert read_jsonl(user_path(user_a) / "tasks.jsonl") == []


# ---------------------------------------------------------------------------
# 5. Review scans only the requesting user's own records
# ---------------------------------------------------------------------------

def test_review_scans_only_own_records(storage, user_a, chat_a, user_b, chat_b, make_task):
    # Seed user_b with a task missing context
    bad_task = make_task(user_b, chat_b, context="", area="")
    append_jsonl(user_path(user_b) / "tasks.jsonl", bad_task)

    result = route("/review", user_a, chat_a)
    section = next(
        s for s in result["result"]["sections"]
        if s["name"] == "active_tasks_missing_metadata"
    )
    assert section["count"] == 0


# ---------------------------------------------------------------------------
# 6. Path traversal user_id raises ValueError
# ---------------------------------------------------------------------------

def test_path_traversal_single_dot_dot_raises(storage):
    with pytest.raises(ValueError, match="invalid"):
        user_path("../evil")


def test_path_traversal_double_dot_dot_raises(storage):
    with pytest.raises(ValueError, match="invalid"):
        user_path("../../etc/passwd")


def test_path_traversal_slash_only_raises(storage):
    with pytest.raises(ValueError, match="invalid"):
        user_path("/absolute/path")


# ---------------------------------------------------------------------------
# 7. Route with empty user_id raises ValueError
# ---------------------------------------------------------------------------

def test_route_empty_user_id_raises(storage, chat_a):
    with pytest.raises(ValueError):
        route("/next", "", chat_a)
