"""Tests for scripts/estimate_macros.py."""

from __future__ import annotations
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from estimate_macros import estimate_macros_from_description


_VALID_BANANA = json.dumps({
    "calories": 105,
    "protein_g": 1.3,
    "fat_g": 0.4,
    "carbs_g": 27.0,
    "confidence": "high",
})

_MALFORMED = "not json at all"


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Return a mock Anthropic client that yields each response in sequence."""
    responses_iter = iter(responses)

    def _create(**kwargs):
        text = next(responses_iter)
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    client = MagicMock()
    client.messages.create.side_effect = _create
    return client


def test_valid_response_parsed_correctly() -> None:
    """Valid JSON response → EstimateResult fields parsed and returned as dict."""
    with patch("estimate_macros.anthropic.Anthropic") as mock_cls, \
         patch("estimate_macros._load_api_key", return_value="test-key"):
        mock_cls.return_value = _make_mock_client([_VALID_BANANA])
        result = estimate_macros_from_description("1 large banana")

    assert result["calories"] == 105
    assert result["protein_g"] == pytest.approx(1.3)
    assert result["fat_g"] == pytest.approx(0.4)
    assert result["carbs_g"] == pytest.approx(27.0)
    assert result["confidence"] == "high"


def test_retry_on_malformed_first_response() -> None:
    """Malformed JSON on first call → valid response on retry → result returned."""
    with patch("estimate_macros.anthropic.Anthropic") as mock_cls, \
         patch("estimate_macros._load_api_key", return_value="test-key"):
        mock_cls.return_value = _make_mock_client([_MALFORMED, _VALID_BANANA])
        result = estimate_macros_from_description("1 large banana")

    assert result["calories"] == 105
    assert result["confidence"] == "high"
    assert mock_cls.return_value.messages.create.call_count == 2


def test_raises_after_two_failures() -> None:
    """Malformed JSON on both attempts → ValueError with diagnostic message."""
    with patch("estimate_macros.anthropic.Anthropic") as mock_cls, \
         patch("estimate_macros._load_api_key", return_value="test-key"):
        mock_cls.return_value = _make_mock_client([_MALFORMED, _MALFORMED])
        with pytest.raises(ValueError, match="schema validation failed after retry"):
            estimate_macros_from_description("1 large banana")
