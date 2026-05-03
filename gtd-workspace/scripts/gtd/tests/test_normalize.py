"""Tests for scripts/gtd/normalize.py.

25 behavioral tests ported from gtd-workspace/tests/test_normalize.py (attribute access rewrite).
6 new tests for the typed Pydantic contract and OTEL span.
"""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from normalize import Classification, Intent, normalize


# ---------------------------------------------------------------------------
# 1. /task command with body
# ---------------------------------------------------------------------------

def test_task_command_with_text() -> None:
    r = normalize("/task Call the customs broker")
    assert r.intent == "task_capture"
    assert r.confidence == 1.0
    assert r.needs_llm is False
    assert "customs broker" in r.candidate.title


# ---------------------------------------------------------------------------
# 2. /idea command with body
# ---------------------------------------------------------------------------

def test_idea_command_with_text() -> None:
    r = normalize("/idea Build a watch scanner agent")
    assert r.intent == "idea_capture"
    assert r.confidence == 1.0
    assert r.needs_llm is False
    assert "watch scanner" in r.candidate.title


# ---------------------------------------------------------------------------
# 3. /idea with known domain keyword
# ---------------------------------------------------------------------------

def test_idea_command_extracts_domain() -> None:
    r = normalize("/idea automate the listing workflow with an agent")
    assert r.intent == "idea_capture"
    assert r.candidate.area_hint in ("ai-automation", "watch-business")


# ---------------------------------------------------------------------------
# 4. /next command
# ---------------------------------------------------------------------------

def test_next_command() -> None:
    r = normalize("/next")
    assert r.intent == "query_next"
    assert r.confidence == 1.0
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 5. /review command
# ---------------------------------------------------------------------------

def test_review_command() -> None:
    r = normalize("/review")
    assert r.intent == "review_request"
    assert r.confidence == 1.0
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 6. /waiting command
# ---------------------------------------------------------------------------

def test_waiting_command() -> None:
    r = normalize("/waiting")
    assert r.intent == "query_waiting"
    assert r.confidence == 1.0
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 7. NL task — "remind me to"
# ---------------------------------------------------------------------------

def test_nl_task_remind_me_to() -> None:
    r = normalize("remind me to call the broker")
    assert r.intent == "task_capture"
    assert r.confidence >= 0.8
    assert r.needs_llm is False
    assert "call the broker" in r.candidate.title


# ---------------------------------------------------------------------------
# 8. NL task — "I need to"
# ---------------------------------------------------------------------------

def test_nl_task_i_need_to() -> None:
    r = normalize("I need to renew the business insurance")
    assert r.intent == "task_capture"
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 9. NL idea — "idea:" prefix
# ---------------------------------------------------------------------------

def test_nl_idea_prefix() -> None:
    r = normalize("idea: build a watch scanner agent")
    assert r.intent == "idea_capture"
    assert r.needs_llm is False
    assert "watch scanner" in r.candidate.title


# ---------------------------------------------------------------------------
# 10. NL idea — "what if"
# ---------------------------------------------------------------------------

def test_nl_idea_what_if() -> None:
    r = normalize("what if we automated the listing workflow")
    assert r.intent == "idea_capture"
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 11. NL delegation — "waiting on"
# ---------------------------------------------------------------------------

def test_nl_delegation_waiting_on() -> None:
    r = normalize("waiting on Alex for the invoice")
    assert r.intent == "delegation_capture"
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 12. NL task with context hint
# ---------------------------------------------------------------------------

def test_nl_task_with_context_hint() -> None:
    r = normalize("call the customs broker @phone")
    assert r.candidate.context_hint == "@phone"
    assert "context" not in r.candidate.missing_fields


# ---------------------------------------------------------------------------
# 13. Priority hint — "urgent"
# ---------------------------------------------------------------------------

def test_nl_priority_urgent() -> None:
    r = normalize("urgent: fix the webhook")
    assert r.candidate.priority_hint == "critical"


# ---------------------------------------------------------------------------
# 14. Ambiguous input — needs_llm True
# ---------------------------------------------------------------------------

def test_ambiguous_input_needs_llm() -> None:
    r = normalize("the thing with the form")
    assert r.needs_llm is True


# ---------------------------------------------------------------------------
# 15. Very short vague input
# ---------------------------------------------------------------------------

def test_vague_single_word() -> None:
    r = normalize("stuff")
    assert r.needs_llm is True
    assert r.intent == "unknown"


# ---------------------------------------------------------------------------
# 16. Voice-transcription-style input
# ---------------------------------------------------------------------------

def test_voice_transcription_task() -> None:
    r = normalize("uh yeah i need to uh call the watch broker about the customs thing you know")
    assert r.intent == "task_capture"
    assert r.needs_llm is False
    assert "uh" not in r.candidate.title


# ---------------------------------------------------------------------------
# 17. Multiple signals: priority + context + delegation
# ---------------------------------------------------------------------------

def test_multiple_signals() -> None:
    r = normalize("urgent follow up with Marcus about the invoice @phone")
    assert r.intent == "delegation_capture"
    assert r.candidate.priority_hint == "critical"
    assert r.candidate.context_hint == "@phone"


