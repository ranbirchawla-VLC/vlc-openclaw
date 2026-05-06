"""turn_state -- multi-mode dispatcher for the GTD agent.

Classifies intent from the user message (three layers: deterministic signals,
inner LLM fallback, unknown routing), reads the matching capability file from
disk, and returns {intent, capability_prompt}.

Input (stdin):  {"user_message": "<verbatim text>"}
Output (stdout): {"ok": true,  "data": {"intent": "...", "capability_prompt": "..."}}
                 {"ok": false, "error": {"code": "...", "message": "..."}}

No side effects. No state written. Capability file read fresh every call.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import TypedDict

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import anthropic
from common import GTDError, err, ok
from otel_common import attach_parent_trace_context, configure_tracer_provider, get_tracer  # noqa: F401 re-exported for tests
from opentelemetry.trace import StatusCode

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0
_MAX_TOKENS = 256
_MAX_RETRIES = 3

_VALID_INTENTS: frozenset[str] = frozenset({
    "capture",
    "query_tasks",
    "query_ideas",
    "query_parking_lot",
    "review",
    "calendar_read",
    "unknown",
})

_TOOL_INTENTS: frozenset[str] = _VALID_INTENTS - {"unknown"}

# ---------------------------------------------------------------------------
# Signal patterns (Layer 1 -- deterministic)
# Compiled once at module load. High precision; false positive worse than miss.
# ---------------------------------------------------------------------------

_SIGNALS: list[tuple[str, list[re.Pattern[str]]]] = [
    ("capture", [
        re.compile(r"\bremind me\b", re.I),
        re.compile(r"\badd\b.{0,20}\btask\b", re.I),
        re.compile(r"\bnote that\b", re.I),
        re.compile(r"\bdon'?t forget\b", re.I),
        re.compile(r"\bi need to\b", re.I),
        re.compile(r"\bwe need to\b", re.I),
        re.compile(r"\bfollow up on\b", re.I),
        re.compile(r"\bwaiting on\b", re.I),
        re.compile(r"^task:", re.I),
        re.compile(r"^idea:", re.I),
        re.compile(r"\bpark this\b", re.I),
        re.compile(r"^parking lot:", re.I),
        # Decision 6: verb wins over target ("park this in ideas: ...")
        re.compile(r"\bpark\s+this\s+in\b", re.I),
    ]),
    ("query_tasks", [
        re.compile(r"\bwhat\b.{0,30}\btasks?\b", re.I),
        re.compile(r"\bshow\b.{0,20}\btasks?\b", re.I),
        re.compile(r"\bmy tasks?\b", re.I),
        re.compile(r"\bnext actions?\b", re.I),
        re.compile(r"\bwhat\b.{0,20}\bto.?do\b", re.I),
        re.compile(r"\bopen tasks?\b", re.I),
        re.compile(r"\bwhat\b.{0,30}\bon my list\b", re.I),
        # Decision 6: commitment-biased reading for "plate"
        re.compile(r"\bwhat'?s\b.{0,20}\bon my plate\b", re.I),
        re.compile(r"\bwhat\b.{0,20}\bon my plate\b", re.I),
    ]),
    ("query_ideas", [
        re.compile(r"\bmy ideas?\b", re.I),
        re.compile(r"\bshow\b.{0,20}\bideas?\b", re.I),
        re.compile(r"\bany ideas?\b", re.I),
    ]),
    ("query_parking_lot", [
        re.compile(r"\bparking lot\b", re.I),
        re.compile(r"\bwhat\b.{0,20}\bparking\b", re.I),
    ]),
    ("review", [
        re.compile(r"\bweekly review\b", re.I),
        re.compile(r"\brun\b.{0,20}\breview\b", re.I),
        re.compile(r"\breview\b.{0,20}\blist\b", re.I),
        re.compile(r"\breview time\b", re.I),
        re.compile(r"\bdo\b.{0,20}\breview\b", re.I),
        re.compile(r"\bmy review\b", re.I),
    ]),
    ("calendar_read", [
        re.compile(r"\bcalendar\b", re.I),
        re.compile(r"\bschedule\b", re.I),
        re.compile(r"\bagenda\b", re.I),
        re.compile(r"\bwhat\b.{0,20}\bon.{0,10}\btoday\b", re.I),
        re.compile(r"\bevents?\b", re.I),
    ]),
]


# ---------------------------------------------------------------------------
# Layer 1: deterministic signal classifier
# ---------------------------------------------------------------------------

def _classify_deterministic(user_message: str) -> dict | None:
    """Return {intent, confidence, rationale} if a signal pattern matches, else None."""
    for intent, patterns in _SIGNALS:
        for pat in patterns:
            if pat.search(user_message):
                return {"intent": intent, "confidence": "high", "rationale": f"signal:{pat.pattern}"}
    return None


# ---------------------------------------------------------------------------
# Layer 2: inner LLM classifier
# ---------------------------------------------------------------------------

def _load_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        try:
            return config["models"]["providers"]["mnemo"]["apiKey"]
        except KeyError:
            pass
    raise RuntimeError("ANTHROPIC_API_KEY not set and no key found at ~/.openclaw/openclaw.json")


_CLASSIFIER_PROMPT = """You are an intent classifier for Trina, a GTD assistant. Your only task is intent classification.

