"""LLM integration tests for capabilities/meal_log.md: banana flow end-to-end.

Tests the full meal_log capability: estimate -> confirm -> write_meal_log ->
get_daily_reconciled_view -> read back remaining.

## Harness

Uses the production dispatch mechanism (turn_state) with the real capabilities_dir.
meal_log.md is loaded fresh per turn via turn_state. The harness handles all tools
the meal_log capability uses:
  - turn_state
  - estimate_macros_from_description (inner LLM call)
  - write_meal_log
  - get_daily_reconciled_view

data_root is a tmp directory; no mesocycle is active (remaining is null for all tests).
The today's date is injected into the system prompt so the LLM knows what date to pass
to get_daily_reconciled_view.

## Fail-before-fix baseline

These tests fail before estimate_macros_from_description and get_daily_reconciled_view
are registered in openclaw.json, before the meal_log.md confirm_macros sub-flow is
embedded, and before turn_state routes meal_log intent to the new capability file.
"""

from __future__ import annotations
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from estimate_macros import estimate_macros_from_description
from write_meal_log import _Input as WmlInput, run_write_meal_log
from get_daily_reconciled_view import _Input as GdrvInput, run_get_daily_reconciled_view
from turn_state import compute_turn_state
from llm_test_utils import (
    LLM_TEST_MODEL,
    LLM_TEST_TEMPERATURE,
    assert_no_llm_arithmetic,
    assert_no_process_narration,
)

_WORKSPACE = Path(__file__).parent.parent.parent.parent  # skills/nutriosv2/
_CAPABILITIES_DIR = str(_WORKSPACE / "capabilities")
_TEST_USER_ID = 99998
# Frozen date for reproducibility; the LLM is told this is today so it passes
# the same date to get_daily_reconciled_view across all runs. A dynamic date
# would introduce non-determinism in what the tool filters. Update if the LLM
# model's training cutoff makes this date too stale to be realistic.
_TODAY = "2026-04-26"


def _augment_system_prompt(base: str) -> str:
    return f"Today's date is {_TODAY} (America/Denver timezone).\n\n{base}"


def _execute_turn_state(tool_use: Any, session_dir: str, user_id: int) -> dict:
    return dict(compute_turn_state(
        user_message=tool_use.input.get("user_message", ""),
        user_id=int(tool_use.input.get("user_id", user_id)),
        session_dir=session_dir,
        capabilities_dir=_CAPABILITIES_DIR,
    ))


