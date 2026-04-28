"""LLM integration tests: estimate_macros_from_description.

Calls the real API against the production model + temperature=0.
Run via: make test-nutriosv2-llm or make test-nutriosv2-llm-3x

Production-parity: estimate_macros_from_description creates its own client
internally using the same model pin (_MODEL) and temperature (_TEMPERATURE = 0)
as production. Tests call the function directly; no harness scaffolding needed.
"""

from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from estimate_macros import estimate_macros_from_description


@pytest.mark.llm
def test_banana_returns_plausible_macros(llm_client: object) -> None:
    """'1 large banana' returns macros within plausible nutritional bounds.

    Loose bounds: testing the API call works and returns valid structure,
    not nutrition accuracy. Model and temperature are pinned inside the tool.
    """
    result = estimate_macros_from_description("1 large banana")
    assert 80 <= result["calories"] <= 130, f"calories out of range: {result['calories']}"
    assert result["protein_g"] < 3, f"protein unexpectedly high: {result['protein_g']}"
    assert 20 <= result["carbs_g"] <= 35, f"carbs out of range: {result['carbs_g']}"
    assert result["confidence"] in ("high", "medium"), f"unexpected confidence: {result['confidence']}"
