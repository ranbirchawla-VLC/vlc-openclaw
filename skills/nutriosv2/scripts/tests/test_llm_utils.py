"""Unit tests for LLM test utility assertions (llm_test_utils.py).

These are Python-level tests, not LLM integration tests. They verify that the
regex patterns in assert_no_llm_arithmetic and assert_no_process_narration
match and exclude the right strings.
"""

from __future__ import annotations
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "llm"))
from llm_test_utils import assert_no_llm_arithmetic, assert_no_process_narration


# ── assert_no_llm_arithmetic: date-range false-positive regression (B-1) ──────

def test_iso_date_range_with_unicode_arrow_does_not_trigger() -> None:
    """ISO date range 'YYYY-MM-DD → YYYY-MM-DD' must not fire arithmetic assertion."""
    assert_no_llm_arithmetic("Your cycle runs 2025-05-05 → 2026-06-01.")


def test_iso_date_range_end_of_text_does_not_trigger() -> None:
    """Date range at end of text without trailing char must not trigger."""
    assert_no_llm_arithmetic("Cycle locked. Runs 2026-04-26 → 2026-07-19.")


def test_real_arithmetic_still_triggers() -> None:
    """Actual arithmetic expression N op N = N must still fire."""
    with pytest.raises(AssertionError, match="zero-arithmetic rule violated"):
        assert_no_llm_arithmetic("The result: 12,600 - 1,550 = 11,050.")


def test_arithmetic_with_arrow_still_triggers() -> None:
    """Arithmetic using Unicode arrow (11,050 / 6 → 1,841) must fire."""
    with pytest.raises(AssertionError, match="zero-arithmetic rule violated"):
        assert_no_llm_arithmetic("Per day: 11,050 / 6 → 1,841 kcal.")


# ── assert_no_process_narration: process-narration pattern coverage (NB-E) ────

@pytest.mark.parametrize("phrase", [
    "I'll now run the script",
    "I'll run the computation",
    "I will run the numbers",
    "I will now run that",
    "I am going to compute the table",
    "Let me compute that for you",
    "Let me calculate the macros",
    "Let me run the tool",
    "Computing that for you now",
])
def test_process_narration_patterns_fire(phrase: str) -> None:
    """Each process-narration phrase must trigger the assertion."""
    with pytest.raises(AssertionError, match="process narration"):
        assert_no_process_narration(phrase)


@pytest.mark.parametrize("clean_text", [
    "Sunday: 2,086 cal; 175g protein, 65g fat, 200g carbs.",
    "Your cycle ends July 5.",
    "Sunday is dose day. Monday is the day after.",
    "Got it, 1,850 calorie weekly deficit. Yes?",
    "No active cycle yet. Want to set one up?",
])
def test_clean_responses_do_not_trigger_narration(clean_text: str) -> None:
    """Valid responses without narration must pass without error."""
    assert_no_process_narration(clean_text)


# ── assert_no_process_narration: offset-language pattern coverage ─────────────

@pytest.mark.parametrize("phrase", [
    "offset 0 = Sunday",
    "offset 1 = Monday",
    "offset 6 = Saturday",
    "weekday 6",
])
def test_offset_language_patterns_fire(phrase: str) -> None:
    """Offset-language phrases must trigger the offset-language pattern."""
    with pytest.raises(AssertionError, match="offset language"):
        assert_no_process_narration(phrase)
