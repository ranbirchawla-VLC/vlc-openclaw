"""LLM integration tests for capabilities/_shared/confirm_macros.md sub-flow.

Tests the estimate-and-confirm pattern in isolation using a minimal capability
that applies the sub-flow without any downstream write call. Production callers
(meal_log, recipe_build) embed this snippet; this file tests the snippet
independent of the dispatch mechanism.

## Design

The system prompt is built from confirm_macros.md content plus a minimal instruction
("after Yes, state confirmed macros and stop"). Only estimate_macros_from_description
is available as a tool; no turn_state, no write_meal_log. This isolates the confirm
sub-flow from production dispatch and write-side effects.

## Fail-before-fix baseline

These tests fail before confirm_macros.md exists and before
estimate_macros_from_description is callable from the LLM. They pass once both
are in place and the snippet correctly routes Yes/No/Change.
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from estimate_macros import estimate_macros_from_description
from llm_test_utils import (
    LLM_TEST_MODEL,
    LLM_TEST_TEMPERATURE,
    assert_no_llm_arithmetic,
    assert_no_process_narration,
)

_WORKSPACE = Path(__file__).parent.parent.parent.parent  # skills/nutriosv2/
_CAPABILITIES_DIR = _WORKSPACE / "capabilities"
_TOOLS_SCHEMA = _WORKSPACE.parent.parent / "plugins" / "nutriosv2-tools" / "tools.schema.json"


def _build_confirm_macros_system_prompt() -> str:
    confirm_md = (_CAPABILITIES_DIR / "_shared" / "confirm_macros.md").read_text()
    return (
        "You are NutriOS, a nutrition assistant.\n\n"
        "When the user describes a food item, apply the confirm_macros sub-flow below.\n"
        "After the user confirms (presses Yes or supplies macros directly), state the\n"
        "confirmed macros in this format:\n"
        "\"Confirmed: [calories] cal, [protein_g]g protein, [fat_g]g fat, [carbs_g]g carbs.\"\n"
        "Do not call write_meal_log or any tool beyond estimate_macros_from_description.\n\n"
        f"{confirm_md}"
    )


def _build_confirm_tools() -> list[dict]:
    config = json.loads(_TOOLS_SCHEMA.read_text())
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["inputSchema"],
        }
        for t in config.get("tools", [])
        if t["name"] == "estimate_macros_from_description"
    ]


class ConfirmMacrosHarness:
    """Multi-turn harness for confirm_macros sub-flow tests.

    Only estimate_macros_from_description is available; any other tool call
    returns an error, letting us assert the snippet does not call write_meal_log.
    """

    def __init__(self, llm_client: Any, system_prompt: str, tools: list[dict]) -> None:
        self._client = llm_client
        self._system = system_prompt
        self._tools = tools
        self._messages: list[dict] = []
        self.last_estimate: dict | None = None
        self.estimate_call_count: int = 0
        self.write_call_count: int = 0

    def send(
        self,
        user_message: str,
        max_tokens: int = 1024,
        max_inner_turns: int = 6,
        check_arithmetic: bool = True,
        check_narration: bool = True,
    ) -> tuple[list[Any], str]:
        """Send one user turn; return (tool_uses, final_text)."""
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

            all_tool_uses.extend(tool_uses)
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
            case "estimate_macros_from_description":
                result = estimate_macros_from_description(tu.input["description"])
                self.last_estimate = result
                self.estimate_call_count += 1
                return result
            case "write_meal_log":
                self.write_call_count += 1
                return {"error": "write_meal_log not available in confirm_macros harness"}
            case _:
                return {"error": f"tool {tu.name!r} not available in confirm_macros harness"}


@pytest.fixture(scope="module")
def confirm_system_prompt() -> str:
    return _build_confirm_macros_system_prompt()


@pytest.fixture(scope="module")
def confirm_tools() -> list[dict]:
    return _build_confirm_tools()


# ── Yes path ─────────────────────────────────────────────────────────────────

@pytest.mark.llm
def test_confirm_macros_yes_path(
    llm_client: Any, confirm_system_prompt: str, confirm_tools: list[dict]
) -> None:
    """Yes path: estimator called once; confirmed macros match estimator output verbatim.

    Production failure mode: LLM substitutes or rounds values before write_meal_log.
    This test asserts that after Yes, the confirmed calorie value equals what the
    estimator returned. write_meal_log must not be called in this snippet-only harness.
    """
    harness = ConfirmMacrosHarness(llm_client, confirm_system_prompt, confirm_tools)

    _, t1_text = harness.send(
        "1 large banana",
        check_arithmetic=False, check_narration=False,
    )
    assert harness.estimate_call_count == 1, (
        "estimate_macros_from_description must be called after food description"
    )
    est = harness.last_estimate
    assert est is not None

    stripped1 = t1_text.replace(",", "")
    assert str(est["calories"]) in stripped1, (
        f"Estimator calories {est['calories']} not in read-back. Got: {t1_text[:300]}"
    )
    text_lower1 = t1_text.lower()
    assert any(w in text_lower1 for w in ("yes", "no", "change")), (
        f"Expected Yes/No/Change buttons in read-back. Got: {t1_text[:300]}"
    )

    _, t2_text = harness.send(
        "Yes",
        check_arithmetic=False, check_narration=False,
    )
    stripped2 = t2_text.replace(",", "")
    # All four estimator values must appear verbatim in the confirmed readback (NB-37)
    assert str(est["calories"]) in stripped2, (
        f"Estimator calories {est['calories']} not in confirmed response. Got: {t2_text[:300]}"
    )
    assert str(round(est["protein_g"])) in stripped2, (
        f"Estimator protein_g {round(est['protein_g'])} not in confirmed response. Got: {t2_text[:300]}"
    )
    assert str(round(est["fat_g"])) in stripped2, (
        f"Estimator fat_g {round(est['fat_g'])} not in confirmed response. Got: {t2_text[:300]}"
    )
    assert str(round(est["carbs_g"])) in stripped2, (
        f"Estimator carbs_g {round(est['carbs_g'])} not in confirmed response. Got: {t2_text[:300]}"
    )
    assert harness.estimate_call_count == 1, (
        "estimate_macros_from_description called more than once for the same item"
    )
    assert harness.write_call_count == 0, (
        "write_meal_log must not be called from the confirm_macros snippet"
    )


# ── Change path ───────────────────────────────────────────────────────────────

@pytest.mark.llm
def test_confirm_macros_change_path(
    llm_client: Any, confirm_system_prompt: str, confirm_tools: list[dict]
) -> None:
    """Change path: single-field change applied; other estimator values untouched.

    Production failure mode: LLM recomputes all fields after a single-field change.
    This test asserts protein=2 in the updated read-back and that the estimator
    calories value still appears (not recomputed).
    """
    harness = ConfirmMacrosHarness(llm_client, confirm_system_prompt, confirm_tools)

    _, _ = harness.send(
        "1 large banana",
        check_arithmetic=False, check_narration=False,
    )
    assert harness.estimate_call_count == 1
    est = harness.last_estimate
    assert est is not None

    _, t2_text = harness.send(
        "change protein to 2",
        check_arithmetic=False, check_narration=False,
    )
    stripped2 = t2_text.replace(",", "")

    # protein should be 2 in the updated read-back
    assert re.search(r"(?<!\d)2(?!\d)", stripped2), (
        f"Updated protein value 2 not found in response. Got: {t2_text[:300]}"
    )
    # calories, fat, and carbs should still match estimator (not recomputed); NB-38
    assert str(est["calories"]) in stripped2, (
        f"Estimator calories {est['calories']} missing after protein change; "
        f"LLM may have recomputed calories. Got: {t2_text[:300]}"
    )
    assert str(round(est["fat_g"])) in stripped2 or re.search(
        r'\b' + re.escape(str(est["fat_g"])) + r'\b', t2_text
    ), (
        f"Estimator fat_g {est['fat_g']} missing after protein change; "
        f"LLM may have recomputed fat. Got: {t2_text[:300]}"
    )
    assert str(round(est["carbs_g"])) in stripped2 or re.search(
        r'\b' + re.escape(str(est["carbs_g"])) + r'\b', t2_text
    ), (
        f"Estimator carbs_g {est['carbs_g']} missing after protein change; "
        f"LLM may have recomputed carbs. Got: {t2_text[:300]}"
    )
    assert harness.estimate_call_count == 1, (
        "estimate_macros_from_description called again after change; must not re-estimate"
    )
    assert harness.write_call_count == 0


# ── No path ───────────────────────────────────────────────────────────────────

@pytest.mark.llm
def test_confirm_macros_no_path(
    llm_client: Any, confirm_system_prompt: str, confirm_tools: list[dict]
) -> None:
    """No path: bot asks for macros directly; confirmed macros are user-supplied values.

    Production failure mode: LLM falls back to estimator values despite user rejection.
    This test asserts the bot asks for calories/protein/fat/carbs and reads back
    the user-supplied values (not the estimator's).
    """
    harness = ConfirmMacrosHarness(llm_client, confirm_system_prompt, confirm_tools)

    _, _ = harness.send(
        "1 large banana",
        check_arithmetic=False, check_narration=False,
    )
    assert harness.estimate_call_count == 1
    est = harness.last_estimate
    assert est is not None

    _, t2_text = harness.send(
        "No",
        check_arithmetic=False, check_narration=False,
    )
    text_lower2 = t2_text.lower()
    assert any(w in text_lower2 for w in ("calorie", "protein", "fat", "carb", "macro")), (
        f"Expected bot to ask for macros after No. Got: {t2_text[:300]}"
    )

    # User provides completely different macros
    _USER_CAL = 420
    _USER_PROT = 10
    _, t3_text = harness.send(
        f"{_USER_CAL} calories, {_USER_PROT}g protein, 15g fat, 65g carbs",
        check_arithmetic=False, check_narration=False,
    )
    stripped3 = t3_text.replace(",", "")
    assert str(_USER_CAL) in stripped3, (
        f"User-supplied calories {_USER_CAL} not in confirmed response. Got: {t3_text[:300]}"
    )
    assert str(_USER_PROT) in stripped3, (
        f"User-supplied protein {_USER_PROT} not in confirmed response. Got: {t3_text[:300]}"
    )
    # Estimator calories must NOT appear (user rejected them)
    assert str(est["calories"]) not in stripped3 or _USER_CAL == est["calories"], (
        f"Estimator calories {est['calories']} appeared in confirmed response after user rejection. "
        f"Got: {t3_text[:300]}"
    )
    assert harness.write_call_count == 0, (
        "write_meal_log must not be called from the confirm_macros snippet"
    )


# ── narration compliance ───────────────────────────────────────────────────────

@pytest.mark.llm
def test_confirm_macros_narration_compliance(
    llm_client: Any, confirm_system_prompt: str, confirm_tools: list[dict]
) -> None:
    """Narration compliance: estimation process must not be narrated in any turn.

    Cross-cutting check; check_narration=True (default) on every send.
    """
    harness = ConfirmMacrosHarness(llm_client, confirm_system_prompt, confirm_tools)

    harness.send("1 large banana", check_narration=True)
    harness.send("Yes", check_narration=True)
