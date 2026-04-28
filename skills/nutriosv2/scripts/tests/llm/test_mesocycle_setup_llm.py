"""LLM integration tests — mesocycle setup capability.

These tests call the real Claude API with the actual capability prompt loaded.
They verify tool call args and response text, not Python logic.

Run via: make test-llm
"""

from __future__ import annotations
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # for llm_test_utils
from compute_candidate_macros import _Input as MacrosInput, compute as py_compute
from recompute_macros_with_overrides import _Input as RecomputeInput, recompute as py_recompute
from llm_test_utils import assert_no_llm_arithmetic

# Python reference for deficit=1850, tdee=2350, protein=175, fat=65
# calories = round(2350 - 1850/7) = round(2085.71) = 2086
# carbs = (2086 - 175*4 - 65*9) // 4 = (2086 - 700 - 585) // 4 = 801 // 4 = 200
_EXPECTED_CALORIES = 2086
_EXPECTED_CARBS_G = 200

# Adjustment fixture: TDEE 2300, deficit 3500, Sunday dose, protein 175, fat 65
# weekly_intake = 2300*7 - 3500 = 12600; override Monday=1550
# remaining = 12600-1550 = 11050; floor: 11050//6 = 1841
_ADJ_WEEKLY_TARGET = 12600
_ADJ_MONDAY_OVERRIDE = 1550
_ADJ_OTHER_DAYS = 1841

# Intent-change fixture: initial deficit 4000 -> changed to 3500, Monday override 1600
# Old baseline (must NOT appear): 2300*7 - 4000 = 12100
# New baseline: 2300*7 - 3500 = 12600
# Monday override = 1600; remaining = 12600-1600 = 11000 for 6 days
# per_day = 11000 // 6 = 1833 (floor division)
_IC_OLD_BASELINE = 12100
_IC_NEW_WEEKLY = 12600
_IC_NEW_DEFICIT = 3500
_IC_MONDAY = 1600
_IC_OTHER_DAYS = 1833


def _call_with_tools(
    llm_client, agent_system_prompt, agent_tools, user_message: str,
    check_arithmetic: bool = True
):
    """Single turn; returns (tool_uses, text).

    check_arithmetic=False: skip zero-arithmetic assertion (only for tests
    intentionally probing arithmetic-leak failure modes).
    """
    resp = llm_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=agent_system_prompt,
        tools=agent_tools,
        messages=[{"role": "user", "content": user_message}],
    )
    tool_uses = [b for b in resp.content if b.type == "tool_use"]
    text = " ".join(b.text for b in resp.content if b.type == "text")
    if check_arithmetic and text:
        assert_no_llm_arithmetic(text)
    return tool_uses, text, resp.content


def _call_with_tool_loop(
    llm_client, agent_system_prompt, agent_tools, user_message: str,
    max_tokens: int = 1024, max_turns: int = 4, check_arithmetic: bool = True
):
    """Multi-turn: send user message, execute tool calls via Python, return final text.

    Returns (first_tool_uses, final_text) where first_tool_uses is from the
    first assistant turn (for arg assertions) and final_text is the last text response.

    check_arithmetic=False: skip zero-arithmetic assertion (only for tests
    intentionally probing arithmetic-leak failure modes).
    """
    messages = [{"role": "user", "content": user_message}]
    first_tool_uses = None
    final_text = ""

    for _ in range(max_turns):
        resp = llm_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=agent_system_prompt,
            tools=agent_tools,
            messages=messages,
        )
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        text = " ".join(b.text for b in resp.content if b.type == "text")
        if text:
            final_text = text

        if first_tool_uses is None and tool_uses:
            first_tool_uses = tool_uses

        if resp.stop_reason == "end_turn" or not tool_uses:
            break

        # Append assistant turn
        messages.append({"role": "assistant", "content": resp.content})

        # Execute tool calls and append results
        tool_results = []
        for tu in tool_uses:
            if tu.name == "compute_candidate_macros":
                inp = MacrosInput(**tu.input)
                result = py_compute(inp)
            elif tu.name == "recompute_macros_with_overrides":
                inp = RecomputeInput(**tu.input)
                int_overrides = {int(k): v for k, v in inp.overrides.items()}
                try:
                    rows = py_recompute(
                        estimated_tdee_kcal=inp.estimated_tdee_kcal,
                        target_deficit_kcal=inp.target_deficit_kcal,
                        protein_floor_g=inp.protein_floor_g,
                        fat_ceiling_g=inp.fat_ceiling_g,
                        overrides=int_overrides,
                    )
                    result = {
                        "weekly_kcal_target": inp.estimated_tdee_kcal * 7 - inp.target_deficit_kcal,
                        "rows": [r.model_dump() for r in rows],
                    }
                except ValueError as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"tool {tu.name} not available in test harness"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    if check_arithmetic and final_text:
        assert_no_llm_arithmetic(final_text)
    return first_tool_uses or [], final_text