class MealLogHarness:
    """Multi-turn harness for meal_log capability tests.

    Handles turn_state, estimate_macros_from_description, write_meal_log, and
    get_daily_reconciled_view with real Python implementations and a tmp data_root.
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
        self.last_estimate: dict | None = None
        self.estimate_call_count: int = 0
        self.write_calls: list[Any] = []
        self.gdrv_call_count: int = 0

    def send(
        self,
        user_message: str,
        max_tokens: int = 1024,
        max_inner_turns: int = 8,
        check_arithmetic: bool = True,
        check_narration: bool = True,
    ) -> tuple[list[Any], str]:
        """Send one user turn; return (non-turn_state tool_uses, final_text)."""
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

        if check_narration and final_text:
            assert_no_process_narration(final_text)
        return all_tool_uses, final_text

    def _execute_tool(self, tu: Any) -> dict:
        match tu.name:
            case "turn_state":
                return _execute_turn_state(tu, self._session_dir, self._user_id)
            case "estimate_macros_from_description":
                result = estimate_macros_from_description(tu.input["description"])
                self.last_estimate = result
                self.estimate_call_count += 1
                return result
            case "write_meal_log":
                try:
                    inp = WmlInput(**{**tu.input, "user_id": self._user_id})
                    result = run_write_meal_log(inp, data_root=self._data_root)
                    self.write_calls.append(tu)
                    return result
                except Exception as e:
                    return {"error": str(e)}
            case "get_daily_reconciled_view":
                try:
                    inp = GdrvInput(**{**tu.input, "user_id": self._user_id})
                    self.gdrv_call_count += 1
                    return run_get_daily_reconciled_view(inp, data_root=self._data_root)
                except Exception as e:
                    return {"error": str(e)}
            case _:
                return {"error": f"tool {tu.name!r} not available in meal_log harness"}


# ── banana Yes path ───────────────────────────────────────────────────────────

@pytest.mark.llm
def test_meal_log_banana_yes(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """Banana flow: estimate -> Yes -> write_meal_log called with estimator macros.

    Production failure mode: LLM skips estimation and asks for macros manually, or
    calls write_meal_log with incorrect macro values (substituted, rounded, or computed).

    Assertions:
    - estimate_macros_from_description called exactly once
    - write_meal_log called exactly once with source=ad_hoc and macros matching
      estimator output (within rounding: floats to nearest int per schema)
    - get_daily_reconciled_view called; response reads back a log entry
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()

    augmented_prompt = _augment_system_prompt(agent_system_prompt)
    harness = MealLogHarness(
        llm_client, augmented_prompt, agent_tools,
        data_root=data_root, session_dir=session_dir,
    )

    # Turn 1: food description triggers meal_log intent; LLM calls estimate
    _, t1_text = harness.send(
        "I had 1 large banana",
        check_arithmetic=False, check_narration=False,
    )
    assert harness.estimate_call_count == 1, (
        "estimate_macros_from_description must be called after food description; "
        f"called {harness.estimate_call_count} times"
    )
    est = harness.last_estimate
    assert est is not None
    stripped1 = t1_text.replace(",", "")
    assert str(est["calories"]) in stripped1, (
        f"Estimator calories {est['calories']} not in read-back. Got: {t1_text[:300]}"
    )

    # Turn 2: Yes confirmation triggers write_meal_log + get_daily_reconciled_view
    _, t2_text = harness.send(
        "Yes",
        max_tokens=1024,
        check_arithmetic=False, check_narration=False,
    )

    assert len(harness.write_calls) == 1, (
        f"write_meal_log must be called exactly once after Yes; "
        f"called {len(harness.write_calls)} times"
    )
    wml_args = harness.write_calls[0].input
    assert wml_args.get("source") == "ad_hoc", (
        f"source must be 'ad_hoc'; got {wml_args.get('source')!r}"
    )
    macros = wml_args.get("macros", {})
    # Key-presence checks (NB-43): catch missing keys with clear messages before abs-delta
    for key in ("calories", "protein_g", "fat_g", "carbs_g"):
        assert key in macros, f"write_meal_log macros missing key {key!r}; got macros={macros}"
    assert abs(macros["calories"] - est["calories"]) <= 1, (
        f"write_meal_log calories {macros['calories']} differs from "
        f"estimator {est['calories']} by more than 1; verbatim passthrough required"
    )
    assert abs(macros["protein_g"] - round(est["protein_g"])) <= 1, (
        f"write_meal_log protein_g {macros['protein_g']} differs from "
        f"rounded estimator {round(est['protein_g'])}; only rounding to int is allowed"
    )
    assert abs(macros["fat_g"] - round(est["fat_g"])) <= 1, (
        f"write_meal_log fat_g {macros['fat_g']} differs from "
        f"rounded estimator {round(est['fat_g'])}"
    )
    assert abs(macros["carbs_g"] - round(est["carbs_g"])) <= 1, (
        f"write_meal_log carbs_g {macros['carbs_g']} differs from "
        f"rounded estimator {round(est['carbs_g'])}"
    )

    assert harness.gdrv_call_count >= 1, (
        "get_daily_reconciled_view must be called after write_meal_log"
    )

    # Response should contain the log_id or indicate successful logging
    assert t2_text, "Expected a final text response after logging"
    text_lower2 = t2_text.lower()
    assert any(w in text_lower2 for w in ("log", "logged", "banana")), (
        f"Response should acknowledge the logged meal. Got: {t2_text[:300]}"
    )


