"""Tests for scripts/inner_skills/batch_estimate.py.

All tests mock the Anthropic client. No real API calls.
"""

from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inner_skills.batch_estimate import (
    BaseMacroEstimate,
    BatchEstimateResult,
    _PROMPT,
    estimate_macros,
)


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


_EGG = {"calories": 72, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}
_BREAD = {"calories": 80, "protein_g": 4.0, "fat_g": 1.0, "carbs_g": 14.0}
_AVOCADO = {"calories": 234, "protein_g": 2.9, "fat_g": 21.0, "carbs_g": 12.0}


# ---------------------------------------------------------------------------
# Structural: empty input
# ---------------------------------------------------------------------------


def test_empty_descriptions_returns_empty_no_llm_call() -> None:
    """Empty descriptions list returns empty BatchEstimateResult; LLM never called."""
    client = _make_mock_client([])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros([])

    assert result.items == []
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 0


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_single_item_happy_path() -> None:
    """Single item; mock returns valid one-element array; structure and values flow through."""
    client = _make_mock_client([json.dumps([_EGG])])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["two eggs"])

    assert len(result.items) == 1
    item = result.items[0]
    assert isinstance(item, BaseMacroEstimate)
    assert item.calories == round(_EGG["calories"])
    assert item.protein_g == round(_EGG["protein_g"])
    assert item.fat_g == round(_EGG["fat_g"])
    assert item.carbs_g == round(_EGG["carbs_g"])
    assert item.notes is None
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 1


def test_multi_item_happy_path_order_preserved() -> None:
    """3-item input; mock returns 3-element array; input order is preserved in output."""
    response = json.dumps([_EGG, _BREAD, _AVOCADO])
    client = _make_mock_client([response])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["two eggs", "slice of whole wheat bread", "half an avocado"])

    assert len(result.items) == 3
    assert result.items[0].calories == round(_EGG["calories"])
    assert result.items[1].calories == round(_BREAD["calories"])
    assert result.items[2].calories == round(_AVOCADO["calories"])
    assert result.retry_occurred is False
    assert client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Prompt structure: quantifier-ignore contract
# ---------------------------------------------------------------------------


def test_prompt_contains_quantifier_ignore_rule() -> None:
    """Prompt instructs LLM to ignore quantifiers; critical rule text present verbatim."""
    assert "ignore quantifiers in the description" in _PROMPT


# ---------------------------------------------------------------------------
# Schema validation: length mismatch
# ---------------------------------------------------------------------------


def test_schema_length_mismatch_triggers_retry_then_succeeds() -> None:
    """Array with wrong length on first call triggers retry; correct second call succeeds."""
    wrong = json.dumps([_EGG, _BREAD])  # 2 items for a 1-item input
    correct = json.dumps([_EGG])
    client = _make_mock_client([wrong, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["two eggs"])

    assert len(result.items) == 1
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Schema validation: missing required key
# ---------------------------------------------------------------------------


def test_schema_missing_required_key_triggers_retry_then_succeeds() -> None:
    """Element missing 'carbs_g' triggers retry; correct second call succeeds."""
    missing_key = json.dumps([{"calories": 72, "protein_g": 6.3, "fat_g": 4.8}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([missing_key, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Schema validation: extra keys
# ---------------------------------------------------------------------------


def test_schema_extra_key_triggers_retry_then_succeeds() -> None:
    """Element with extra key 'notes' triggers retry; correct second call succeeds."""
    extra_key = json.dumps([{**_EGG, "notes": "typical large egg"}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([extra_key, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Schema validation: negative value
# ---------------------------------------------------------------------------


def test_schema_negative_value_triggers_retry_then_succeeds() -> None:
    """Element with negative calories triggers retry; correct second call succeeds."""
    negative = json.dumps([{"calories": -5, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([negative, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Schema validation: non-numeric value
# ---------------------------------------------------------------------------


def test_schema_nonnumeric_value_triggers_retry_then_succeeds() -> None:
    """Element with string calories (e.g., '72') triggers retry; correct second call succeeds."""
    nonnumeric = json.dumps([{"calories": "72", "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([nonnumeric, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Retry on bad JSON
# ---------------------------------------------------------------------------


def test_retry_on_bad_json_succeeds_second_attempt() -> None:
    """Malformed JSON on first call; valid response on second; retry_occurred=True."""
    client = _make_mock_client(["not valid json {{{", json.dumps([_EGG])])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert len(result.items) == 1
    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


def test_retry_on_bad_json_both_fail_raises() -> None:
    """Malformed JSON on both attempts raises ValueError per spec §6.2."""
    client = _make_mock_client(["not json", "also not json"])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        with pytest.raises(ValueError, match="schema validation failed after retry"):
            estimate_macros(["egg"])

    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Retry on schema-fail (not bad JSON)
# ---------------------------------------------------------------------------


def test_retry_on_schema_fail_succeeds_second_attempt() -> None:
    """Valid JSON but failing schema on first call; correct second call succeeds; retry_occurred=True."""
    schema_fail = json.dumps([{"calories": -1, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([schema_fail, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Float values rounded to int
# ---------------------------------------------------------------------------


def test_schema_non_dict_element_triggers_retry_then_succeeds() -> None:
    """Non-dict element (integer) in array triggers retry; correct second call succeeds."""
    non_dict = json.dumps([42])  # integer element, not a dict
    correct = json.dumps([_EGG])
    client = _make_mock_client([non_dict, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


def test_schema_bool_value_triggers_retry_then_succeeds() -> None:
    """Bool value (True) is not valid numeric; triggers retry; correct second call succeeds."""
    bool_val = json.dumps([{"calories": True, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}])
    correct = json.dumps([_EGG])
    client = _make_mock_client([bool_val, correct])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    assert result.retry_occurred is True
    assert client.messages.create.call_count == 2


def test_float_macro_values_rounded_to_int() -> None:
    """LLM may return floats; _validate rounds them to int per BaseMacroEstimate contract."""
    floats = json.dumps([{"calories": 72.6, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}])
    client = _make_mock_client([floats])
    with patch("inner_skills.batch_estimate.anthropic.Anthropic", return_value=client), \
         patch("inner_skills.batch_estimate._load_api_key", return_value="test-key"):
        result = estimate_macros(["egg"])

    item = result.items[0]
    assert item.calories == 73
    assert item.protein_g == 6
    assert item.fat_g == 5
    assert item.carbs_g == 0
    assert result.retry_occurred is False
