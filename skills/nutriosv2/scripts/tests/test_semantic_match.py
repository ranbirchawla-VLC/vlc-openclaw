"""Tests for scripts/inner_skills/semantic_match.py.

All tests mock the Anthropic client. No real API calls.
"""

from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inner_skills.semantic_match import SemanticMatchResult, match_recipes


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Return a mock Anthropic client that yields responses in sequence."""
    responses_iter = iter(responses)

    def _create(**kwargs):
        text = next(responses_iter)
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    client = MagicMock()
    client.messages.create.side_effect = _create
    return client


def _patch(client: MagicMock):
    return (
        patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client),
        patch("inner_skills.semantic_match._load_api_key", return_value="test-key"),
    )


# ---------------------------------------------------------------------------
# Structural: empty input
# ---------------------------------------------------------------------------


def test_empty_items_returns_empty_no_llm_call() -> None:
    """Empty unmatched_items list returns empty matches; LLM never called."""
    client = _make_mock_client([])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes([], ["Recovery Shake", "Chicken Tikka Lunch Bowl"])

    assert result.matches == []
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 0


def test_empty_recipe_names_returns_all_nulls_no_llm_call() -> None:
    """Empty recipe_names returns [None]*len(unmatched_items); LLM never called."""
    client = _make_mock_client([])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(["tikka lunch", "Thai noodles"], [])

    assert result.matches == [None, None]
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 0


# ---------------------------------------------------------------------------
# MATCH examples from build prompt
# ---------------------------------------------------------------------------


def test_match_tikka_short_form() -> None:
    """'my tikka lunch' matches 'Chicken Tikka Lunch Bowl' (shorter form)."""
    client = _make_mock_client([json.dumps(["Chicken Tikka Lunch Bowl"])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my tikka lunch"],
            recipe_names=["Chicken Tikka Lunch Bowl"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl"]
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 1


def test_match_tikka_masala_variation() -> None:
    """'tikka masala lunch' matches 'Chicken Tikka Lunch Bowl' (slight variation, only tikka)."""
    client = _make_mock_client([json.dumps(["Chicken Tikka Lunch Bowl"])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["tikka masala lunch"],
            recipe_names=["Chicken Tikka Lunch Bowl"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl"]
    assert result.retry_occurred is False


def test_match_tikka_with_unrelated_recipe() -> None:
    """'tikka lunch' matches 'Chicken Tikka Lunch Bowl'; 'Recovery Shake' unrelated."""
    response = json.dumps(["Chicken Tikka Lunch Bowl"])
    client = _make_mock_client([response])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["tikka lunch"],
            recipe_names=["Chicken Tikka Lunch Bowl", "Recovery Shake"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl"]
    assert result.retry_occurred is False


def test_match_single_item_single_recipe_clean() -> None:
    """Single item, single recipe, verbatim match; call_count == 1."""
    client = _make_mock_client([json.dumps(["Recovery Shake"])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my recovery shake"],
            recipe_names=["Recovery Shake"],
        )

    assert result.matches == ["Recovery Shake"]
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# DO NOT MATCH examples from build prompt
# ---------------------------------------------------------------------------


def test_no_match_wrong_food() -> None:
    """'tikka lunch' against only 'Recovery Shake' recipe returns null."""
    client = _make_mock_client([json.dumps([None])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["tikka lunch"],
            recipe_names=["Recovery Shake"],
        )

    assert result.matches == [None]
    assert result.retry_occurred is False


def test_no_match_different_restaurant() -> None:
    """'Chipotle chicken bowl' against 'Qdoba Chicken Bowl' returns null (different restaurants)."""
    client = _make_mock_client([json.dumps([None])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["Chipotle chicken bowl"],
            recipe_names=["Qdoba Chicken Bowl"],
        )

    assert result.matches == [None]
    assert result.retry_occurred is False


def test_no_match_category_not_recipe() -> None:
    """'Thai noodles' against 'Pad Thai' returns null (category, not recipe reference)."""
    client = _make_mock_client([json.dumps([None])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["Thai noodles"],
            recipe_names=["Pad Thai"],
        )

    assert result.matches == [None]
    assert result.retry_occurred is False


def test_no_match_ambiguous_multiple_recipes() -> None:
    """'my shake' against two shake recipes returns null (ambiguous; user owns disambiguation)."""
    client = _make_mock_client([json.dumps([None])])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my shake"],
            recipe_names=["Morning Protein Shake", "Recovery Shake"],
        )

    assert result.matches == [None]
    assert result.retry_occurred is False


# ---------------------------------------------------------------------------
# Schema validation: length mismatch triggers retry
# ---------------------------------------------------------------------------


def test_schema_length_mismatch_triggers_retry_then_succeeds() -> None:
    """Array with wrong length on first call triggers retry; correct second call succeeds."""
    wrong_length = json.dumps(["Chicken Tikka Lunch Bowl", "extra element"])
    correct = json.dumps(["Chicken Tikka Lunch Bowl"])
    client = _make_mock_client([wrong_length, correct])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["tikka lunch"],
            recipe_names=["Chicken Tikka Lunch Bowl"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl"]
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Schema validation: non-verbatim element triggers retry
# ---------------------------------------------------------------------------


def test_schema_nonverbatim_name_triggers_retry_then_succeeds() -> None:
    """Element not verbatim in recipe_names on first call triggers retry; correct second call succeeds."""
    nonverbatim = json.dumps(["chicken tikka lunch bowl"])  # wrong casing
    correct = json.dumps(["Chicken Tikka Lunch Bowl"])
    client = _make_mock_client([nonverbatim, correct])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["tikka lunch"],
            recipe_names=["Chicken Tikka Lunch Bowl"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl"]
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Retry on bad JSON
# ---------------------------------------------------------------------------


def test_retry_on_bad_json_succeeds_second_attempt() -> None:
    """Malformed JSON on first call; valid JSON on second call; retry_occurred=True."""
    correct = json.dumps(["Recovery Shake"])
    client = _make_mock_client(["not valid json {{{", correct])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my recovery shake"],
            recipe_names=["Recovery Shake"],
        )

    assert result.matches == ["Recovery Shake"]
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


def test_retry_on_bad_json_both_fail_raises() -> None:
    """Malformed JSON on both attempts raises ValueError per spec §6.1."""
    client = _make_mock_client(["not json", "also not json"])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        with pytest.raises(ValueError, match="schema validation failed after retry"):
            match_recipes(
                unmatched_items=["tikka lunch"],
                recipe_names=["Chicken Tikka Lunch Bowl"],
            )

    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Multi-item: mixed matches and nulls in one call
# ---------------------------------------------------------------------------


def test_schema_integer_element_triggers_retry_then_succeeds() -> None:
    """Integer element (not str or null) fails validation; retry with correct response succeeds."""
    integer_element = json.dumps([42])  # 42 is not a recipe name or null
    correct = json.dumps(["Recovery Shake"])
    client = _make_mock_client([integer_element, correct])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my recovery shake"],
            recipe_names=["Recovery Shake"],
        )

    assert result.matches == ["Recovery Shake"]
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


def test_multi_item_mixed_matches_and_nulls() -> None:
    """Multiple items in one call; some match, some null; input order preserved."""
    response = json.dumps(["Chicken Tikka Lunch Bowl", None, "Recovery Shake"])
    client = _make_mock_client([response])
    with patch("inner_skills.semantic_match.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.semantic_match._load_api_key", return_value="test-key"):
        result = match_recipes(
            unmatched_items=["my tikka lunch", "Thai noodles", "my shake"],
            recipe_names=["Chicken Tikka Lunch Bowl", "Recovery Shake"],
        )

    assert result.matches == ["Chicken Tikka Lunch Bowl", None, "Recovery Shake"]
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 1
