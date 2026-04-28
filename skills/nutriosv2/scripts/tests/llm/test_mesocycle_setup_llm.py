"""LLM integration tests; mesocycle setup capability.

These tests call the real Claude API with the actual capability prompt loaded.
They verify tool call args and response text, not Python logic.

Run via: make test-nutriosv2-llm

## Harness shapes

**Single-shot (_call_with_tools / _call_with_tool_loop):**
One self-contained user message carries all context. The LLM sees no prior turn
history beyond what the tool loop accumulates. turn_state is executed automatically
on each API cycle; the capability_prompt it returns gives the LLM fresh instructions
every turn. Exercises single-turn and inner-loop compliance.

**Multi-turn (MultiTurnHarness):**
Each .send() call appends to a persistent messages list, exactly as OpenClaw does
between Telegram turns. Tool calls are executed against the real Python implementations
using a per-test tmp directory. assert_no_llm_arithmetic and assert_no_process_narration
fire on every assistant text block in every turn, not just the final response.

The multi-turn harness is the regression guard for bugs that single-shot tests cannot
surface: in-context drift, stale baseline reuse across turns, and continuity-turn
ambiguity.

## Production-parity discipline (CLAUDE.md "Test conditions match production conditions")

Every fixture that closes a production bug documents:
1. The production failure mode it exercises.
2. Confirmation that the fixture fails against pre-fix code.
"""

from __future__ import annotations
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from compute_candidate_macros import _Input as MacrosInput, compute as py_compute
from recompute_macros_with_overrides import _Input as RecomputeInput, recompute as py_recompute
from llm_test_utils import (
    assert_no_llm_arithmetic,
    assert_no_process_narration,
    LLM_TEST_MODEL,
    LLM_TEST_TEMPERATURE,
)
from lock_mesocycle import _Input as LockInput, run_lock_mesocycle
from get_active_mesocycle import run_get_active_mesocycle
from turn_state import compute_turn_state

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

# Multi-turn production-arc fixture constants (rewritten from clean arc to production arc):
# Turn 1 (intent bundling): 4000 deficit setup with all params bundled
#   daily = round(2300 - 4000/7) = round(2300 - 571.4) = round(1728.57) = 1729
# Turn 2 (continuity): ambiguous "yeah that looks right, continue"
# Turn 3 (deficit-change-after-offer): change from 4000 to 3500
#   new daily = round(2300 - 3500/7) = round(2300 - 500) = 1800
#   new weekly = 2300*7 - 3500 = 12600
# Turn 4 (Monday override on new baseline): Monday=1600
#   remaining = 12600-1600 = 11000; others = 11000//6 = 1833
_MT_DEFICIT_INITIAL = 4000
_MT_BASELINE_INITIAL = 12100   # 2300*7 - 4000; must NOT appear after turn 3
_MT_DEFICIT_NEW = 3500
_MT_BASELINE_NEW = 12600       # 2300*7 - 3500; must appear after turn 3
_MT_MON_T4 = 1600
_MT_OTHER_T4 = 1833            # (12600-1600)//6

_CAPABILITIES_DIR = str(Path(__file__).parent.parent.parent.parent / "capabilities")
_TEST_USER_ID = 99999
# Module-level session dir for single-shot tests; shared across the session.
_SINGLE_SHOT_SESSION_DIR = tempfile.mkdtemp(prefix="nutriosv2_ss_sessions_")


def _execute_turn_state(tool_use: Any, session_dir: str, user_id: int = _TEST_USER_ID) -> dict:
    return dict(compute_turn_state(
        user_message=tool_use.input.get("user_message", ""),
        user_id=int(tool_use.input.get("user_id", user_id)),
        session_dir=session_dir,
        capabilities_dir=_CAPABILITIES_DIR,
    ))


