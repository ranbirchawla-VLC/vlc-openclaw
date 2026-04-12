"""Tests for gtd_normalize.py — 20 cases covering commands, NL, and edge cases."""

import pytest

from gtd_normalize import normalize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(result: dict) -> dict:
    return result["candidate"]


# ---------------------------------------------------------------------------
# 1. Explicit /task command with body
# ---------------------------------------------------------------------------

def test_task_command_with_text() -> None:
    r = normalize("/task Call the customs broker")
    assert r["intent"] == "task_capture"
    assert r["confidence"] == 1.0
    assert r["needs_llm"] is False
    assert r["status"] == "ok"
    assert "customs broker" in _candidate(r)["title"]


# ---------------------------------------------------------------------------
# 2. Explicit /idea command with body
# ---------------------------------------------------------------------------

def test_idea_command_with_text() -> None:
    r = normalize("/idea Build a watch scanner agent")
    assert r["intent"] == "idea_capture"
    assert r["confidence"] == 1.0
    assert r["needs_llm"] is False
    assert "watch scanner" in _candidate(r)["title"]


# ---------------------------------------------------------------------------
# 3. /idea with known domain keyword — domain hint extracted
# ---------------------------------------------------------------------------

def test_idea_command_extracts_domain() -> None:
    r = normalize("/idea automate the listing workflow with an agent")
    assert r["intent"] == "idea_capture"
    assert _candidate(r)["area_hint"] in ("ai-automation", "watch-business")


# ---------------------------------------------------------------------------
# 4. /next command
# ---------------------------------------------------------------------------

def test_next_command() -> None:
    r = normalize("/next")
    assert r["intent"] == "query_next"
    assert r["confidence"] == 1.0
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 5. /review command
# ---------------------------------------------------------------------------

def test_review_command() -> None:
    r = normalize("/review")
    assert r["intent"] == "review_request"
    assert r["confidence"] == 1.0
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 6. /waiting command
# ---------------------------------------------------------------------------

def test_waiting_command() -> None:
    r = normalize("/waiting")
    assert r["intent"] == "query_waiting"
    assert r["confidence"] == 1.0
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 7. Natural language task capture — explicit "remind me to"
# ---------------------------------------------------------------------------

def test_nl_task_remind_me_to() -> None:
    r = normalize("remind me to call the broker")
    assert r["intent"] == "task_capture"
    assert r["confidence"] >= 0.8
    assert r["needs_llm"] is False
    assert "call the broker" in _candidate(r)["title"]


# ---------------------------------------------------------------------------
# 8. Natural language task with "I need to"
# ---------------------------------------------------------------------------

def test_nl_task_i_need_to() -> None:
    r = normalize("I need to renew the business insurance")
    assert r["intent"] == "task_capture"
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 9. Natural language idea capture — "idea:" prefix
# ---------------------------------------------------------------------------

def test_nl_idea_prefix() -> None:
    r = normalize("idea: build a watch scanner agent")
    assert r["intent"] == "idea_capture"
    assert r["needs_llm"] is False
    assert "watch scanner" in _candidate(r)["title"]


# ---------------------------------------------------------------------------
# 10. Natural language idea — "what if" pattern
# ---------------------------------------------------------------------------

def test_nl_idea_what_if() -> None:
    r = normalize("what if we automated the listing workflow")
    assert r["intent"] == "idea_capture"
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 11. Natural language delegation — "waiting on [name]"
# ---------------------------------------------------------------------------

def test_nl_delegation_waiting_on() -> None:
    r = normalize("waiting on Alex for the invoice")
    assert r["intent"] == "delegation_capture"
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 12. Natural language with context hint
# ---------------------------------------------------------------------------

def test_nl_task_with_context_hint() -> None:
    r = normalize("call the customs broker @phone")
    assert _candidate(r)["context_hint"] == "@phone"
    # context is present so context should not be in missing_fields
    assert "context" not in _candidate(r)["missing_fields"]


# ---------------------------------------------------------------------------
# 13. Natural language with priority hint — "urgent"
# ---------------------------------------------------------------------------

