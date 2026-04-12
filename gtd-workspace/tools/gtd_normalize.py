"""Normalize raw captures into task/idea/parking_lot schema.

Detects explicit commands and classifies natural language input via
keyword and regex pattern matching. Never writes storage, invents
missing values, or calls any LLM.

Usage: python3 gtd_normalize.py '<raw_input>'
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Taxonomy — loaded from references/taxonomy.json (read-only at runtime)
# ---------------------------------------------------------------------------

_TAXONOMY_PATH = Path(__file__).parent.parent / "references" / "taxonomy.json"
_taxonomy = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))

KNOWN_CONTEXTS: frozenset[str] = frozenset(_taxonomy["contexts"])
KNOWN_DOMAINS: frozenset[str] = frozenset(_taxonomy["idea_domains"])
KNOWN_AREAS: frozenset[str] = frozenset(_taxonomy["areas"])

EXPLICIT_COMMANDS: frozenset[str] = frozenset({
    "/task", "/idea", "/next", "/review", "/waiting",
    "/capture", "/start", "/help", "/settings", "/privacy",
})

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

_STRONG_BASE: float = 0.85
_WEAK_BASE: float = 0.60
_SCORE_STEP: float = 0.05
_STRONG_CAP: float = 0.98
_WEAK_CAP: float = 0.75
_CONFIDENCE_THRESHOLD: float = 0.6   # below this → needs_llm = True
_INTENT_THRESHOLD: float = 0.5       # below this → intent = "unknown"

_MAX_TITLE_LEN: int = 120

# ---------------------------------------------------------------------------
# Intent classification patterns
# ---------------------------------------------------------------------------

_TASK_PATTERNS_STRONG: list[re.Pattern] = [
    re.compile(r"\bremind me to\b", re.I),
    re.compile(r"\bi need to\b", re.I),
    re.compile(r"\bdon'?t forget to\b", re.I),
    re.compile(r"\bmake sure to\b", re.I),
    re.compile(r"\bneed to\b", re.I),
    re.compile(r"\bhave to\b", re.I),
    re.compile(r"\bmust\b", re.I),
]

# Broad catch: imperative verb at sentence start
_TASK_PATTERNS_WEAK: list[re.Pattern] = [
    re.compile(
        r"^(fix|call|email|send|update|check|prepare|write|buy|"
        r"schedule|book|contact|submit|complete|finish|draft|order|"
        r"confirm|cancel|reply|follow|review)\b",
        re.I,
    ),
    re.compile(r"^(urgent|critical|asap)\s*[:\-]\s*\w", re.I),
]

_IDEA_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*idea\s*[:\-]", re.I),
    re.compile(r"\bwhat if\b", re.I),
    re.compile(r"\bmaybe (we|i) should\b", re.I),
    re.compile(r"\bi'?ve been thinking (about|of)\b", re.I),
    re.compile(r"\bwhat about\b", re.I),
    re.compile(r"\bcould (we|i)\b", re.I),
    re.compile(r"\bwe should (consider|try|look into|explore)\b", re.I),
    re.compile(r"\bit might be (worth|good|interesting)\b", re.I),
]

_DELEGATION_PATTERNS: list[re.Pattern] = [
    # Negative lookbehind excludes question form "am i waiting on"
    re.compile(r"(?<![Aa]m [Ii] )\bwaiting (on|for)\b", re.I),
    re.compile(r"\bfollow[\s-]?up with\b", re.I),
    re.compile(r"\bask \w+ (about|for|to)\b", re.I),
    re.compile(r"\bdelegate (to|it to)\b", re.I),
    re.compile(r"\bchasing\b", re.I),
    re.compile(r"\bchase (up|down)\b", re.I),
    re.compile(r"\bowing me\b", re.I),
]

_QUERY_NEXT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwhat'?s next\b", re.I),
    re.compile(r"\bwhat should i do\b", re.I),
    re.compile(r"\bshow (my )?tasks?\b", re.I),
    re.compile(r"\bshow (my )?(next )?actions?\b", re.I),
    re.compile(r"\bwhat can i (do|work on)\b", re.I),
    re.compile(r"\bnext actions?\b", re.I),
]

_REVIEW_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(weekly |daily )?review\b", re.I),
    re.compile(r"\bshow (my )?review\b", re.I),
    re.compile(r"\bwhat'?s (stale|overdue)\b", re.I),
]

_QUERY_WAITING_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwhat am i waiting (on|for)\b", re.I),
    re.compile(r"\bwho owes me\b", re.I),
    re.compile(r"\bwaiting (list|items?)\b", re.I),
    re.compile(r"\bshow (my )?waiting\b", re.I),
]

# ---------------------------------------------------------------------------
# Field extraction patterns
# ---------------------------------------------------------------------------

_CONTEXT_PATTERN = re.compile(r"(@[\w-]+)")

_PRIORITY_MAP: list[tuple[str, re.Pattern]] = [
    ("critical", re.compile(r"\b(critical|asap|emergency|urgent)\b", re.I)),
    ("high",     re.compile(r"\b(high[\s-]priority|important|must do today)\b", re.I)),
    ("low",      re.compile(r"\b(low[\s-]priority|whenever|someday maybe)\b", re.I)),
]

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "ai-automation":        ["ai", "agent", "automation", "llm", "claude", "openai", "bot", "script", "automate"],
    "watch-business":       ["watch", "watches", "rolex", "tudor", "omega", "listing", "grailzee", "watchtrack", "auction"],
    "business-improvement": ["process", "workflow", "improve", "efficiency", "system", "optimize", "streamline"],
    "meetings-to-schedule": ["meet", "meeting", "call", "schedule", "sync", "catch up", "coffee"],
    "home-life":            ["home", "house", "grocery", "family", "kids", "garden", "chore"],
    "learning":             ["learn", "read", "study", "course", "book", "research", "understand"],
    "content":              ["write", "post", "publish", "blog", "article", "content", "video", "newsletter"],
}

_LEAD_IN_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*remind me to\s+", re.I),
    re.compile(r"^\s*i need to\s+", re.I),
    re.compile(r"^\s*don'?t forget to\s+", re.I),
    re.compile(r"^\s*make sure to\s+", re.I),
    re.compile(r"^\s*idea\s*[:\-]\s*", re.I),
    re.compile(r"^\s*(urgent|critical|asap)\s*[:\-]\s*", re.I),
]

_FILLER_PATTERN = re.compile(r"\b(uh|um|er|ah|you know|like|so)\b,?\s*", re.I)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_tier(hits: int, base: float, cap: float) -> float:
    return min(base + (hits - 1) * _SCORE_STEP, cap) if hits else 0.0


def _score_strong_weak(
    text: str,
    strong: list[re.Pattern],
    weak: list[re.Pattern],
) -> float:
    """Score with strong (0.85 base) and weak (0.60 base) pattern tiers."""
    strong_hits = sum(1 for p in strong if p.search(text))
    if strong_hits:
        return _score_tier(strong_hits, _STRONG_BASE, _STRONG_CAP)
    weak_hits = sum(1 for p in weak if p.search(text))
    return _score_tier(weak_hits, _WEAK_BASE, _WEAK_CAP)


def _score_patterns(text: str, patterns: list[re.Pattern]) -> float:
    """Score a flat pattern list; delegates to _score_strong_weak with no weak tier."""
    return _score_strong_weak(text, patterns, [])


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_context(text: str) -> str | None:
    """Return the first known @context found in text, lowercase, or None."""
    for m in _CONTEXT_PATTERN.findall(text):
        if m.lower() in KNOWN_CONTEXTS:
            return m.lower()
    return None


def _extract_priority(text: str) -> str:
    """Return 'critical', 'high', 'low', or 'normal'."""
    for priority, pattern in _PRIORITY_MAP:
        if pattern.search(text):
            return priority
    return "normal"


def _extract_domain(text: str) -> str | None:
    """Return the best-matching idea domain by keyword count, or None."""
    lower = text.lower()
    best_domain: str | None = None
    best_count = 0
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in lower)
        if count > best_count:
            best_count = count
            best_domain = domain
    return best_domain if best_count > 0 else None


def _extract_title(text: str) -> str | None:
    """Strip lead-ins, filler words, and @context markers; return a clean title."""
    cleaned = text
    for pattern in _LEAD_IN_PATTERNS:
        stripped = pattern.sub("", cleaned).strip()
        if stripped != cleaned.strip():
            cleaned = stripped
            break
    if not cleaned:
        return None
    cleaned = _FILLER_PATTERN.sub(" ", cleaned).strip()
    cleaned = _CONTEXT_PATTERN.sub("", cleaned).strip()
    cleaned = cleaned.strip(" .,")
    return cleaned[:_MAX_TITLE_LEN] if cleaned else None


def _compute_missing(intent: str, title: str | None, context_hint: str | None) -> list[str]:
    """Return required fields that appear to be missing for the given intent."""
    match intent:
        case "task_capture":
            return (["title"] if not title else []) + (["context"] if not context_hint else [])
        case "idea_capture":
            return ["title"] if not title else []
        case _:
            return []


# ---------------------------------------------------------------------------
# Result factory
# ---------------------------------------------------------------------------

def _result(
    status: str,
    intent: str,
    confidence: float,
    needs_llm: bool,
    title: str | None,
    context_hint: str | None,
    priority_hint: str | None,
    area_hint: str | None,
    missing: list[str],
) -> dict:
    return {
        "status": status,
        "intent": intent,
        "confidence": confidence,
        "needs_llm": needs_llm,
        "candidate": {
            "title": title,
            "context_hint": context_hint,
            "priority_hint": priority_hint,
            "area_hint": area_hint,
            "missing_fields": missing,
        },
    }


def _ok(
    intent: str,
    confidence: float,
    title: str | None,
    context_hint: str | None,
    priority_hint: str | None,
    area_hint: str | None,
    missing: list[str],
) -> dict:
    return _result("ok", intent, confidence, False, title, context_hint, priority_hint, area_hint, missing)


def _uncertain(text: str, missing_fields: list[str]) -> dict:
    title = text[:_MAX_TITLE_LEN].strip() if text else None
    return _result("uncertain", "unknown", 0.0, True, title, None, None, None, missing_fields)


def _system_command(intent: str) -> dict:
    return _ok(intent, 1.0, None, None, None, None, [])


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def _detect_command(text: str) -> str | None:
    lower = text.lower()
    return next(
        (cmd for cmd in EXPLICIT_COMMANDS
         if lower == cmd or lower.startswith(cmd + " ") or lower.startswith(cmd + "\n")),
        None,
    )


def _handle_command(command: str, text: str) -> dict:
    """Return a high-confidence result for an explicit command."""
    body = text[len(command):].strip()

    match command:
        case "/task" | "/idea":
            context_hint = _extract_context(body) if body else None
            priority_hint = _extract_priority(body) if body else "normal"
            title = _extract_title(body) if body else None
            if command == "/task":
                missing = (["title"] if not title else []) + (["context"] if not context_hint else [])
                return _ok("task_capture", 1.0, title, context_hint, priority_hint, None, missing)
            domain_hint = _extract_domain(body) if body else None
            missing = (["title"] if not title else []) + (["domain"] if not domain_hint else [])
            return _ok("idea_capture", 1.0, title, context_hint, priority_hint, domain_hint, missing)
        case "/capture":
            return _classify_natural_language(body) if body else _uncertain(text, ["intent", "title"])
        case "/next":
            return _system_command("query_next")
        case "/review":
            return _system_command("review_request")
        case "/waiting":
            return _system_command("query_waiting")
        case "/start":
            return _system_command("start")
        case "/help":
            return _system_command("help")
        case "/settings":
            return _system_command("settings")
        case "/privacy":
            return _system_command("privacy")
        case _:
            return _uncertain(text, ["intent"])


# ---------------------------------------------------------------------------
# Natural language classifier
# ---------------------------------------------------------------------------

def _classify_natural_language(text: str) -> dict:
    """Score all intent patterns and return the best match."""
    scores: dict[str, float] = {
        "task_capture":       _score_strong_weak(text, _TASK_PATTERNS_STRONG, _TASK_PATTERNS_WEAK),
        "idea_capture":       _score_patterns(text, _IDEA_PATTERNS),
        "delegation_capture": _score_patterns(text, _DELEGATION_PATTERNS),
        "query_next":         _score_patterns(text, _QUERY_NEXT_PATTERNS),
        "review_request":     _score_patterns(text, _REVIEW_PATTERNS),
        "query_waiting":      _score_patterns(text, _QUERY_WAITING_PATTERNS),
    }

    best_intent, confidence = max(scores.items(), key=lambda kv: kv[1])

    if confidence < _INTENT_THRESHOLD:
        best_intent = "unknown"
        confidence = 0.0

    needs_llm = confidence < _CONFIDENCE_THRESHOLD or best_intent == "unknown"
    status = "uncertain" if needs_llm else "ok"

    context_hint = _extract_context(text)
    priority_hint = _extract_priority(text)
    domain_hint = _extract_domain(text) if best_intent in ("idea_capture", "unknown") else None
    title = _extract_title(text)
    missing = _compute_missing(best_intent, title, context_hint)

    return _result(status, best_intent, round(confidence, 2), needs_llm, title, context_hint, priority_hint, domain_hint, missing)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize(raw_input: str) -> dict:
    """Classify intent and extract structured fields from raw text.

    Returns the normalizer output contract as specified in IMPLEMENTATION.md.
    Never writes storage, invents missing values, or calls any LLM.
    """
    text = raw_input.strip() if raw_input else ""

    if not text:
        return _uncertain(text, ["intent", "context", "title"])

    command = _detect_command(text)
    if command:
        return _handle_command(command, text)

    return _classify_natural_language(text)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gtd_normalize.py '<raw_input>'")
        sys.exit(1)
    result = normalize(sys.argv[1])
    print(json.dumps(result, indent=2))
