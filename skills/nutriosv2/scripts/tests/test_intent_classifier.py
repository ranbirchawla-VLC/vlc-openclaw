"""Tests for scripts/intent_classifier.py."""

from __future__ import annotations
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from intent_classifier import classify_intent


# ── mesocycle_setup ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "set up a cycle",
    "new mesocycle",
    "start a plan",
    "new cycle",
    "set up my plan",
    "create a cycle",
    "i want to start",
    "Set Up A Cycle",
    "NEW MESOCYCLE",
])
def test_mesocycle_setup_trigger(phrase: str) -> None:
    intent, ambiguous = classify_intent(phrase)
    assert intent == "mesocycle_setup"
    assert ambiguous is False


# ── cycle_read_back ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "what's my cycle",
    "show my plan",
    "what are my macros",
    "what's my target today",
    "show my mesocycle",
    "what cycle am i on",
    "What's My Cycle",
    "SHOW MY PLAN",
])
def test_cycle_read_back_trigger(phrase: str) -> None:
    intent, ambiguous = classify_intent(phrase)
    assert intent == "cycle_read_back"
    assert ambiguous is False


# ── meal_log ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "log a meal",
    "i ate chicken and rice",
    "i had a protein shake",
    "just ate lunch",
    "food log",
    "log food",
    "log breakfast",
    "log lunch",
    "log dinner",
    "Log A Meal",
    "I ATE",
])
def test_meal_log_trigger(phrase: str) -> None:
    intent, ambiguous = classify_intent(phrase)
    assert intent == "meal_log"
    assert ambiguous is False


# ── ambiguous (default) ──────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "sounds good",
    "yes",
    "ok",
    "1850",
    "what does TDEE mean?",
    "anything else?",
    "",
    "hello",
])
def test_ambiguous_no_trigger_match(phrase: str) -> None:
    intent, ambiguous = classify_intent(phrase)
    assert intent == "default"
    assert ambiguous is True


# ── trigger embedded in longer message ───────────────────────────────────────

def test_mesocycle_setup_trigger_embedded() -> None:
    intent, ambiguous = classify_intent(
        "Hey NutriOS, I want to set up a new cycle for this month"
    )
    assert intent == "mesocycle_setup"
    assert ambiguous is False


def test_cycle_read_back_trigger_embedded() -> None:
    intent, ambiguous = classify_intent("Can you show my plan again please?")
    assert intent == "cycle_read_back"
    assert ambiguous is False


# ── return type ──────────────────────────────────────────────────────────────

def test_return_type_is_tuple_of_str_bool() -> None:
    result = classify_intent("anything")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], bool)