def test_nl_priority_urgent() -> None:
    r = normalize("urgent: fix the webhook")
    assert _candidate(r)["priority_hint"] == "critical"


# ---------------------------------------------------------------------------
# 14. Ambiguous input — should set needs_llm = True
# ---------------------------------------------------------------------------

def test_ambiguous_input_needs_llm() -> None:
    r = normalize("the thing with the form")
    assert r["needs_llm"] is True


# ---------------------------------------------------------------------------
# 15. Very short vague input
# ---------------------------------------------------------------------------

def test_vague_single_word() -> None:
    r = normalize("stuff")
    assert r["needs_llm"] is True
    assert r["intent"] == "unknown"


# ---------------------------------------------------------------------------
# 16. Voice-transcription-style messy input
# ---------------------------------------------------------------------------

def test_voice_transcription_task() -> None:
    r = normalize("uh yeah i need to uh call the watch broker about the customs thing you know")
    assert r["intent"] == "task_capture"
    assert r["needs_llm"] is False
    # Filler words removed from title
    assert "uh" not in _candidate(r)["title"]


# ---------------------------------------------------------------------------
# 17. Multiple signals: priority + context + delegation
# ---------------------------------------------------------------------------

def test_multiple_signals() -> None:
    r = normalize("urgent follow up with Marcus about the invoice @phone")
    assert r["intent"] == "delegation_capture"
    c = _candidate(r)
    assert c["priority_hint"] == "critical"
    assert c["context_hint"] == "@phone"


# ---------------------------------------------------------------------------
# 18. /capture with body — attempts NL classification
# ---------------------------------------------------------------------------

def test_capture_with_body_classifies() -> None:
    r = normalize("/capture remind me to submit the quarterly report")
    # Body is classifiable as task
    assert r["intent"] == "task_capture"
    assert r["needs_llm"] is False


# ---------------------------------------------------------------------------
# 19. /capture with ambiguous body
# ---------------------------------------------------------------------------

def test_capture_ambiguous_body() -> None:
    r = normalize("/capture this could be interesting")
    # Weak or no match — either uncertain or low confidence
    assert r["needs_llm"] is True or r["confidence"] < 0.7


# ---------------------------------------------------------------------------
# 20. Empty input
# ---------------------------------------------------------------------------

def test_empty_string() -> None:
    r = normalize("")
    assert r["intent"] == "unknown"
    assert r["needs_llm"] is True
    assert r["status"] == "uncertain"


# ---------------------------------------------------------------------------
# 21. Whitespace-only input
# ---------------------------------------------------------------------------

def test_whitespace_only() -> None:
    r = normalize("   ")
    assert r["intent"] == "unknown"
    assert r["needs_llm"] is True


# ---------------------------------------------------------------------------
# 22. Task mentioning a person — should NOT be delegation without trigger
# ---------------------------------------------------------------------------

def test_task_with_person_mention_no_delegation_trigger() -> None:
    r = normalize("call Marcus about the invoice")
    # No delegation trigger phrase — should be task or uncertain, NOT delegation
    assert r["intent"] != "delegation_capture"


# ---------------------------------------------------------------------------
# 23. Output contract shape is always present
# ---------------------------------------------------------------------------

def test_output_contract_shape() -> None:
    r = normalize("some random input that may or may not classify")
    assert "status" in r
    assert "intent" in r
    assert "confidence" in r
    assert "needs_llm" in r
    assert "candidate" in r
    c = r["candidate"]
    assert "title" in c
    assert "context_hint" in c
    assert "priority_hint" in c
    assert "area_hint" in c
    assert "missing_fields" in c


# ---------------------------------------------------------------------------
# 24. /task missing body — title in missing_fields
# ---------------------------------------------------------------------------

def test_task_command_no_body() -> None:
    r = normalize("/task")
    assert r["intent"] == "task_capture"
    assert "title" in _candidate(r)["missing_fields"]


# ---------------------------------------------------------------------------
# 25. query_waiting via natural language
# ---------------------------------------------------------------------------

def test_nl_query_waiting() -> None:
    r = normalize("what am I waiting on from the team")
    assert r["intent"] == "query_waiting"
    assert r["needs_llm"] is False
