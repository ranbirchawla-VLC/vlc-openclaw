"""Intent classifier for NutriOS; mirrors SKILL.md dispatch pattern-match logic."""

from __future__ import annotations

_MESOCYCLE_SETUP_TRIGGERS: list[str] = [
    "set up a cycle",
    "new mesocycle",
    "start a plan",
    "new cycle",
    "set up my plan",
    "create a cycle",
    "create a new mesocycle",
    "new meso",
    "i want to start",
]

_CYCLE_READ_BACK_TRIGGERS: list[str] = [
    "what's my cycle",
    "show my plan",
    "what are my macros",
    "what's my target today",
    "show my mesocycle",
    "what cycle am i on",
]

_MEAL_LOG_TRIGGERS: list[str] = [
    "log a meal",
    "log meal",
    "i ate",
    "i had",
    "just ate",
    "just had",
    "food log",
    "log food",
    "track a meal",
    "add a meal",
    "log my meal",
    "log breakfast",
    "log lunch",
    "log dinner",
    "log a snack",
]

_TODAY_VIEW_TRIGGERS: list[str] = [
    "what have i eaten today",
    "what's left today",
    "show me today",
    "today view",
    "what about today",
    "what have i had today",
]


def classify_intent(message: str) -> tuple[str, bool]:
    """Classify a user message into (intent, ambiguous).

    intent: "mesocycle_setup" | "cycle_read_back" | "meal_log" | "today_view" | "default"
    ambiguous: True when no trigger phrase matched; callers default to continuation.
    """
    msg_lower = message.lower()

    for phrase in _MESOCYCLE_SETUP_TRIGGERS:
        if phrase in msg_lower:
            return ("mesocycle_setup", False)

    for phrase in _CYCLE_READ_BACK_TRIGGERS:
        if phrase in msg_lower:
            return ("cycle_read_back", False)

    for phrase in _TODAY_VIEW_TRIGGERS:
        if phrase in msg_lower:
            return ("today_view", False)

    for phrase in _MEAL_LOG_TRIGGERS:
        if phrase in msg_lower:
            return ("meal_log", False)

    return ("default", True)
