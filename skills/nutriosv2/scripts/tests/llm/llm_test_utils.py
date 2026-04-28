"""Shared assertions for NutriOS LLM integration tests.

assert_no_llm_arithmetic enforces the project-wide zero-arithmetic rule
(CLAUDE.md Core Principle): every numeric value in LLM output must trace to a
Python tool return. The LLM must never compute, sum, distribute, or narrate
arithmetic.

assert_no_process_narration enforces the "LLM voice rules" section of CLAUDE.md:
the LLM does not narrate its own process. Called from every LLM test fixture
alongside assert_no_llm_arithmetic.

assert_metric_confirmation enforces NB-18: metric inputs require a Yes/No/Change
read-back confirmation before the value lands in any tool call. Call sites land
in the check-in capability build; see NB-29 in KNOWN_ISSUES.md.

Opt-out: pass check_arithmetic=False or check_narration=False to the harness
helpers for tests that intentionally probe failure modes. Default is always
enforcement.
"""

from __future__ import annotations
import re

# ── model pin ─────────────────────────────────────────────────────────────────
# Must match the production agent model in skills/nutriosv2/openclaw.json and
# in the root ~/.openclaw/openclaw.json agents.list entry for nutriosv2.
# Changing this without updating production config is a contract violation.
LLM_TEST_MODEL: str = "claude-sonnet-4-6"

# temperature=0 for determinism. LLM tests run 3x require-all-pass; any test
# that flakes at temperature=0 is undertested or asserting the wrong thing.
LLM_TEST_TEMPERATURE: int = 0

# ── zero-arithmetic assertion ─────────────────────────────────────────────────

# Matches a full arithmetic expression with result: "N op N = N" or "N op N -> N"
# Operator: -, +, *, /, div, ÷, ×
# Separator: =, ->, or Unicode arrow
# Numbers may include commas as thousands separators.
# Example matches: "12,600 - 1,550 = 11,050" / "11,050 / 6 -> 1,841"
# Does NOT match: ISO dates ("2026-05-01"), unit fractions ("1/2 cup"),
# or bare numbers ("2,086 cal"); all lack the N op N = N structure.
_ARITH_RE: re.Pattern[str] = re.compile(
    r'\d[\d,]*'          # left operand
    r'\s*[-+*/÷×]\s*'   # arithmetic operator (ASCII + Unicode)
    r'\d[\d,]*'          # right operand
    r'\s*(?:=|-?>|→)\s*'  # equals (=), arrow (->), or Unicode arrow
    r'\d[\d,]*',
    re.UNICODE,
)

# Exclude: → followed by a 4-digit year then - / identifies ISO date ranges.
# Applied to text[m.start():m.end()+10] so the trailing YYYY- after the match
# boundary is visible. Arithmetic "N / N → N" has no trailing YYYY-.
_DATE_RANGE_ARROW_FP: re.Pattern[str] = re.compile(r'→\s*\d{4}[-/]', re.UNICODE)


def assert_no_llm_arithmetic(text: str) -> None:
    """Raise AssertionError if text contains an arithmetic expression N op N = N.

    Called automatically by harness helpers on every non-empty assistant response.
    Opt-out: pass check_arithmetic=False to those helpers.
    """
    for match in _ARITH_RE.finditer(text):
        context = text[match.start():match.end() + 10]
        if _DATE_RANGE_ARROW_FP.search(context):
            continue  # skip: date-range arrow, not arithmetic separator
        raise AssertionError(
            f"LLM emitted arithmetic (zero-arithmetic rule violated): "
            f"'{match.group()}' in response. Full text: {text[:400]}"
        )


# ── process-narration assertion ───────────────────────────────────────────────
#
# Each entry: (pattern_name, compiled_regex)
# Extends in lock-step with the forbidden-patterns table in CLAUDE.md
# "LLM voice rules" section. Add a new tuple when a cousin surfaces in
# production; add a regression test in the LLM-test suite at the same time.

_NARRATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "date-arithmetic prose",
        re.compile(
            r'today\s+plus\s+\d+|plus\s+\d+\s+weeks?\s+(?:is|from\s+today)',
            re.IGNORECASE,
        ),
    ),
    (
        "script description",
        re.compile(
            r'\bthe\s+script\b|\bjson\s+string\b|one\s+call\s+covers\s+all\s+rows?'
            r'|\bthe\s+algorithm\b|\bsingle\s+json\b',
            re.IGNORECASE,
        ),
    ),
    (
        "offset language",
        re.compile(
            r'\boffset\s*[0-6]\s*=|\bweekday\s+[0-6]\b',
            re.IGNORECASE,
        ),
    ),
    (
        "intermediate baseline value",
        re.compile(
            r'\bbaseline\s+row\s+is\b|\bbaseline\s*:\s*[\d,]+\s*cal',
            re.IGNORECASE,
        ),
    ),
    (
        "process narration",
        re.compile(
            r"\blet\s+me\s+(?:compute|calculate|run)\b"
            r"|(?:\bi(?:'?ll|[\s]+will)\s+(?:now\s+)?run\b)"
            r"|\bi\s+am\s+going\s+to\b"
            r"|\bcomputing\s+that\b",
            re.IGNORECASE,
        ),
    ),
]


def assert_no_process_narration(text: str) -> None:
    """Raise AssertionError if text matches any LLM process-narration pattern.

    Called automatically by harness helpers alongside assert_no_llm_arithmetic.
    Opt-out: pass check_narration=False to those helpers.
    """
    for name, pattern in _NARRATION_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            raise AssertionError(
                f"LLM process narration detected (pattern: {name!r}): "
                f"'{match.group()}' in response. Full text: {text[:400]}"
            )


# ── NB-18 metric-confirmation assertion ───────────────────────────────────────

_CONFIRMATION_WORDS: frozenset[str] = frozenset({
    "yes?", "correct?", "right?", "confirm", "got it", "yes,", "yes.",
})


def assert_metric_confirmation(
    first_text: str,
    first_tool_uses: list,
    metric_value: int,
) -> None:
    """Assert the LLM confirmed a metric value before calling any tool (NB-18).

    The first LLM response after a metric input must be a confirmation turn
    (readable text containing the value); tool calls come only after the
    user confirms. Fires on metric inputs listed in CLAUDE.md NB-18:
    weekly deficit, weight, TDEE, protein floor, fat ceiling, target calories.

    first_tool_uses: tool_use blocks from the FIRST assistant response.
    metric_value: the integer value the user supplied.
    """
    assert not first_tool_uses, (
        f"LLM called {first_tool_uses[0].name!r} without confirming "
        f"metric value {metric_value} first. "
        "NB-18: metric inputs require a Yes/No/Change confirmation turn before "
        "the value lands in any tool call."
    )
    if first_text:
        stripped = first_text.replace(",", "")
        assert str(metric_value) in stripped, (
            f"LLM did not read back metric value {metric_value} in confirmation. "
            f"Got: {first_text[:200]}"
        )
        text_lower = first_text.lower()
        assert any(w in text_lower for w in _CONFIRMATION_WORDS), (
            f"No confirmation language found in text for metric value {metric_value}. "
            f"Got: {first_text[:200]}"
        )
