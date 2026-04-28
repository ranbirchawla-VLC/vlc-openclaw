"""LLM integration tests for capabilities/today_view.md.

Three fixtures covering empty day, mid-day, and end-of-day states.
Each asserts the read-back contains the exact numeric values the tool returned
(no rounding, no substitution, no arithmetic narration).

## Harness

Uses the production dispatch mechanism (turn_state) with the real capabilities_dir.
today_view.md is loaded fresh per turn via turn_state. The harness handles:
  - turn_state
  - get_daily_reconciled_view (real Python implementation against tmp data_root)

Meal log entries are written directly to JSONL with hardcoded UTC timestamps on
_TODAY so tests are reproducible regardless of when they run.

## Date setup

_TODAY = "2026-04-27" (Monday, weekday 0). Mesocycle uses dose_weekday=0,
start_date="2026-04-27", giving offset=0 for the test date. Row 0 of the macro
table is used for all fixtures.

## Fail-before-fix baseline

These tests fail before today_view.md exists, before turn_state._CAPABILITY_FILES
maps "today_view" to "today_view.md", and before intent_classifier includes
_TODAY_VIEW_TRIGGERS.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from get_daily_reconciled_view import _Input as GdrvInput, run_get_daily_reconciled_view
from lock_mesocycle import _Input as LockInput, run_lock_mesocycle
from turn_state import compute_turn_state
from llm_test_utils import (
    LLM_TEST_MODEL,
    LLM_TEST_TEMPERATURE,
    assert_no_llm_arithmetic,
    assert_no_process_narration,
)

_WORKSPACE = Path(__file__).parent.parent.parent.parent  # skills/nutriosv2/
_CAPABILITIES_DIR = str(_WORKSPACE / "capabilities")
_TEST_USER_ID = 99997
_TODAY = "2026-04-27"

# Macro table row 0 (used when dose_weekday=0 and date is Monday 2026-04-27)
_TARGET_CALORIES = 2000
_TARGET_PROTEIN = 175
_TARGET_FAT = 50
_TARGET_CARBS = 200


def _augment_system_prompt(base: str) -> str:
    return f"Today's date is {_TODAY} (America/Denver timezone).\n\n{base}"


def _seven_rows() -> list[dict]:
    return [
        dict(
            calories=_TARGET_CALORIES,
            protein_g=_TARGET_PROTEIN,
            fat_g=_TARGET_FAT,
            carbs_g=_TARGET_CARBS,
            restrictions=[],
        )
        for _ in range(7)
    ]


def _seed_mesocycle(data_root: str) -> None:
    run_lock_mesocycle(
        LockInput(
            user_id=_TEST_USER_ID,
            name="test cut",
            weeks=13,
            start_date=_TODAY,
            dose_weekday=0,
            macro_table=_seven_rows(),
            intent=dict(target_deficit_kcal=3500, protein_floor_g=175, rationale="cut"),
        ),
        data_root=data_root,
    )


def _write_meal_entry(data_root: Path, entry: dict) -> None:
    log_dir = data_root / str(_TEST_USER_ID)
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "meal_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def _meal_entry(
    log_id: int,
    food_description: str,
    calories: int,
    protein_g: int,
    fat_g: int,
    carbs_g: int,
) -> dict:
    return {
        "log_id": log_id,
        "user_id": _TEST_USER_ID,
        "timestamp_utc": f"{_TODAY}T14:00:00Z",
        "timezone_at_log": "America/Denver",
        "food_description": food_description,
        "macros": {
            "calories": calories,
            "protein_g": protein_g,
            "fat_g": fat_g,
            "carbs_g": carbs_g,
        },
        "source": "ad_hoc",
        "recipe_id": None,
        "recipe_name_snapshot": None,
        "supersedes": None,
    }


class TodayViewHarness:
    """Single-turn harness for today_view capability tests.

    Handles turn_state and get_daily_reconciled_view with real Python
    implementations against a tmp data_root.
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
        self.gdrv_call_count: int = 0
        self.gdrv_result: dict | None = None

    def send(
        self,
        user_message: str,
        max_tokens: int = 512,
        max_inner_turns: int = 6,
    ) -> str:
        """Send one user turn; return the final text response."""
        self._messages.append({"role": "user", "content": user_message})
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
                assert_no_llm_arithmetic(text)

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

        if final_text:
            assert_no_process_narration(final_text)
        return final_text

    def _execute_tool(self, tu: Any) -> dict:
        match tu.name:
            case "turn_state":
                result = dict(compute_turn_state(
                    user_message=tu.input.get("user_message", ""),
                    user_id=int(tu.input.get("user_id", self._user_id)),
                    session_dir=self._session_dir,
                    capabilities_dir=_CAPABILITIES_DIR,
                ))
                # Freeze today_date for test reproducibility; seeded meal log
                # entries have timestamps on _TODAY regardless of when the test runs.
                result["today_date"] = _TODAY
                return result
            case "get_daily_reconciled_view":
                try:
                    inp = GdrvInput(**{**tu.input, "user_id": self._user_id})
                    result = run_get_daily_reconciled_view(inp, data_root=self._data_root)
                    self.gdrv_call_count += 1
                    self.gdrv_result = result
                    return result
                except Exception as e:
                    return {"error": str(e)}
            case _:
                return {"error": f"tool {tu.name!r} not available in today_view harness"}


# ── empty day ─────────────────────────────────────────────────────────────────

