"""Route normalizer output to the correct GTD tool branch.

Single entry point for all incoming messages. Deterministic routing only.
LLM is never called from this module — callers receive a needs_llm signal
and decide whether to invoke an appropriate skill.

Usage: python3 gtd_router.py '<raw_input>' <user_id> <telegram_chat_id>
"""

from __future__ import annotations

import json
import sys

from common import (
    Energy, IdeaStatus, ParkingLotReason, Priority,
    PromotionState, ReviewCadence, Source, TaskStatus,
)
from gtd_delegation import delegation
from gtd_normalize import normalize
from gtd_query import query
from gtd_review import review
from gtd_write import write_record


# ---------------------------------------------------------------------------
# Candidate builder helpers
# ---------------------------------------------------------------------------

def _task_from_candidate(
    candidate: dict,
    user_id: str,
    telegram_chat_id: str,
    status: TaskStatus = TaskStatus.active,
) -> dict:
    """Build a task record from normalizer candidate fields."""
    return {
        "record_type":      "task",
        "user_id":          user_id,
        "telegram_chat_id": telegram_chat_id,
        "title":            candidate.get("title") or "",
        "context":          candidate.get("context_hint") or "",
        "area":             candidate.get("area_hint") or "",
        "priority":         candidate.get("priority_hint") or Priority.normal,
        "energy":           Energy.medium,
        "duration_minutes": None,
        "status":           status,
        "delegate_to":      None,
        "waiting_for":      None,
        "notes":            None,
        "source":           Source.telegram_text,
        "completed_at":     None,
    }


def _idea_from_candidate(
    candidate: dict,
    user_id: str,
    telegram_chat_id: str,
) -> dict:
    """Build an idea record from normalizer candidate fields.

    area_hint carries the domain for idea captures (shared field name).
    """
    return {
        "record_type":      "idea",
        "user_id":          user_id,
        "telegram_chat_id": telegram_chat_id,
        "title":            candidate.get("title") or "",
        "domain":           candidate.get("area_hint") or "",
        "context":          candidate.get("context_hint") or "",
        "review_cadence":   ReviewCadence.monthly,
        "promotion_state":  PromotionState.raw,
        "spark_note":       None,
        "status":           IdeaStatus.active,
        "source":           Source.telegram_text,
        "last_reviewed_at": None,
        "promoted_task_id": None,
    }


def _parking_lot_from_candidate(
    candidate: dict,
    user_id: str,
    telegram_chat_id: str,
    reason: ParkingLotReason = ParkingLotReason.ambiguous_capture,
) -> dict:
    """Build a parking-lot record from normalizer candidate fields."""
    return {
        "record_type":      "parking_lot",
        "user_id":          user_id,
        "telegram_chat_id": telegram_chat_id,
        "raw_text":         candidate.get("title") or "",
        "source":           Source.telegram_text,
        "reason":           reason,
        "status":           TaskStatus.active,
    }


# ---------------------------------------------------------------------------
# Result factories
# ---------------------------------------------------------------------------

def _ok(branch: str, result: object) -> dict:
    return {"branch": branch, "result": result, "needs_llm": False}


def _llm(branch: str, result: object) -> dict:
    return {"branch": branch, "result": result, "needs_llm": True}


# ---------------------------------------------------------------------------
# Capture branch
# ---------------------------------------------------------------------------

def _handle_capture(
    intent: str,
    candidate: dict,
    user_id: str,
    telegram_chat_id: str,
) -> dict:
    """Attempt to write a capture; return needs_clarification on validation failure."""
    match intent:
        case "task_capture":
            record = _task_from_candidate(candidate, user_id, telegram_chat_id)
            record_type = "task"
        case "idea_capture":
            record = _idea_from_candidate(candidate, user_id, telegram_chat_id)
            record_type = "idea"
        case "delegation_capture":
            # Captured as a waiting task; waiting_for is resolved via LLM clarification if absent
            record = _task_from_candidate(candidate, user_id, telegram_chat_id, status=TaskStatus.waiting)
            record_type = "task"
        case _:
            record = _parking_lot_from_candidate(candidate, user_id, telegram_chat_id)
            record_type = "parking_lot"

    write_result = write_record(record, record_type, user_id)

    if write_result.get("status") == "ok":
        return _ok("capture", write_result)

    # Validation failed — surface missing fields so the LLM clarification skill can ask
    errors = write_result.get("errors", [])
    return _llm("capture", {
        "status":         "needs_clarification",
        "record_type":    record_type,
        "missing_fields": [e["field"] for e in errors],
        "candidate":      candidate,
        "errors":         errors,
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route(raw_input: str, user_id: str, telegram_chat_id: str) -> dict:
    """Route a raw message to the appropriate GTD tool branch.

    Never calls the LLM. Returns needs_llm: True when an LLM skill is required
    (low-confidence input, unknown intent, or capture with missing required fields).

    Args:
        raw_input: Raw text from the user.
        user_id: Caller's user_id for storage scoping and isolation.
        telegram_chat_id: Caller's Telegram chat ID stamped on written records.

    Returns:
        {
            branch:    "capture" | "retrieval_next" | "retrieval_waiting" |
                       "review" | "system" | "llm_fallback",
            result:    tool output, system dict, or normalizer output,
            needs_llm: bool,
        }
    """
    norm = normalize(raw_input)
    intent = norm["intent"]
    needs_llm = norm.get("needs_llm", False)
    candidate = norm.get("candidate", {})

    match intent:
        case "task_capture" | "idea_capture" | "delegation_capture":
            if needs_llm:
                # Confidence below threshold — normalizer is uncertain despite a hint
                return _llm("llm_fallback", norm)
            return _handle_capture(intent, candidate, user_id, telegram_chat_id)

        case "query_next":
            return _ok("retrieval_next", query(user_id))

        case "query_waiting":
            return _ok("retrieval_waiting", delegation(user_id))

        case "review_request":
            return _ok("review", review(user_id))

        case "start" | "help" | "settings" | "privacy":
            return _ok("system", {"intent": intent})

        case _:
            return _llm("llm_fallback", norm)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: gtd_router.py '<raw_input>' <user_id> <telegram_chat_id>")
        sys.exit(1)
    output = route(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(output, indent=2, default=str))
    sys.exit(0 if not output["needs_llm"] else 2)