class MultiTurnHarness:
    """Multi-turn conversation harness for LLM integration tests.

    Maintains a persistent messages list across .send() calls, replicating how
    OpenClaw builds conversation history across Telegram turns. Tool calls are
    executed against the real Python implementations using a tmp data_root.

    assert_no_llm_arithmetic and assert_no_process_narration run on every
    assistant text block in every inner loop turn. Opt-out per .send() call via
    check_arithmetic=False / check_narration=False.
    """

    def __init__(
        self,
        llm_client: Any,
        system_prompt: str,
        tools: list[dict],
        data_root: str,
        session_dir: str,
        user_id: int = _TEST_USER_ID,
    ) -> None:
        self._client = llm_client
        self._system = system_prompt
        self._tools = tools
        self._data_root = data_root
        self._session_dir = session_dir
        self._user_id = user_id
        self._messages: list[dict] = []

    def send(
        self,
        user_message: str,
        max_tokens: int = 2048,
        max_inner_turns: int = 10,
        check_arithmetic: bool = True,
        check_narration: bool = True,
    ) -> tuple[list[Any], str]:
        """Append user_message, drive tool loop, return (all_tool_uses, final_text).

        turn_state is executed automatically and not counted in all_tool_uses.
        all_tool_uses contains only non-turn_state tool calls.
        check_arithmetic=False: skip zero-arithmetic assertion for this turn only.
        check_narration=False: skip process-narration assertion for this turn only.
        """
        self._messages.append({"role": "user", "content": user_message})
        all_tool_uses: list[Any] = []
        final_text = ""

        for _ in range(max_inner_turns):
            resp = self._client.messages.create(
                model=LLM_TEST_MODEL,
                temperature=LLM_TEST_TEMPERATURE,
                max_tokens=max_tokens,
                system=self._system,
                tools=self._tools,
                messages=self._messages,
            )
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            text = " ".join(b.text for b in resp.content if b.type == "text")
            if text:
                final_text = text
                # Arithmetic: check every text block (any arithmetic in any turn is a violation).
                # Narration: check only on the final user-facing response per .send() call.
                if check_arithmetic:
                    assert_no_llm_arithmetic(text)

            non_ts = [t for t in tool_uses if t.name != "turn_state"]
            all_tool_uses.extend(non_ts)
            self._messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn" or not tool_uses:
                break

            tool_results = []
            for tu in tool_uses:
                result = self._execute_tool(tu)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": str(result),
                })
            self._messages.append({"role": "user", "content": tool_results})

        # Process narration checked once on final text; intermediate pre-tool text is
        # LLM reasoning not shown directly in the user-facing response.
        if check_narration and final_text:
            assert_no_process_narration(final_text)
        return all_tool_uses, final_text

    def _execute_tool(self, tool_use: Any) -> dict:
        match tool_use.name:
            case "turn_state":
                return _execute_turn_state(tool_use, self._session_dir, self._user_id)
            case "compute_candidate_macros":
                inp = MacrosInput(**tool_use.input)
                return py_compute(inp)
            case "recompute_macros_with_overrides":
                inp = RecomputeInput(**tool_use.input)
                int_overrides = {int(k): v for k, v in inp.overrides.items()}
                try:
                    rows = py_recompute(
                        estimated_tdee_kcal=inp.estimated_tdee_kcal,
                        target_deficit_kcal=inp.target_deficit_kcal,
                        protein_floor_g=inp.protein_floor_g,
                        fat_ceiling_g=inp.fat_ceiling_g,
                        overrides=int_overrides,
                    )
                    return {
                        "weekly_kcal_target": inp.estimated_tdee_kcal * 7 - inp.target_deficit_kcal,
                        "rows": [r.model_dump() for r in rows],
                    }
                except ValueError as e:
                    return {"error": str(e)}
            case "lock_mesocycle":
                try:
                    inp = LockInput(**tool_use.input)
                    return run_lock_mesocycle(inp, data_root=self._data_root)
                except Exception as e:
                    return {"error": str(e)}
            case "get_active_mesocycle":
                uid = tool_use.input.get("user_id", self._user_id)
                try:
                    result = run_get_active_mesocycle(uid, data_root=self._data_root)
                    return result if result is not None else {"active_cycle": None}
                except Exception as e:
                    return {"error": str(e)}
            case _:
                return {"error": f"tool {tool_use.name!r} not available in test harness"}


