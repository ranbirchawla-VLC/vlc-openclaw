"""turn_state — capability routing tool for grailzee-eval.

Classifies the incoming message, reads the matching capability file from
disk, and returns the instructions for this turn.

Input (stdin):  {"user_message": "<verbatim text>"}
Output (stdout): {"ok": true,  "data": {"intent": "...", "capability_prompt": "..."}}
                  {"ok": false, "error": "..."}

No side effects. No state written. Single-operator agent; no user_id needed.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import TypedDict

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPTS_DIR)
_CAPABILITIES_DIR = os.path.join(_SKILL_DIR, "capabilities")

_CAPABILITY_FILES: dict[str, str] = {
    "evaluate_deal": "deal.md",
    "report": "report.md",
    "ledger": "ledger.md",
}

_VALID_INTENTS: frozenset[str] = frozenset(set(_CAPABILITY_FILES) | {"default"})


class TurnStateResult(TypedDict):
    intent: str
    capability_prompt: str


def _classify(message: str) -> str:
    """Classify user message into one of: evaluate_deal, report, ledger, default.

    Precedence: slash command > dollar-sign price signal > report keywords >
    ledger keywords > default. Free-form deal detection requires a $ prefix
    on the price for disambiguation; /eval works without it.
    """
    lower = message.strip().lower()

    if lower.startswith("/eval"):
        return "evaluate_deal"
    if lower.startswith("/report"):
        return "report"
    if lower.startswith("/ledger"):
        return "ledger"

    if re.search(r"\$\d", lower):
        return "evaluate_deal"

    if re.search(r"\b(?:new report|report is in|grailzee pro|pipeline)\b|\.xlsx", lower):
        return "report"

    if re.search(r"\b(?:ledger|ingest|watchtrack|extract|jsonl|fold in)\b", lower):
        return "ledger"

    return "default"


def _load_capability(intent: str, capabilities_dir: str) -> str:
    filename = _CAPABILITY_FILES.get(intent)
    if filename is None:
        return ""
    path = os.path.join(capabilities_dir, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r") as f:
        return f.read()


def compute_turn_state(
    user_message: str,
    *,
    capabilities_dir: str = _CAPABILITIES_DIR,
) -> TurnStateResult:
    intent = _classify(user_message)
    capability_prompt = _load_capability(intent, capabilities_dir)
    return TurnStateResult(intent=intent, capability_prompt=capability_prompt)


def _ok(data: dict) -> None:
    print(json.dumps({"ok": True, "data": data}))


def _err(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}))


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        _err(f"Invalid JSON input: {e}")
        return

    user_message = payload.get("user_message")
    if user_message is None:
        _err("user_message is required")
        return
    if not isinstance(user_message, str):
        _err("user_message must be a string")
        return

    result = compute_turn_state(user_message)
    _ok(result)


if __name__ == "__main__":
    main()