@pytest.mark.llm
def test_maintenance_name_deficit_1850_passes_through(llm_client, agent_system_prompt, agent_tools):
    """Cycle name 'maintenance' must not override an explicit deficit of 1850."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "Compute dose-day macros."
    )
    tool_uses, _, _ = _call_with_tools(llm_client, agent_system_prompt, agent_tools, msg)
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    args = compute_calls[0].input
    assert args.get("target_deficit_kcal") == 1850, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')} — "
        "expected 1850; fabrication bug: LLM must not override user-supplied value"
    )


@pytest.mark.llm
def test_explicit_deficit_zero_passes_through(llm_client, agent_system_prompt, agent_tools):
    """Explicit deficit=0 (true maintenance) must reach the tool as 0, not null."""
    msg = (
        "Set up a cycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 0 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "Compute dose-day macros."
    )
    tool_uses, _, _ = _call_with_tools(llm_client, agent_system_prompt, agent_tools, msg)
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    args = compute_calls[0].input
    assert args.get("target_deficit_kcal") == 0, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')} — expected 0"
    )


@pytest.mark.llm
def test_omitted_deficit_prompts_question(llm_client, agent_system_prompt, agent_tools):
    """When deficit is not supplied, LLM must ask — not substitute a value."""
    msg = (
        "I want to start a new mesocycle. Name it 'maintenance'. "
        "4 weeks. Sunday dose. TDEE 2350 kcal/day. Protein floor 175g. Fat ceiling 65g."
    )
    tool_uses, text, _ = _call_with_tools(llm_client, agent_system_prompt, agent_tools, msg)
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]

    # If LLM called compute, deficit must be null (not fabricated)
    for call in compute_calls:
        assert call.input.get("target_deficit_kcal") is None, (
            f"LLM fabricated target_deficit_kcal={call.input.get('target_deficit_kcal')} "
            "when user did not supply a deficit"
        )

    # If no tool call was made, LLM must ask about deficit in its text response
    if not compute_calls:
        text_lower = text.lower()
        assert any(w in text_lower for w in ("deficit", "how much", "target", "lose", "weekly")), (
            f"Expected LLM to ask about deficit, got: {text[:200]}"
        )


@pytest.mark.llm
def test_all_values_readback_matches_python_output(llm_client, agent_system_prompt, agent_tools):
    """Full tool loop: response must read back calories ±1 of Python output; no script narration."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute dose-day macros and tell me the targets."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg
    )
    compute_calls = [t for t in first_tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    assert first_tool_uses[0].input.get("target_deficit_kcal") == 1850

    assert final_text, "Expected a final text response after tool execution"

    # Calories within ±1 of Python reference — strip commas to handle "2,086" formatting
    stripped = final_text.replace(",", "")
    cal_matches = [int(m) for m in re.findall(r"\b(\d{4})\b", stripped)]
    assert any(abs(c - _EXPECTED_CALORIES) <= 1 for c in cal_matches), (
        f"Response calories not within ±1 of {_EXPECTED_CALORIES}. "
        f"4-digit numbers found: {cal_matches}. Full text: {final_text[:300]}"
    )

    # Must not describe the script, JSON, or algorithm
    forbidden = ["script", "algorithm", "compute_candidate", "the tool", "python"]
    text_lower = final_text.lower()
    for word in forbidden:
        assert word not in text_lower, (
            f"Response exposes implementation detail '{word}': {final_text[:300]}"
        )

    # Must not contain fabrication narration
    assert "deficit = 0" not in text_lower
    assert "deficit=0" not in text_lower


@pytest.mark.llm
def test_carbs_appears_in_readback(llm_client, agent_system_prompt, agent_tools):
    """carbs_g must appear in read-back; LLM must not silently drop the fourth macro."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute dose-day macros and tell me the targets."
    )
    _, final_text = _call_with_tool_loop(llm_client, agent_system_prompt, agent_tools, msg)
    assert final_text, "Expected a final text response after tool execution"

    stripped = final_text.replace(",", "")
    # Use non-digit boundary to avoid matching 200 inside 1200, 2200, etc.
    assert re.search(r"(?<!\d)" + str(_EXPECTED_CARBS_G) + r"(?!\d)", stripped), (
        f"carbs_g={_EXPECTED_CARBS_G} not found in response. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_weekday_names_in_readback_no_numeric_labels(llm_client, agent_system_prompt, agent_tools):
    """Rows must be labeled by weekday name; no +N or 'day N' numeric offset labels."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute all 7 rows and show me the full weekly macro table."
    )
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg, max_tokens=2048
    )
    assert final_text, "Expected a final text response after tool execution"

    text_lower = final_text.lower()

    weekday_names = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    found_names = [name for name in weekday_names if name in text_lower]
    # Threshold of 3: max_turns=4 may not complete all 7 tool calls before end_turn;
    # 3 distinct weekday names in the response is a reliable signal that labeling is active.
    # Raise this only alongside a max_turns increase.
    assert len(found_names) >= 3, (
        f"Expected at least 3 weekday names in table, found: {found_names}. "
        f"Full text: {final_text[:500]}"
    )

    assert not re.search(r'\+[0-6]', final_text), (
        f"Numeric offset label (+N) found in response. Full text: {final_text[:400]}"
    )
    assert not re.search(r'\bday [0-6]\b', text_lower), (
        f"'day N' label found in response. Full text: {final_text[:400]}"
    )
    assert not re.search(r'\b(?:row|offset)\s+[0-6]\b', text_lower), (
        f"'row N' or 'offset N' label found in response. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_adjustment_flow_calls_recompute_and_reads_back_correctly(
    llm_client, agent_system_prompt, agent_tools
):
    """Adjustment flow: LLM calls recompute tool; reads back 1550/1841 not inline arithmetic."""
    msg = (
        "We're negotiating a mesocycle. "
        "TDEE 2300 kcal/day, weekly deficit 3500 kcal, Sunday dose day, "
        "protein floor 175g, fat ceiling 65g. "
        "The baseline table shows 1800 cal/day across all 7 days. "
        "The user now says: Monday should be 1,550 kcal; raise the other days to compensate."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg, max_tokens=2048
    )

    # Must have called recompute
    recompute_calls = [t for t in first_tool_uses if t.name == "recompute_macros_with_overrides"]
    assert recompute_calls, (
        f"Expected recompute_macros_with_overrides to be called. "
        f"Tools called: {[t.name for t in first_tool_uses]}"
    )

    # Some override must contain calories=1550 (the user's value passed through verbatim)
    # Exact offset key accuracy is a Python-layer concern tested in test_recompute_macros.py
    args = recompute_calls[0].input
    overrides = args.get("overrides", {})
    override_calories = [v.get("calories") for v in overrides.values()]
    assert _ADJ_MONDAY_OVERRIDE in override_calories, (
        f"Expected {_ADJ_MONDAY_OVERRIDE} in override calories, got overrides={overrides}"
    )
    # Verbatim pass-through: TDEE and deficit must reach the tool unchanged
    assert args.get("estimated_tdee_kcal") == 2300, (
        f"LLM sent estimated_tdee_kcal={args.get('estimated_tdee_kcal')} — expected 2300"
    )
    assert args.get("target_deficit_kcal") == 3500, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')} — expected 3500"
    )

    assert final_text, "Expected a final text response after tool execution"
    stripped = final_text.replace(",", "")

    # Monday value must appear
    assert re.search(r"(?<!\d)1550(?!\d)", stripped), (
        f"Monday value 1550 not found in response. Full text: {final_text[:400]}"
    )
    # Other-days value must appear
    assert re.search(r"(?<!\d)" + str(_ADJ_OTHER_DAYS) + r"(?!\d)", stripped), (
        f"Other-days value {_ADJ_OTHER_DAYS} not found in response. Full text: {final_text[:400]}"
    )
    # Weekly target from tool must appear; not the fabricated wrong value
    assert re.search(r"(?<!\d)" + str(_ADJ_WEEKLY_TARGET).replace(",", "") + r"(?!\d)", stripped), (
        f"Weekly target {_ADJ_WEEKLY_TARGET} not found in response. Full text: {final_text[:400]}"
    )
    # Wrong weekly baseline (12100) must NOT appear
    assert "12100" not in stripped and "12,100" not in final_text, (
        f"Wrong weekly baseline 12,100 found in response. Full text: {final_text[:400]}"
    )
    # Wrong deficit (3502 or 4002) must NOT appear
    text_lower = final_text.lower()
    assert "3502" not in text_lower and "3,502" not in final_text, (
        f"Wrong deficit 3,502 found in response. Full text: {final_text[:400]}"
    )
    assert "4002" not in text_lower and "4,002" not in final_text, (
        f"Wrong deficit 4,002 found in response. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_adjustment_flow_surfaces_constraint_error_on_infeasible_override(
    llm_client, agent_system_prompt, agent_tools
):
    """Negative: override that exhausts budget must surface as a constraint question, not silently ignored."""
    msg = (
        "We're negotiating a mesocycle. "
        "TDEE 2300 kcal/day, weekly deficit 3500 kcal, Sunday dose day, "
        "protein floor 175g, fat ceiling 65g. "
        "The user says: Monday should be 9,000 kcal; raise the other days."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg, max_tokens=1024
    )

    assert final_text, "Expected a text response"

    # LLM must surface the constraint, not pretend the adjustment worked
    text_lower = final_text.lower()
    constraint_words = [
        "can't", "cannot", "constraint", "exceed", "budget", "floor",
        "won't work", "not possible", "too high", "leaves", "reduce"
    ]
    assert any(w in text_lower for w in constraint_words), (
        f"Expected LLM to surface a constraint. Got: {final_text[:400]}"
    )