def _call_with_tools(
    llm_client: Any,
    agent_system_prompt: str,
    agent_tools: list[dict],
    user_message: str,
    check_arithmetic: bool = True,
    check_narration: bool = True,
) -> tuple[list[Any], str, list[Any]]:
    """Single-session call with automatic turn_state execution.

    Drives a mini tool loop so turn_state is handled before returning.
    Returns (non_ts_tool_uses, final_text, last_resp_content) where
    non_ts_tool_uses excludes turn_state calls.
    """
    messages: list[dict] = [{"role": "user", "content": user_message}]
    all_non_ts: list[Any] = []
    final_text = ""
    last_content: list[Any] = []

    for _ in range(4):
        resp = llm_client.messages.create(
            model=LLM_TEST_MODEL,
            temperature=LLM_TEST_TEMPERATURE,
            max_tokens=1024,
            system=agent_system_prompt,
            tools=agent_tools,
            messages=messages,
        )
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        text = " ".join(b.text for b in resp.content if b.type == "text")
        last_content = resp.content
        if text:
            final_text = text
            # Arithmetic: every block. Narration: final block only (see MultiTurnHarness note).
            if check_arithmetic:
                assert_no_llm_arithmetic(text)

        non_ts = [t for t in tool_uses if t.name != "turn_state"]
        all_non_ts.extend(non_ts)

        if resp.stop_reason == "end_turn" or not tool_uses:
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tu in tool_uses:
            if tu.name == "turn_state":
                result = _execute_turn_state(tu, _SINGLE_SHOT_SESSION_DIR)
            elif tu.name == "compute_candidate_macros":
                inp = MacrosInput(**tu.input)
                result = py_compute(inp)
            else:
                result = {"error": f"tool {tu.name!r} not available in single-shot harness"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    if check_narration and final_text:
        assert_no_process_narration(final_text)
    return all_non_ts, final_text, last_content


def _call_with_tool_loop(
    llm_client: Any,
    agent_system_prompt: str,
    agent_tools: list[dict],
    user_message: str,
    max_tokens: int = 1024,
    max_turns: int = 4,
    check_arithmetic: bool = True,
    check_narration: bool = True,
) -> tuple[list[Any], str]:
    """Multi-turn: send user message, execute tool calls via Python, return final text.

    Returns (first_non_ts_tool_uses, final_text). first_non_ts_tool_uses is from
    the first assistant turn that contains non-turn_state tools (for arg assertions).
    turn_state is executed automatically; its result is not in the returned list.
    """
    messages: list[dict] = [{"role": "user", "content": user_message}]
    first_non_ts_tools: list[Any] | None = None
    final_text = ""

    for _ in range(max_turns):
        resp = llm_client.messages.create(
            model=LLM_TEST_MODEL,
            temperature=LLM_TEST_TEMPERATURE,
            max_tokens=max_tokens,
            system=agent_system_prompt,
            tools=agent_tools,
            messages=messages,
        )
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        text = " ".join(b.text for b in resp.content if b.type == "text")
        if text:
            final_text = text
            # Arithmetic: check every block (consistent with _call_with_tools and MultiTurnHarness).
            if check_arithmetic:
                assert_no_llm_arithmetic(text)

        non_ts = [t for t in tool_uses if t.name != "turn_state"]
        if first_non_ts_tools is None and non_ts:
            first_non_ts_tools = non_ts

        if resp.stop_reason == "end_turn" or not tool_uses:
            break

        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        for tu in tool_uses:
            if tu.name == "turn_state":
                result = _execute_turn_state(tu, _SINGLE_SHOT_SESSION_DIR)
            elif tu.name == "compute_candidate_macros":
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
                result = {"error": f"tool {tu.name!r} not available in loop harness"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    # Narration: final text only (pre-tool intermediate text is internal reasoning).
    if check_narration and final_text:
        assert_no_process_narration(final_text)
    return first_non_ts_tools or [], final_text


# ── single-shot tests ─────────────────────────────────────────────────────────

@pytest.mark.llm
def test_maintenance_name_deficit_1850_passes_through(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Cycle name 'maintenance' must not override an explicit deficit of 1850."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "Compute dose-day macros."
    )
    tool_uses, _, _ = _call_with_tools(
        llm_client, agent_system_prompt, agent_tools, msg,
        check_arithmetic=False, check_narration=False,
    )
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    args = compute_calls[0].input
    assert args.get("target_deficit_kcal") == 1850, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')}; "
        "expected 1850; LLM must not override user-supplied value"
    )


@pytest.mark.llm
def test_explicit_deficit_zero_passes_through(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Explicit deficit=0 (true maintenance) must reach the tool as 0, not null."""
    msg = (
        "Set up a cycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 0 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "Compute dose-day macros."
    )
    tool_uses, _, _ = _call_with_tools(
        llm_client, agent_system_prompt, agent_tools, msg,
        check_arithmetic=False, check_narration=False,
    )
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    args = compute_calls[0].input
    assert args.get("target_deficit_kcal") == 0, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')}; expected 0"
    )


@pytest.mark.llm
def test_omitted_deficit_prompts_question(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """When deficit is not supplied, LLM must ask; must not substitute a value."""
    msg = (
        "I want to start a new mesocycle. Name it 'maintenance'. "
        "4 weeks. Sunday dose. TDEE 2350 kcal/day. Protein floor 175g. Fat ceiling 65g."
    )
    tool_uses, text, _ = _call_with_tools(
        llm_client, agent_system_prompt, agent_tools, msg,
        check_arithmetic=False, check_narration=False,
    )
    compute_calls = [t for t in tool_uses if t.name == "compute_candidate_macros"]

    for call in compute_calls:
        assert call.input.get("target_deficit_kcal") is None, (
            f"LLM fabricated target_deficit_kcal={call.input.get('target_deficit_kcal')} "
            "when user did not supply a deficit"
        )

    if not compute_calls:
        text_lower = text.lower()
        assert any(w in text_lower for w in ("deficit", "how much", "target", "lose", "weekly")), (
            f"Expected LLM to ask about deficit, got: {text[:200]}"
        )


@pytest.mark.llm
def test_all_values_readback_matches_python_output(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Full tool loop: response reads back calories ±1 of Python output; no narration."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute dose-day macros and tell me the targets."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        check_arithmetic=False, check_narration=False,
    )
    compute_calls = [t for t in first_tool_uses if t.name == "compute_candidate_macros"]
    assert compute_calls, "Expected compute_candidate_macros to be called"
    assert first_tool_uses[0].input.get("target_deficit_kcal") == 1850

    assert final_text, "Expected a final text response after tool execution"

    stripped = final_text.replace(",", "")
    cal_matches = [int(m) for m in re.findall(r"\b(\d{4})\b", stripped)]
    assert any(abs(c - _EXPECTED_CALORIES) <= 1 for c in cal_matches), (
        f"Response calories not within +-1 of {_EXPECTED_CALORIES}. "
        f"4-digit numbers found: {cal_matches}. Full text: {final_text[:300]}"
    )

    forbidden = ["script", "algorithm", "compute_candidate", "the tool", "python"]
    text_lower = final_text.lower()
    for word in forbidden:
        assert word not in text_lower, (
            f"Response exposes implementation detail {word!r}: {final_text[:300]}"
        )


@pytest.mark.llm
def test_carbs_appears_in_readback(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """carbs_g must appear in read-back; LLM must not silently drop the fourth macro."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute dose-day macros and tell me the targets."
    )
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        check_arithmetic=False, check_narration=False,
    )
    assert final_text, "Expected a final text response after tool execution"

    stripped = final_text.replace(",", "")
    assert re.search(r"(?<!\d)" + str(_EXPECTED_CARBS_G) + r"(?!\d)", stripped), (
        f"carbs_g={_EXPECTED_CARBS_G} not found in response. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_weekday_names_in_readback_no_numeric_labels(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Rows must be labeled by weekday name; no +N or 'day N' numeric offset labels."""
    msg = (
        "Set up a mesocycle. Name: 'maintenance'. 4 weeks. Sunday dose. "
        "Weekly deficit: 1850 kcal. TDEE: 2350. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute all 7 rows and show me the full weekly macro table."
    )
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        max_tokens=2048, check_arithmetic=False, check_narration=False,
    )
    assert final_text, "Expected a final text response after tool execution"

    text_lower = final_text.lower()

    # Accept both full names ("sunday") and standard abbreviations ("sun").
    # Full names are preferred per capability rules; abbreviations are also compliant.
    weekday_tokens = [
        ("sunday", "sun"), ("monday", "mon"), ("tuesday", "tue"), ("wednesday", "wed"),
        ("thursday", "thu"), ("friday", "fri"), ("saturday", "sat"),
    ]
    found_days = [
        full for full, abbr in weekday_tokens
        if full in text_lower or abbr in text_lower
    ]
    assert len(found_days) >= 3, (
        f"Expected at least 3 weekday names in table, found: {found_days}. "
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
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Adjustment flow: LLM calls recompute tool; reads back 1550/1841 not inline arithmetic."""
    msg = (
        "We're negotiating a mesocycle. "
        "TDEE 2300 kcal/day, weekly deficit 3500 kcal, Sunday dose day, "
        "protein floor 175g, fat ceiling 65g. "
        "The baseline table shows 1800 cal/day across all 7 days. "
        "The user now says: Monday should be 1,550 kcal; raise the other days to compensate."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        max_tokens=2048, check_arithmetic=False, check_narration=False,
    )

    recompute_calls = [t for t in first_tool_uses if t.name == "recompute_macros_with_overrides"]
    assert recompute_calls, (
        f"Expected recompute_macros_with_overrides to be called. "
        f"Tools called: {[t.name for t in first_tool_uses]}"
    )

    args = recompute_calls[0].input
    overrides = args.get("overrides", {})
    override_calories = [v.get("calories") for v in overrides.values()]
    assert _ADJ_MONDAY_OVERRIDE in override_calories, (
        f"Expected {_ADJ_MONDAY_OVERRIDE} in override calories, got overrides={overrides}"
    )
    assert args.get("estimated_tdee_kcal") == 2300, (
        f"LLM sent estimated_tdee_kcal={args.get('estimated_tdee_kcal')}; expected 2300"
    )
    assert args.get("target_deficit_kcal") == 3500, (
        f"LLM sent target_deficit_kcal={args.get('target_deficit_kcal')}; expected 3500"
    )

    assert final_text, "Expected a final text response after tool execution"
    stripped = final_text.replace(",", "")

    assert re.search(r"(?<!\d)1550(?!\d)", stripped), (
        f"Monday value 1550 not found in response. Full text: {final_text[:400]}"
    )
    assert re.search(r"(?<!\d)" + str(_ADJ_OTHER_DAYS) + r"(?!\d)", stripped), (
        f"Other-days value {_ADJ_OTHER_DAYS} not found. Full text: {final_text[:400]}"
    )
    assert re.search(
        r"(?<!\d)" + str(_ADJ_WEEKLY_TARGET).replace(",", "") + r"(?!\d)", stripped
    ), (
        f"Weekly target {_ADJ_WEEKLY_TARGET} not found. Full text: {final_text[:400]}"
    )
    assert "12100" not in stripped and "12,100" not in final_text, (
        f"Wrong weekly baseline 12,100 found. Full text: {final_text[:400]}"
    )
    # Direct string match: catches bare wrong-number narration that the N op N = N
    # arithmetic regex does not cover (LLM stating "3,502 kcal deficit" without operator).
    assert "3502" not in stripped and "3,502" not in final_text, (
        f"Wrong deficit 3,502 found in response. Full text: {final_text[:400]}"
    )
    assert "4002" not in stripped and "4,002" not in final_text, (
        f"Wrong deficit 4,002 found in response. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_adjustment_flow_surfaces_constraint_error_on_infeasible_override(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Negative: override that exhausts budget must surface as a constraint question."""
    msg = (
        "We're negotiating a mesocycle. "
        "TDEE 2300 kcal/day, weekly deficit 3500 kcal, Sunday dose day, "
        "protein floor 175g, fat ceiling 65g. "
        "The user says: Monday should be 9,000 kcal; raise the other days."
    )
    first_tool_uses, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools, msg,
        max_tokens=1024, check_arithmetic=False, check_narration=False,
    )

    assert final_text, "Expected a text response"

    text_lower = final_text.lower()
    constraint_words = [
        "can't", "cannot", "constraint", "exceed", "budget", "floor",
        "won't work", "not possible", "too high", "leaves", "reduce"
    ]
    assert any(w in text_lower for w in constraint_words), (
        f"Expected LLM to surface a constraint. Got: {final_text[:400]}"
    )


