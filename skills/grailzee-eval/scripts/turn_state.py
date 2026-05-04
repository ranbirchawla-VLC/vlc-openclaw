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
from pathlib import Path
from typing import TypedDict

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPTS_DIR)
_V2_ROOT = str(Path(_SCRIPTS_DIR).parent)
sys.path.insert(0, _V2_ROOT)

from scripts.grailzee_common import attach_parent_trace_context, get_tracer

tracer = get_tracer(__name__)
_CAPABILITIES_DIR = os.path.join(_SKILL_DIR, "capabilities")

_CAPABILITY_FILES: dict[str, str] = {
    "evaluate_deal": "deal.md",
    "report": "report.md",
    "ledger": "ledger.md",
    "buying": "buying.md",
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
    if lower.startswith("/buying"):
        return "buying"

    if re.search(r"\$\d", lower):
        return "evaluate_deal"

    if re.search(r"\b(?:new report|report is in|grailzee pro|pipeline)\b|\.xlsx", lower):
        return "report"

    if re.search(r"\b(?:ledger|ingest|watchtrack|extract|jsonl|fold in)\b", lower):
        return "ledger"

    if re.search(r"\b(?:buying list|what.*buy|targets|this week)\b", lower):
        return "buying"

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
    with attach_parent_trace_context(), tracer.start_as_current_span("turn_state.run") as span:
        intent = _classify(user_message)
        capability_file = _CAPABILITY_FILES.get(intent)
        capability_prompt = _load_capability(intent, capabilities_dir)
        span.set_attribute("intent", intent)
        span.set_attribute("capability_file", capability_file or "")
        span.set_attribute("capability_loaded", len(capability_prompt) > 0)
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