The only valid output values are exactly these seven:
- capture: user wants to record a task, idea, or parking-lot item
- query_tasks: user wants to see their task list or next actions
- query_ideas: user wants to see their ideas
- query_parking_lot: user wants to see their parking lot
- review: user wants to run a GTD review pass
- calendar_read: user wants to read calendar events or schedule
- unknown: anything else -- greetings, out-of-scope, ambiguous

Return exactly: {"intent": "<value>"}
No prose. No explanation. No additional fields.

Correct examples:
"add a task to call the dentist" -> {"intent": "capture"}
"what tasks do I have this week?" -> {"intent": "query_tasks"}
"any ideas on the list?" -> {"intent": "query_ideas"}
"show me the parking lot" -> {"intent": "query_parking_lot"}
"let's do the weekly review" -> {"intent": "review"}
"what does my schedule look like tomorrow?" -> {"intent": "calendar_read"}

Incorrect (do not do this):
"add a task to call the dentist" -> {"intent": "capture", "task": "call the dentist"} WRONG: no parameters
"I think this is probably a task" -> this is a task WRONG: no prose
"schedule_read" -> WRONG: out-of-vocabulary

Continuity turns: short messages of 1-3 words ("yes", "no", "task", "Friday") are often
continuations of a prior question. If intent is not discernible, return {"intent": "unknown"}.

Never extract fields, entities, or parameters. Never invent vocabulary values. Never return prose.

