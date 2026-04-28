"""Shared assertions for NutriOS LLM integration tests.

This module is imported by every LLM test file. Its primary export,
assert_no_llm_arithmetic, enforces the project-wide zero-arithmetic rule
(see CLAUDE.md Core Principle): every numeric value in LLM output must
trace to a Python tool return. The LLM must never compute, sum, distribute,
or narrate arithmetic.

Opt-out: pass check_arithmetic=False to _call_with_tool_loop or
_call_with_tools for tests that intentionally probe arithmetic-leak failure
modes. The default is always enforcement.
"""

from __future__ import annotations
import re

# Matches a full arithmetic expression with result: "N op N = N" or "N op N -> N"
# Operator: -, +, *, /, ÷, ×
# Separator: =, ->, →
# Numbers may include commas as thousands separators.
# Example matches: "12,600 - 1,550 = 11,050" / "11,050 / 6 → 1,841"
# Does NOT match: ISO dates ("2026-05-01"), unit fractions ("1/2 cup"),
# or bare numbers ("2,086 cal"); all lack the N op N = N structure.
_ARITH_RE: re.Pattern[str] = re.compile(
    r'\d[\d,]*'          # left operand
    r'\s*[-+*/÷×]\s*'   # arithmetic operator (ASCII + Unicode)
    r'\d[\d,]*'          # right operand
    r'\s*(?:=|-?>|\u2192)\s*'  # equals (=), arrow (->), or Unicode arrow (→)
    r'\d[\d,]*',
    re.UNICODE,
)


def assert_no_llm_arithmetic(text: str) -> None:
    """Raise AssertionError if text contains an arithmetic expression N op N = N.

    Called automatically by _call_with_tool_loop and _call_with_tools on every
    non-empty final response. Opt-out: pass check_arithmetic=False to those helpers.
    """
    match = _ARITH_RE.search(text)
    assert match is None, (
        f"LLM emitted arithmetic (zero-arithmetic rule violated): "
        f"'{match.group()}' in response. Full text: {text[:400]}"
    )