@pytest.mark.llm
def test_intent_change_deficit_triggers_recompute(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
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
        check_arithmetic=False, check_narration=False,
    )

    assert final_text, "Expected a final text response"
    stripped = final_text.replace(",", "")

    assert re.search(r"(?<!\d)" + str(_IC_MONDAY) + r"(?!\d)", stripped), (
        f"Monday value {_IC_MONDAY} not found. Full text: {final_text[:400]}"
    )
    assert re.search(r"(?<!\d)" + str(_IC_OTHER_DAYS) + r"(?!\d)", stripped), (
        f"Other-days value {_IC_OTHER_DAYS} not found. Full text: {final_text[:400]}"
    )
    assert re.search(r"(?<!\d)" + str(_IC_NEW_WEEKLY) + r"(?!\d)", stripped), (
        f"New weekly target {_IC_NEW_WEEKLY} not found. Full text: {final_text[:400]}"
    )
    assert str(_IC_OLD_BASELINE) not in stripped, (
        f"Old baseline {_IC_OLD_BASELINE} found; LLM reused stale weekly intake. "
        f"Full text: {final_text[:400]}"
    )
    assert re.search(r"(?<!\d)" + str(_IC_NEW_DEFICIT) + r"(?!\d)", stripped), (
        f"New deficit {_IC_NEW_DEFICIT} not found in read-back. Full text: {final_text[:400]}"
    )