# ---------------------------------------------------------------------------
# 18. /capture with classifiable body
# ---------------------------------------------------------------------------

def test_capture_with_body_classifies() -> None:
    r = normalize("/capture remind me to submit the quarterly report")
    assert r.intent == "task_capture"
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 19. /capture with ambiguous body
# ---------------------------------------------------------------------------

def test_capture_ambiguous_body() -> None:
    r = normalize("/capture this could be interesting")
    assert r.needs_llm is True or r.confidence < 0.7


# ---------------------------------------------------------------------------
# 20. Empty input
# ---------------------------------------------------------------------------

def test_empty_string() -> None:
    r = normalize("")
    assert r.intent == "unknown"
    assert r.needs_llm is True


# ---------------------------------------------------------------------------
# 21. Whitespace-only input
# ---------------------------------------------------------------------------

def test_whitespace_only() -> None:
    r = normalize("   ")
    assert r.intent == "unknown"
    assert r.needs_llm is True


# ---------------------------------------------------------------------------
# 22. Task with person mention — not delegation without trigger
# ---------------------------------------------------------------------------

def test_task_with_person_mention_no_delegation_trigger() -> None:
    r = normalize("call Marcus about the invoice")
    assert r.intent != "delegation_capture"


# ---------------------------------------------------------------------------
# 23. Output contract shape
# ---------------------------------------------------------------------------

def test_output_contract_shape() -> None:
    r = normalize("some random input that may or may not classify")
    assert isinstance(r, Classification)
    assert isinstance(r.intent, Intent)
    assert isinstance(r.confidence, float)
    assert isinstance(r.needs_llm, bool)
    assert r.candidate.title is None or isinstance(r.candidate.title, str)
    assert r.candidate.context_hint is None or isinstance(r.candidate.context_hint, str)
    assert isinstance(r.candidate.priority_hint, str)
    assert isinstance(r.candidate.missing_fields, list)


# ---------------------------------------------------------------------------
# 24. /task missing body — title in missing_fields
# ---------------------------------------------------------------------------

def test_task_command_no_body() -> None:
    r = normalize("/task")
    assert r.intent == "task_capture"
    assert "title" in r.candidate.missing_fields


# ---------------------------------------------------------------------------
# 25. query_waiting via natural language
# ---------------------------------------------------------------------------

def test_nl_query_waiting() -> None:
    r = normalize("what am I waiting on from the team")
    assert r.intent == "query_waiting"
    assert r.needs_llm is False


# ---------------------------------------------------------------------------
# 26 (new). Classification is a Pydantic model instance
# ---------------------------------------------------------------------------

def test_returns_pydantic_model() -> None:
    r = normalize("remind me to call the broker")
    assert isinstance(r, Classification)
    assert isinstance(r.intent, Intent)


# ---------------------------------------------------------------------------
# 27 (new). Intent enum value matches string for str-enum comparison
# ---------------------------------------------------------------------------

def test_intent_enum_str_comparison() -> None:
    r = normalize("/task Call Alex")
    assert r.intent == Intent.task_capture
    assert r.intent == "task_capture"


# ---------------------------------------------------------------------------
# 28 (new). Candidate fields have correct types for all non-None cases
# ---------------------------------------------------------------------------

def test_candidate_field_types() -> None:
    r = normalize("/task Call @phone")
    assert isinstance(r.candidate.title, (str, type(None)))
    assert isinstance(r.candidate.context_hint, (str, type(None)))
    assert isinstance(r.candidate.priority_hint, str)
    assert r.candidate.priority_hint in ("normal", "high", "critical", "low")
    assert isinstance(r.candidate.missing_fields, list)


# ---------------------------------------------------------------------------
# 29 (new). needs_llm False when no status field present (status dropped)
# ---------------------------------------------------------------------------

def test_no_status_field_on_model() -> None:
    r = normalize("/task Call the broker")
    assert not hasattr(r, "status"), "status field must not exist on Classification"


# ---------------------------------------------------------------------------
# 30 (new). OTEL span emitted with normalize.intent / confidence / needs_llm
# ---------------------------------------------------------------------------

def test_normalize_emits_otel_span() -> None:
    import otel_common

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    normalize("/task Call the broker")

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    span = next((s for s in spans if "normalize" in s.name), None)
    assert span is not None, f"no normalize span in {[s.name for s in spans]}"
    attrs = dict(span.attributes)
    assert attrs.get("normalize.intent") == "task_capture"
    assert isinstance(attrs.get("normalize.confidence"), float)
    assert attrs.get("normalize.needs_llm") is False


# ---------------------------------------------------------------------------
# 31 (new). OTEL span is root (no parent) when called standalone
# ---------------------------------------------------------------------------

def test_normalize_span_is_root_standalone() -> None:
    import otel_common
    from opentelemetry.trace import INVALID_SPAN_ID

    exporter = InMemorySpanExporter()
    otel_common.configure_tracer_provider(exporter)

    normalize("remind me to call the broker")

    spans = exporter.get_finished_spans()
    normalize_span = next((s for s in spans if "normalize" in s.name), None)
    assert normalize_span is not None
    assert normalize_span.parent is None or normalize_span.parent.span_id == INVALID_SPAN_ID