Message: {user_message}"""


def _classify_llm(user_message: str, span) -> dict:
    """Return {intent, confidence, rationale} via inner LLM. Raises GTDError on exhaustion."""
    client = anthropic.Anthropic(
        api_key=_load_api_key(),
        base_url="https://api.anthropic.com",
    )
    prompt = _CLASSIFIER_PROMPT.replace("{user_message}", user_message)
    raw = ""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(1)
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
            parsed = json.loads(raw)
            intent = parsed.get("intent", "")
            if intent not in _VALID_INTENTS:
                raise ValueError(f"intent '{intent}' not in bounded vocabulary")
            return {"intent": intent, "confidence": "medium", "rationale": "llm"}
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            # Parse failures at temp=0 are deterministic; retrying produces the same bad output.
            span.set_status(StatusCode.ERROR, "classifier_invalid_response")
            span.set_attributes({
                "error.code": "classifier_invalid_response",
                "error.type": type(exc).__name__,
                "error.location": "_classify_llm",
                "error.context": "attempt=1",
            })
            raise GTDError("classifier_invalid_response", "LLM returned invalid response") from exc
        except Exception as exc:
            last_exc = exc
            continue

    # SDK/network exhaustion — all retries failed
    span.set_status(StatusCode.ERROR, "classifier_call_failed")
    span.set_attributes({
        "error.code": "classifier_call_failed",
        "error.type": type(last_exc).__name__,
        "error.location": "_classify_llm",
        "error.context": f"attempt={_MAX_RETRIES + 1}",
    })
    raise GTDError("classifier_call_failed", "LLM call failed after retries")


# ---------------------------------------------------------------------------
# Capability file read
# ---------------------------------------------------------------------------

def _read_capability(path: Path, span) -> tuple[str, float]:
    """Return (text, mtime). Sets span ERROR and raises GTDError on failure."""
    if not path.exists():
        span.set_status(StatusCode.ERROR, "capability_file_missing")
        span.set_attributes({
            "error.code": "capability_file_missing",
            "error.type": "FileNotFoundError",
            "error.location": "_read_capability",
            "error.context": f"intent={path.stem}",
        })
        raise GTDError("capability_file_missing", f"capability file not found: {path.name}")
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            text = fh.read()
        mtime = os.path.getmtime(str(path))
        return text, mtime
    except OSError as exc:
        span.set_status(StatusCode.ERROR, "capability_file_unreadable")
        span.set_attributes({
            "error.code": "capability_file_unreadable",
            "error.type": type(exc).__name__,
            "error.location": "_read_capability",
            "error.context": f"intent={path.stem}",
        })
        raise GTDError("capability_file_unreadable", f"cannot read capability file: {path.name}") from exc


# ---------------------------------------------------------------------------
# Continuity-turn detection
# ---------------------------------------------------------------------------

def _is_continuity(user_message: str) -> bool:
    return len(user_message.strip().split()) <= 3


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

class TurnStateResult(TypedDict):
    intent: str
    capability_prompt: str


def compute_turn_state(user_message: str) -> TurnStateResult:
    """Classify intent, read capability file, return {intent, capability_prompt}."""
    caps_dir = Path(os.environ.get("GTD_CAPABILITIES_DIR") or
                    str(Path(__file__).resolve().parent.parent / "capabilities"))

    with attach_parent_trace_context():
        with get_tracer(__name__).start_as_current_span("gtd.turn_state") as span:
            try:
                return _run(user_message, caps_dir, span)
            except GTDError as exc:
                err(exc)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, "internal_error")
                span.set_attributes({
                    "error.code": "internal_error",
                    "error.type": type(exc).__name__,
                    "error.location": "compute_turn_state",
                    "error.context": "unexpected",
                })
                err(GTDError("internal_error", "unexpected error in turn_state"))


def _run(user_message: str, caps_dir: Path, span) -> TurnStateResult:
    t0 = time.monotonic()

    # Layer 1: deterministic
    det = _classify_deterministic(user_message)
    if det:
        intent = det["intent"]
        classifier_strategy = "deterministic"
    else:
        # Layer 2: inner LLM
        llm_result = _classify_llm(user_message, span)
        intent = llm_result["intent"]
        classifier_strategy = "llm"

    classifier_latency_ms = round((time.monotonic() - t0) * 1000)
    continuity_turn = _is_continuity(user_message)
    capability_dispatched = intent in _TOOL_INTENTS

    span.set_attributes({
        "intent": intent,
        "capability_dispatched": capability_dispatched,
        "capability_file": f"capabilities/{intent}.md",
        "classifier_strategy": classifier_strategy,
        "classifier_latency_ms": classifier_latency_ms,
        "continuity_turn": continuity_turn,
    })

    cap_path = caps_dir / f"{intent}.md"
    capability_text, mtime = _read_capability(cap_path, span)
    span.set_attribute("capability_file_mtime", mtime)

    return TurnStateResult(intent=intent, capability_prompt=capability_text)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        raw = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        err(GTDError("invalid_input", f"invalid JSON input: {exc}"))
        return

    user_message = raw.get("user_message")
    if not isinstance(user_message, str):
        err(GTDError("invalid_input", "user_message must be a string"))
        return

    result = compute_turn_state(user_message)
    ok(result)


if __name__ == "__main__":
    main()