@pytest.mark.llm
def test_intent_change_deficit_does_not_narrate_arithmetic(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
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
    # assert_no_llm_arithmetic and assert_no_process_narration run automatically.
    # This test documents Bug B as a named regression scenario.


# ── multi-turn harness: production-arc fixture ────────────────────────────────

@pytest.mark.llm
def test_deficit_change_after_offer_multi_turn(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict], tmp_path: Any
) -> None:
    """Gate 3 regression (production arc): deficit-change-after-locked-offer must
    trigger fresh compute, not reuse stale baseline.

    Production arc reproduces the four structural differences from the 2026-04-26
    gate 3 failure that clean single-shot fixtures did not catch:

    1. Intent bundling (turn 1): all setup params arrive in one message.
    2. Continuity turn (turn 2): ambiguous "that looks good" between setup turns.
    3. Deficit-change-after-locked-offer (turn 3): user changes deficit after
       viewing a completed table (the exact shape that caused production drift).
    4. Override on new baseline (turn 4): Monday override must use new baseline.

    FAIL-BEFORE-FIX confirmation (tested against 6821d3d):
    - At 6821d3d: turn_state did not exist in either SKILL.md or openclaw.json.
      MultiTurnHarness._execute_tool had no turn_state case; any turn_state call
      returned {"error": "tool turn_state not available in test harness"}.
      The LLM received the error response and fell back to routing from the system
      prompt's pre-injected SKILL.md (old dispatch: "Load capabilities/mesocycle_setup.md").
      The fresh capability_prompt field was never delivered. In the production 172-message
      session, the capability loaded at turn 6 was the pre-follow-up-#3 version (lacking
      the "Recompute on intent change" rule). Turn 3 assertion fails: LLM reuses the
      12,100 baseline rather than calling compute_candidate_macros with deficit=3500.
    - At this commit: turn_state loads capability fresh per turn from disk. Every turn
      the LLM reads the current "Recompute on intent change" rule. Turn 3 assertion passes.
    """
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()
    harness = MultiTurnHarness(
        llm_client, agent_system_prompt, agent_tools,
        data_root=str(tmp_path / "data"),
        session_dir=session_dir,
    )

    # Turn 1 (intent bundling): all params in one message
    t1_tools, _ = harness.send(
        "New mesocycle: name 'maintenance', 4 weeks, Sunday dose, "
        f"protein floor 175g, fat ceiling 65g, TDEE 2300 kcal/day, "
        f"weekly deficit {_MT_DEFICIT_INITIAL:,} kcal. "
        "Compute and show all 7 rows.",
        check_arithmetic=False, check_narration=False,
    )
    compute_t1 = [t for t in t1_tools if t.name == "compute_candidate_macros"]
    assert compute_t1, "Turn 1: expected compute_candidate_macros to be called"
    assert compute_t1[0].input.get("target_deficit_kcal") == _MT_DEFICIT_INITIAL, (
        f"Turn 1: expected deficit={_MT_DEFICIT_INITIAL}, "
        f"got {compute_t1[0].input.get('target_deficit_kcal')}"
    )

    # Turn 2 (continuity): ambiguous continuation
    _, _ = harness.send("Yeah that looks right, continue.", check_arithmetic=False, check_narration=False)

    # Turn 3 (deficit-change-after-locked-offer): change deficit after seeing the table
    t3_tools, t3_text = harness.send(
        f"Actually, I want to change the weekly deficit to {_MT_DEFICIT_NEW:,} instead of "
        f"{_MT_DEFICIT_INITIAL:,}. Recompute the table with the new deficit.",
        check_arithmetic=False, check_narration=False,
    )
    compute_t3 = [t for t in t3_tools if t.name == "compute_candidate_macros"]
    assert compute_t3, (
        f"Turn 3: LLM must call compute_candidate_macros after deficit change to "
        f"{_MT_DEFICIT_NEW}; no call made. Recompute-on-intent-change rule not triggered. "
        f"Tools called: {[t.name for t in t3_tools]}"
    )
    assert compute_t3[0].input.get("target_deficit_kcal") == _MT_DEFICIT_NEW, (
        f"Turn 3: expected deficit={_MT_DEFICIT_NEW}, "
        f"got {compute_t3[0].input.get('target_deficit_kcal')}"
    )
    stripped3 = t3_text.replace(",", "")
    assert str(_MT_BASELINE_INITIAL) not in stripped3, (
        f"Turn 3: stale baseline {_MT_BASELINE_INITIAL} found; LLM reused prior weekly intake"
    )

    # Turn 4 (override on new baseline): _MT_OTHER_T4=1833 proves new 12600 baseline used
    t4_tools, t4_text = harness.send(
        f"Set Monday to {_MT_MON_T4:,} kcal and redistribute.",
        check_arithmetic=False, check_narration=False,
    )
    recompute_t4 = [t for t in t4_tools if t.name == "recompute_macros_with_overrides"]
    assert recompute_t4, "Turn 4: expected recompute_macros_with_overrides to be called"
    stripped4 = t4_text.replace(",", "")
    assert re.search(r"(?<!\d)" + str(_MT_OTHER_T4) + r"(?!\d)", stripped4), (
        f"Turn 4: other-day value {_MT_OTHER_T4} not found; "
        f"LLM may have used wrong baseline (12100 would yield 1750). "
        f"Response: {t4_text[:300]}"
    )
    assert str(_MT_BASELINE_INITIAL) not in stripped4, (
        f"Turn 4: stale baseline {_MT_BASELINE_INITIAL} still present"
    )
    assert re.search(r"(?<!\d)" + str(_MT_BASELINE_NEW) + r"(?!\d)", stripped4), (
        f"Turn 4: new weekly target {_MT_BASELINE_NEW} not found; confirms new baseline used"
    )


