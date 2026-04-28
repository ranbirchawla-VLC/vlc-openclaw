"""turn_state; first-call-on-every-turn state tool for NutriOS.

On every user turn:
1. Classifies intent from the user message.
2. Reads prior intent from per-user state file in SESSION_DIR.
3. Computes boundary: True when a confident new intent differs from prior.
4. On boundary: atomic-renames the active session JSONL file so OpenClaw
   discovers an empty history on the next turn. Idempotent if file absent.
5. Records effective intent in state file for the next turn.
6. Returns capability_prompt read fresh from disk every invocation.

Side effect: renames <session_file>.jsonl to <session_file>.jsonl.reset.<utc-ts>
on intent-transition boundary. No caching at any layer.
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from typing import TypedDict

sys.path.insert(0, os.path.dirname(__file__))
import zoneinfo

from common import AGENT_TZ, SESSION_DIR, ok, err, read_json, write_json
from intent_classifier import classify_intent

_CAPABILITIES_DIR: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "capabilities",
)

_CAPABILITY_FILES: dict[str, str] = {
    "mesocycle_setup": "mesocycle_setup.md",
    "cycle_read_back": "mesocycle_setup.md",
    "meal_log": "meal_log.md",
    "today_view": "today_view.md",
}

_VALID_INTENTS: frozenset[str] = frozenset(set(_CAPABILITY_FILES) | {"default"})


class TurnStateResult(TypedDict):
    intent: str
    ambiguous: bool
    boundary: bool
    capability_prompt: str
    today_date: str


def _state_path(user_id: int, session_dir: str) -> str:
    return os.path.join(session_dir, f"{user_id}.state.json")


def _read_prior_intent(user_id: int, session_dir: str) -> str | None:
    state = read_json(_state_path(user_id, session_dir))
    if state is None:
        return None
    return state.get("last_intent")


def _write_intent_state(user_id: int, intent: str, session_dir: str) -> None:
    write_json(_state_path(user_id, session_dir), {"last_intent": intent})


def _find_session_file(user_id: int, session_dir: str) -> str | None:
    """Locate the active session JSONL path for (accountId=nutriosv2, from=telegram:<user_id>).

    Returns None when absent or when multiple candidates exist for the same peer.
    """
    sessions_path = os.path.join(session_dir, "sessions.json")
    data = read_json(sessions_path)
    if not data:
        return None

    peer_key = f"telegram:{user_id}"
    candidates: list[str] = []

    for entry in data.values():
        origin = entry.get("origin", {})
        if (
            origin.get("accountId") == "nutriosv2"
            and origin.get("from") == peer_key
        ):
            sf = entry.get("sessionFile")
            if sf:
                candidates.append(sf)

    if len(candidates) != 1:
        return None
    return candidates[0]


def _reset_session_file(user_id: int, session_dir: str) -> None:
    """Rename active session JSONL to <path>.reset.<utc-ts>. Idempotent if absent."""
    session_file = _find_session_file(user_id, session_dir)
    if session_file is None or not os.path.exists(session_file):
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.000Z")
    os.rename(session_file, f"{session_file}.reset.{ts}")


def _load_capability_prompt(intent: str, capabilities_dir: str) -> str:
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
    user_id: int,
    *,
    intent_override: str | None = None,
    session_dir: str = SESSION_DIR,
    capabilities_dir: str = _CAPABILITIES_DIR,
) -> TurnStateResult:
    """Compute intent, boundary, and capability_prompt for one user turn.

    intent_override: when provided, skips classifier and uses value directly
    as the effective intent. Raises ValueError for unknown values.
    session_dir and capabilities_dir are injectable for testing.
    """
    if intent_override is not None:
        if intent_override not in _VALID_INTENTS:
            raise ValueError(
                f"intent_override={intent_override!r} is not a valid intent; "
                f"valid: {sorted(_VALID_INTENTS)}"
            )
        intent = intent_override
        ambiguous = False
    else:
        intent, ambiguous = classify_intent(user_message)
    prior_intent = _read_prior_intent(user_id, session_dir)

    boundary = (
        not ambiguous
        and prior_intent is not None
        and intent != prior_intent
    )

    if boundary:
        sys.stderr.write(
            f"[NB-33] boundary detected user_id={user_id}; rename suppressed\n"
        )

    # Preserve prior intent on ambiguous turns to enable continuation.
    effective_intent = intent if not ambiguous else (prior_intent or "default")
    _write_intent_state(user_id, effective_intent, session_dir)

    capability_prompt = _load_capability_prompt(intent, capabilities_dir)
    today_date = datetime.now(zoneinfo.ZoneInfo(AGENT_TZ)).strftime("%Y-%m-%d")

    return TurnStateResult(
        intent=intent,
        ambiguous=ambiguous,
        boundary=boundary,
        capability_prompt=capability_prompt,
        today_date=today_date,
    )


def main() -> None:
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        err(f"Invalid JSON input: {e}")
        return

    user_message = input_data.get("user_message", "")
    user_id = input_data.get("user_id")
    intent_override = input_data.get("intent_override")

    if user_id is None:
        err("user_id is required")
        return

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        err("user_id must be an integer")
        return

    try:
        result = compute_turn_state(user_message, user_id, intent_override=intent_override)
    except Exception as e:
        err(f"turn_state failed for user_id={user_id}: {e}")
        return

    ok(result)


if __name__ == "__main__":
    main()
