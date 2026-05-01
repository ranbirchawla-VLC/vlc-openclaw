"""batch_estimate inner skill — estimates per-unit macros for a list of food descriptions.

Makes one Anthropic API call (claude-sonnet-4-6, temperature 0) with up to 3 retries on
schema failure, with a 1-second pause between attempts. retry_occurred is returned as a
dataclass field; log_meal_items appends a system-level warning when True.
"""

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic


_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0
_MAX_TOKENS = 1024  # 1-10 items x ~70 chars per macro object; comfortable ceiling without over-allocating

_MAX_RETRIES = 3
_REQUIRED_KEYS = frozenset({"calories", "protein_g", "fat_g", "carbs_g"})

_PROMPT = """\
You are estimating per-unit macronutrients for a list of food descriptions. For each description, return calories, protein in grams, fat in grams, and carbohydrates in grams for ONE UNIT of that food.

CRITICAL RULE — ignore quantifiers in the description. The portion math happens in Python after you return; your job is to estimate one unit only. If the description says "two eggs," return macros for one egg. If it says "half an avocado," return macros for one whole avocado. If it says "three slices of bread," return macros for one slice. The caller will scale.

If a description is genuinely ambiguous about what "one unit" means (e.g., "rice" could be a cup, a bowl, or a side), default to a typical single serving as commonly understood in U.S. nutritional reporting. Do not fail or return null on ambiguity; estimate the typical case.

Use your training knowledge of food composition. The user has accepted approximate accuracy as the design contract; precision-sensitive cases are routed to user-defined recipes upstream and will not reach you.

INPUT
Items to estimate:
{item_list}

OUTPUT: a JSON array, exactly one element per item, in input order. Each element is a JSON object with exactly these four keys: "calories", "protein_g", "fat_g", "carbs_g". All values are non-negative numbers (integers or floats). No other fields. No commentary. No code fences.

Example output for two items ("egg", "slice of whole wheat bread"):
[{"calories": 72, "protein_g": 6.3, "fat_g": 4.8, "carbs_g": 0.4}, {"calories": 80, "protein_g": 4.0, "fat_g": 1.0, "carbs_g": 14.0}]\
"""


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
    raise RuntimeError(
        "ANTHROPIC_API_KEY not set and no key found at ~/.openclaw/openclaw.json"
    )


def _call_llm(client: anthropic.Anthropic, prompt: str) -> str:
    resp = client.messages.create(
        model=_MODEL,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _build_prompt(descriptions: list[str]) -> str:
    item_list = "\n".join(f"{i + 1}. {desc}" for i, desc in enumerate(descriptions))
    return _PROMPT.replace("{item_list}", item_list)


def _validate(raw_text: str, expected_length: int) -> list[BaseMacroEstimate]:
    parsed = json.loads(raw_text)
    if not isinstance(parsed, list):
        raise ValueError(f"LLM returned non-array: {raw_text!r}")
    if len(parsed) != expected_length:
        raise ValueError(
            f"length mismatch: expected {expected_length}, got {len(parsed)}"
        )
    result: list[BaseMacroEstimate] = []
    for i, element in enumerate(parsed):
        if not isinstance(element, dict):
            raise ValueError(f"element {i} is not a dict: {element!r}")
        if set(element.keys()) != _REQUIRED_KEYS:
            raise ValueError(f"element {i} has wrong keys: {set(element.keys())!r}")
        macros: dict[str, int] = {}
        for key in _REQUIRED_KEYS:
            val = element[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"element {i} key {key!r} is not numeric: {val!r}")
            if val < 0:
                raise ValueError(f"element {i} key {key!r} is negative: {val}")
            macros[key] = round(val)
        result.append(BaseMacroEstimate(**macros))
    return result


@dataclass
class BaseMacroEstimate:
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    notes: str | None = None


@dataclass
class BatchEstimateResult:
    items: list[BaseMacroEstimate]
    retry_occurred: bool


def estimate_macros(descriptions: list[str]) -> BatchEstimateResult:
    if not descriptions:
        return BatchEstimateResult(items=[], retry_occurred=False)

    client = anthropic.Anthropic(
        api_key=_load_api_key(),
        base_url="https://api.anthropic.com",
    )
    prompt = _build_prompt(descriptions)
    raw = ""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            time.sleep(1)
        raw = _call_llm(client, prompt)
        try:
            items = _validate(raw, len(descriptions))
            return BatchEstimateResult(items=items, retry_occurred=attempt > 0)
        except (json.JSONDecodeError, ValueError) as e:
            last_exc = e

    raise ValueError(
        f"batch_estimate: schema validation failed after {_MAX_RETRIES} retries: {last_exc}; "
        f"last response: {raw!r}"
    ) from last_exc