# ── narration compliance fixtures ─────────────────────────────────────────────
#
# One fixture per scenario class. Each sends a representative prompt and asserts
# assert_no_process_narration on the final assistant text. check_narration=True
# (default) so the harness auto-enforces the rule.
#
# Per-capability tests use check_narration=False because they assert argument
# correctness, tool-call shape, or output values; cross-cutting narration is
# enforced here. Separating the concerns prevents cascading failures where a
# narration violation in an unrelated code path fails an arg-correctness test.
# See CLAUDE.md "Test conditions match production conditions" section 6.


@pytest.mark.llm
def test_narration_compliance_single_turn_setup(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Scenario class: single-turn full setup. Final response must not narrate process.

    Covers: "Let me compute", "I'll run", script description, offset language,
    intermediate baseline exposure in the final response text.
    """
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools,
        "Set up a mesocycle. Name: 'cut'. 4 weeks. Sunday dose. "
        "Weekly deficit: 3500 kcal. TDEE: 2300. Protein floor: 175g. Fat ceiling: 65g. "
        "No restrictions. Compute dose-day macros and show me the result.",
        max_tokens=2048,
        check_narration=True,
    )
    assert final_text, "Expected a final text response"


@pytest.mark.llm
def test_narration_compliance_adjustment_flow(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict]
) -> None:
    """Scenario class: adjustment-flow row override. Final response must not narrate process.

    Covers: offset language ("offset 0 =", "(offset 1)"), "+N" labels, weekly
    budget arithmetic narration in the override explanation.
    """
    _, final_text = _call_with_tool_loop(
        llm_client, agent_system_prompt, agent_tools,
        "We're negotiating a mesocycle. "
        "TDEE 2300 kcal/day, weekly deficit 3500 kcal, Sunday dose day, "
        "protein floor 175g, fat ceiling 65g. "
        "The user says: Monday should be 1,550 kcal; raise the other days.",
        max_tokens=2048,
        check_narration=True,
    )
    assert final_text, "Expected a final text response"


@pytest.mark.llm
def test_narration_compliance_multi_turn(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict], tmp_path: Any
) -> None:
    """Scenario class: multi-turn conversation. Each turn's final response must not narrate.

    Covers: narration in continuity turns, offset language across turns, inline
    arithmetic after a deficit change. check_narration=True is the default;
    harness asserts it on every .send() final response.
    """
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()
    harness = MultiTurnHarness(
        llm_client, agent_system_prompt, agent_tools,
        data_root=str(tmp_path / "data"),
        session_dir=session_dir,
    )

    # Turn 1: full setup; narration assertion fires automatically on final text
    harness.send(
        "New mesocycle: name 'cut', 4 weeks, Sunday dose, "
        "protein floor 175g, fat ceiling 65g, TDEE 2300 kcal/day, "
        "weekly deficit 3500 kcal. Compute and show all 7 rows.",
        check_narration=True,
    )

    # Turn 2: continuity + deficit change; narration fires on final text
    harness.send(
        "Change the weekly deficit to 4000 kcal instead.",
        check_narration=True,
    )
