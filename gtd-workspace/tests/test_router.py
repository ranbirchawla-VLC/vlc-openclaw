"""Tests for gtd_router.py — routing decisions and capture handling."""

import pytest
from gtd_router import route


# ---------------------------------------------------------------------------
# System commands
# ---------------------------------------------------------------------------

def test_start_routes_to_system(storage, user_a, chat_a):
    result = route("/start", user_a, chat_a)
    assert result["branch"] == "system"
    assert result["result"]["intent"] == "start"
    assert result["needs_llm"] is False


def test_help_routes_to_system(storage, user_a, chat_a):
    result = route("/help", user_a, chat_a)
    assert result["branch"] == "system"
    assert result["result"]["intent"] == "help"
    assert result["needs_llm"] is False


def test_settings_routes_to_system(storage, user_a, chat_a):
    result = route("/settings", user_a, chat_a)
    assert result["branch"] == "system"
    assert result["result"]["intent"] == "settings"


def test_privacy_routes_to_system(storage, user_a, chat_a):
    result = route("/privacy", user_a, chat_a)
    assert result["branch"] == "system"
    assert result["result"]["intent"] == "privacy"


# ---------------------------------------------------------------------------
# Retrieval commands
# ---------------------------------------------------------------------------

def test_next_routes_to_retrieval_next(storage, user_a, chat_a):
    result = route("/next", user_a, chat_a)
    assert result["branch"] == "retrieval_next"
    assert isinstance(result["result"], list)
    assert result["needs_llm"] is False


def test_waiting_routes_to_retrieval_waiting(storage, user_a, chat_a):
    result = route("/waiting", user_a, chat_a)
    assert result["branch"] == "retrieval_waiting"
    assert "groups" in result["result"]
    assert result["needs_llm"] is False


def test_review_command_routes_to_review(storage, user_a, chat_a):
    result = route("/review", user_a, chat_a)
    assert result["branch"] == "review"
    assert "sections" in result["result"]
    assert result["needs_llm"] is False


def test_nl_query_waiting_routes_to_retrieval_waiting(storage, user_a, chat_a):
    result = route("what am I waiting on today", user_a, chat_a)
    assert result["branch"] == "retrieval_waiting"
    assert result["needs_llm"] is False


# ---------------------------------------------------------------------------
# Task capture — explicit command
# ---------------------------------------------------------------------------

def test_task_with_context_captures_ok(storage, user_a, chat_a):
    result = route("/task call the customs broker @phone", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is False
    assert result["result"]["status"] == "ok"
    assert result["result"]["record_type"] == "task"


def test_task_without_context_needs_clarification(storage, user_a, chat_a):
    result = route("/task sort out the paperwork", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is True
    assert result["result"]["status"] == "needs_clarification"
    assert "context" in result["result"]["missing_fields"]


# ---------------------------------------------------------------------------
# Task capture — natural language
# ---------------------------------------------------------------------------

def test_nl_strong_pattern_task_captures_ok(storage, user_a, chat_a):
    # "I need to" is a strong pattern (confidence 0.85) — no LLM needed
    result = route("I need to send the invoice @computer", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is False
    assert result["result"]["status"] == "ok"


# ---------------------------------------------------------------------------
# Idea capture
# ---------------------------------------------------------------------------

def test_idea_with_context_and_domain_captures_ok(storage, user_a, chat_a):
    result = route("/idea automate the listing workflow @ai-review", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is False
    assert result["result"]["status"] == "ok"
    assert result["result"]["record_type"] == "idea"


def test_idea_without_context_needs_clarification(storage, user_a, chat_a):
    # No @context → idea validation fails (context required for ideas)
    result = route("/idea what if we automated valuations", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is True
    assert result["result"]["status"] == "needs_clarification"
    assert "context" in result["result"]["missing_fields"]


# ---------------------------------------------------------------------------
# Delegation capture
# ---------------------------------------------------------------------------

def test_delegation_capture_needs_clarification_for_waiting_for(storage, user_a, chat_a):
    # "chasing" matches delegation pattern; task built with status=waiting, no waiting_for
    result = route("chasing Alice for the contract", user_a, chat_a)
    assert result["branch"] == "capture"
    assert result["needs_llm"] is True
    assert result["result"]["status"] == "needs_clarification"
    assert "waiting_for" in result["result"]["missing_fields"]


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

def test_empty_input_routes_to_llm_fallback(storage, user_a, chat_a):
    result = route("", user_a, chat_a)
    assert result["branch"] == "llm_fallback"
    assert result["needs_llm"] is True


def test_unrecognised_input_routes_to_llm_fallback(storage, user_a, chat_a):
    # No intent pattern matches — intent stays "unknown"
    result = route("asdfghjkl qwerty zxcvb", user_a, chat_a)
    assert result["branch"] == "llm_fallback"
    assert result["needs_llm"] is True