# ── donut Change path ─────────────────────────────────────────────────────────

@pytest.mark.llm
def test_meal_log_donut_change_calories(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """Donut flow with calories change: write_meal_log called with calories=250.

    Production failure mode: LLM recomputes other macros after single-field change,
    or writes with original estimator calories ignoring the change.

    Assertions:
    - write_meal_log.macros.calories == 250 (exact; change was applied)
    - write_meal_log.macros.protein_g / fat_g / carbs_g match estimator (unchanged)
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()

    _CHANGED_CALORIES = 250

    augmented_prompt = _augment_system_prompt(agent_system_prompt)
    harness = MealLogHarness(
        llm_client, augmented_prompt, agent_tools,
        data_root=data_root, session_dir=session_dir,
    )

    # Turn 1: food description
    _, _ = harness.send(
        "I had a donut",
        check_arithmetic=False, check_narration=False,
    )
    assert harness.estimate_call_count == 1
    est = harness.last_estimate
    assert est is not None

    # Turn 2: change calories
    _, t2_text = harness.send(
        f"change calories to {_CHANGED_CALORIES}",
        check_arithmetic=False, check_narration=False,
    )
    stripped2 = t2_text.replace(",", "")
    assert str(_CHANGED_CALORIES) in stripped2, (
        f"Changed calories {_CHANGED_CALORIES} not in updated read-back. Got: {t2_text[:300]}"
    )
    # Not yet written (user hasn't pressed Yes)
    assert len(harness.write_calls) == 0

    # Turn 3: Yes -> write_meal_log
    _, t3_text = harness.send(
        "Yes",
        max_tokens=1024,
        check_arithmetic=False, check_narration=False,
    )

    assert len(harness.write_calls) == 1, (
        f"write_meal_log must be called exactly once after Yes; "
        f"called {len(harness.write_calls)} times"
    )
    wml_args = harness.write_calls[0].input
    macros = wml_args.get("macros", {})
    # Key-presence checks (NB-43)
    for key in ("calories", "protein_g", "fat_g", "carbs_g"):
        assert key in macros, f"write_meal_log macros missing key {key!r}; got macros={macros}"

    # Changed calories must match exactly
    assert macros["calories"] == _CHANGED_CALORIES, (
        f"write_meal_log calories must be {_CHANGED_CALORIES} (user's change); "
        f"got {macros['calories']}"
    )
    # Other macros unchanged from estimator (within rounding tolerance)
    assert abs(macros["protein_g"] - round(est["protein_g"])) <= 1, (
        f"protein_g {macros['protein_g']} differs from estimator "
        f"{round(est['protein_g'])}; only calories should have changed"
    )
    assert abs(macros["fat_g"] - round(est["fat_g"])) <= 1, (
        f"fat_g {macros['fat_g']} differs from estimator {round(est['fat_g'])}"
    )
    assert abs(macros["carbs_g"] - round(est["carbs_g"])) <= 1, (
        f"carbs_g {macros['carbs_g']} differs from estimator {round(est['carbs_g'])}"
    )

    assert t3_text, "Expected a final text response after logging"


# ── narration compliance ───────────────────────────────────────────────────────

@pytest.mark.llm
def test_meal_log_narration_compliance(
    llm_client: Any, agent_system_prompt: str, agent_tools: list[dict],
    tmp_path: Any,
) -> None:
    """Narration compliance: no process narration in any turn of the meal_log flow.

    Cross-cutting check; check_narration=True (default) on every send.
    """
    data_root = str(tmp_path / "data")
    session_dir = str(tmp_path / "sessions")
    Path(session_dir).mkdir()

    augmented_prompt = _augment_system_prompt(agent_system_prompt)
    harness = MealLogHarness(
        llm_client, augmented_prompt, agent_tools,
        data_root=data_root, session_dir=session_dir,
    )

    harness.send("I had 1 large banana", check_narration=True)
    harness.send("Yes", max_tokens=1024, check_narration=True)