@pytest.mark.llm
def test_intent_change_deficit_triggers_recompute(llm_client, agent_system_prompt, agent_tools):
    """Bug A: changing deficit mid-conversation must recompute baseline, not reuse old one."""
    msg = (
        "We're setting up a mesocycle. TDEE 2300 kcal/day, Sunday dose, "
        "protein floor 175g, fat ceiling 65g. "
        "I originally wanted a 4,000 kcal/week deficit. "
        "Now I want to change it to 3,500/week instead. "
        "Also set Monday to 1,600 kcal and redistribute the other days. "
        "Show me the updated table."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        max_tokens=2048, max_turns=6,
    )

    assert final_text, "Expected a final text response"
    stripped = final_text.replace(",", "")

    # Monday value must appear
    assert re.search(r"(?<!\d)" + str(_IC_MONDAY) + r"(?!\d)", stripped), (
        f"Monday value {_IC_MONDAY} not found. Full text: {final_text[:400]}"
    )
    # Other-days value must appear.
    # 1833 = (12600-1600)//6 only when weekly_intake=12600 (deficit=3500).
    # If the LLM reused the old baseline (12100), it would produce a different value
    # (e.g. (12100-1600)//6=1750); this assertion fails on that path.
    assert re.search(r"(?<!\d)" + str(_IC_OTHER_DAYS) + r"(?!\d)", stripped), (
        f"Other-days value {_IC_OTHER_DAYS} not found. Full text: {final_text[:400]}"
    )
    # New weekly target must appear
    assert re.search(r"(?<!\d)" + str(_IC_NEW_WEEKLY) + r"(?!\d)", stripped), (
        f"New weekly target {_IC_NEW_WEEKLY} not found. Full text: {final_text[:400]}"
    )
    # Old wrong baseline must NOT appear (this is the regression check)
    assert str(_IC_OLD_BASELINE) not in stripped, (
        f"Old baseline {_IC_OLD_BASELINE} found; LLM reused stale weekly intake. "
        f"Full text: {final_text[:400]}"
    )
    # Deficit must read back as 3500
    assert re.search(r"(?<!\d)" + str(_IC_NEW_DEFICIT) + r"(?!\d)", stripped), (
        f"New deficit {_IC_NEW_DEFICIT} not found in read-back. Full text: {final_text[:400]}"
    )
    # zero-arithmetic assertion runs automatically via check_arithmetic=True (default)


@pytest.mark.llm
def test_intent_change_deficit_does_not_narrate_arithmetic(
    llm_client, agent_system_prompt, agent_tools
):
    """Bug B: after deficit change, no inline arithmetic narration in response."""
    msg = (
        "Setting up a mesocycle. TDEE 2300, Sunday dose, protein 175g, fat 65g. "
        "Change weekly deficit from 4,000 to 3,500. "
        "Monday target: 1,600 kcal. Show the full redistributed table."
    )
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        max_tokens=2048, max_turns=6,
    )
    assert final_text, "Expected a final text response"
    # assert_no_llm_arithmetic runs automatically; no explicit call needed.
    # This test exists to document Bug B as a named regression scenario.