@pytest.mark.llm
def test_today_view_empty_day(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """Empty day: active cycle, no meals logged. Read-back shows zero consumed, full remaining.

    Production failure mode: LLM substitutes or computes remaining instead of reading
    the tool result; or omits the target/remaining summary.

    Assertions:
    - get_daily_reconciled_view called exactly once
    - response contains exact target calories (2000); verbatim from tool result
    - response contains exact remaining protein (175); verbatim from tool result
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()
    _seed_mesocycle(data_root)

    expected = run_get_daily_reconciled_view(
        GdrvInput(user_id=_TEST_USER_ID, date=_TODAY, active_timezone="America/Denver"),
        data_root=data_root,
    )
    assert expected["target"] is not None
    assert expected["consumed"]["calories"] == 0

    augmented = _augment_system_prompt(agent_system_prompt)
    harness = TodayViewHarness(llm_client, augmented, agent_tools, data_root, session_dir)

    text = harness.send("what have I eaten today")

    assert harness.gdrv_call_count >= 1, (
        "get_daily_reconciled_view must be called for today_view; "
        f"called {harness.gdrv_call_count} times"
    )

    stripped = text.replace(",", "")
    target_cal = expected["target"]["calories"]
    remaining_protein = expected["remaining"]["protein_g"]
    assert str(target_cal) in stripped, (
        f"Target calories {target_cal} not in response (verbatim rule). Got: {text[:400]}"
    )
    assert str(remaining_protein) in stripped, (
        f"Remaining protein {remaining_protein} not in response (verbatim rule). Got: {text[:400]}"
    )


# ── mid-day (banana) ──────────────────────────────────────────────────────────

@pytest.mark.llm
def test_today_view_midday_banana(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """Mid-day: active cycle, one banana logged. Read-back includes entry and consumed totals.

    Production failure mode: LLM rounds or recomputes consumed/remaining instead
    of reading tool result verbatim; or omits the entry from the meal list.

    Assertions:
    - get_daily_reconciled_view called exactly once
    - response mentions "banana" (entry list read-back)
    - response contains exact consumed calories (105) from tool result
    - response contains exact remaining calories (1895) from tool result
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()
    _seed_mesocycle(data_root)
    _write_meal_entry(
        tmp_path / "data",
        _meal_entry(1, "1 large banana", calories=105, protein_g=1, fat_g=0, carbs_g=27),
    )

    expected = run_get_daily_reconciled_view(
        GdrvInput(user_id=_TEST_USER_ID, date=_TODAY, active_timezone="America/Denver"),
        data_root=data_root,
    )
    assert expected["consumed"]["calories"] == 105
    assert expected["remaining"]["calories"] == _TARGET_CALORIES - 105

    augmented = _augment_system_prompt(agent_system_prompt)
    harness = TodayViewHarness(llm_client, augmented, agent_tools, data_root, session_dir)

    text = harness.send("what have I eaten today")

    assert harness.gdrv_call_count >= 1, (
        "get_daily_reconciled_view must be called; "
        f"called {harness.gdrv_call_count} times"
    )

    text_lower = text.lower()
    assert "banana" in text_lower, (
        f"Entry 'banana' not in response. Got: {text[:400]}"
    )

    stripped = text.replace(",", "")
    consumed_cal = expected["consumed"]["calories"]
    remaining_cal = expected["remaining"]["calories"]
    assert str(consumed_cal) in stripped, (
        f"Consumed calories {consumed_cal} not in response (verbatim rule). Got: {text[:400]}"
    )
    assert str(remaining_cal) in stripped, (
        f"Remaining calories {remaining_cal} not in response (verbatim rule). Got: {text[:400]}"
    )


# ── end-of-day (multiple meals) ───────────────────────────────────────────────

@pytest.mark.llm
def test_today_view_end_of_day(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """End-of-day: active cycle, three meals logged near target.

    Production failure mode: LLM sums meals itself instead of reading consumed
    from the tool result; or omits entries; or rounds remaining values.

    Assertions:
    - get_daily_reconciled_view called exactly once
    - response contains exact consumed calories (1172) from tool result
    - response contains exact remaining calories (828) from tool result
    - response mentions at least one of the logged food descriptions
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()
    _seed_mesocycle(data_root)

    entries = [
        _meal_entry(1, "oatmeal", calories=300, protein_g=10, fat_g=6, carbs_g=54),
        _meal_entry(2, "chicken and rice", calories=550, protein_g=55, fat_g=12, carbs_g=55),
        _meal_entry(3, "protein shake", calories=322, protein_g=56, fat_g=4, carbs_g=16),
    ]
    for entry in entries:
        _write_meal_entry(tmp_path / "data", entry)

    expected = run_get_daily_reconciled_view(
        GdrvInput(user_id=_TEST_USER_ID, date=_TODAY, active_timezone="America/Denver"),
        data_root=data_root,
    )
    assert expected["consumed"]["calories"] == 1172
    assert expected["remaining"]["calories"] == _TARGET_CALORIES - 1172

    augmented = _augment_system_prompt(agent_system_prompt)
    harness = TodayViewHarness(llm_client, augmented, agent_tools, data_root, session_dir)

    text = harness.send("what have I eaten today")

    assert harness.gdrv_call_count >= 1, (
        "get_daily_reconciled_view must be called; "
        f"called {harness.gdrv_call_count} times"
    )

    stripped = text.replace(",", "")
    consumed_cal = expected["consumed"]["calories"]
    remaining_cal = expected["remaining"]["calories"]
    assert str(consumed_cal) in stripped, (
        f"Consumed calories {consumed_cal} not in response (verbatim rule). Got: {text[:400]}"
    )
    assert str(remaining_cal) in stripped, (
        f"Remaining calories {remaining_cal} not in response (verbatim rule). Got: {text[:400]}"
    )

    text_lower = text.lower()
    food_names = ["oatmeal", "chicken", "protein shake"]
    assert any(name in text_lower for name in food_names), (
        f"None of the logged food descriptions found in response. Got: {text[:400]}"
    )
