"""semantic_match inner skill; skeleton stub for log_meal_items sub-step 1.

Implemented in sub-step 2. Body raises NotImplementedError.

retry_occurred is the retry indicator communicated back to log_meal_items as a
dataclass field. log_meal_items checks this flag to append a system-level
warning without parsing strings.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path

import anthropic


_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0
_MAX_TOKENS = 4096  # ceiling for large recipe lists; output is N strings/nulls, not a single object

_PROMPT = """\
You are matching colloquial food references to a user's named recipes. For each item description, return either the exact name of a single matching recipe from the list, or null.

CRITICAL RULE — false-negative bias: return null whenever uncertain. A wrong match silently logs the wrong macros under an authoritative recipe; the user notices days later when their totals drift. A null routes the item to fresh estimation; the user gets approximately-right macros and can correct by re-logging or naming the recipe more distinctly. Null is the safe failure mode.

Match only when the user's description clearly names or paraphrases a specific recipe in the list. Do not match by category, cuisine, ingredient overlap, or general similarity.

MATCH:
- Recipe "Chicken Tikka Lunch Bowl"; description "my tikka lunch" -> "Chicken Tikka Lunch Bowl". Shorter form of the same recipe name.
- Recipe "Chicken Tikka Lunch Bowl"; description "tikka masala lunch" -> "Chicken Tikka Lunch Bowl". Slight variation, only one tikka recipe in list.
- Recipes "Chicken Tikka Lunch Bowl" and "Recovery Shake"; description "tikka lunch" -> "Chicken Tikka Lunch Bowl". The other recipe is unrelated.

DO NOT MATCH (return null):
- Recipe "Recovery Shake" only; description "tikka lunch" -> null. Not the same food. Do not match by "they are both items on the list."
- Recipe "Qdoba Chicken Bowl"; description "Chipotle chicken bowl" -> null. Different specific named entities; macros differ. The user named a Chipotle bowl, not the Qdoba recipe.
- Recipe "Pad Thai"; description "Thai noodles" -> null. Category reference, not a recipe reference.
- Recipes "Morning Protein Shake" and "Recovery Shake"; description "my shake" -> null. Two equally plausible matches; user owns the disambiguation.

INPUT
Recipes available:
{recipe_list}

Items to match:
{item_list}

OUTPUT: a JSON array, exactly one element per item, in input order. Each element is either the exact recipe name string from the recipes list (verbatim -- case, spacing, and punctuation must match) or null. No other fields. No commentary. No code fences.

Example output for three items:
["Chicken Tikka Lunch Bowl", null, null]\
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


def _build_prompt(unmatched_items: list[str], recipe_names: list[str]) -> str:
    recipe_list = "\n".join(f"- {name}" for name in recipe_names)
    item_list = "\n".join(f"{i + 1}. {desc}" for i, desc in enumerate(unmatched_items))
    return _PROMPT.format(recipe_list=recipe_list, item_list=item_list)


def _validate(raw_text: str, recipe_names: list[str], expected_length: int) -> list[str | None]:
    parsed = json.loads(raw_text)
    if not isinstance(parsed, list):
        raise ValueError(f"LLM returned non-array: {raw_text!r}")
    if len(parsed) != expected_length:
        raise ValueError(
            f"length mismatch: expected {expected_length}, got {len(parsed)}"
        )
    recipe_name_set = set(recipe_names)
    result: list[str | None] = []
    for element in parsed:
        if element is None:
            result.append(None)
        elif isinstance(element, str) and element in recipe_name_set:
            result.append(element)
        else:
            raise ValueError(
                f"element {element!r} is not a verbatim recipe name or null"
            )
    return result


@dataclass
class SemanticMatchResult:
    matches: list[str | None]
    retry_occurred: bool


def match_recipes(
    unmatched_items: list[str],
    recipe_names: list[str],
) -> SemanticMatchResult:
    if not unmatched_items:
        return SemanticMatchResult(matches=[], retry_occurred=False)
    if not recipe_names:
        return SemanticMatchResult(matches=[None] * len(unmatched_items), retry_occurred=False)

    client = anthropic.Anthropic(
        api_key=_load_api_key(),
        base_url="https://api.anthropic.com",
    )
    prompt = _build_prompt(unmatched_items, recipe_names)

    raw = _call_llm(client, prompt)
    try:
        matches = _validate(raw, recipe_names, len(unmatched_items))
        return SemanticMatchResult(matches=matches, retry_occurred=False)
    except (json.JSONDecodeError, ValueError):
        raw = _call_llm(client, prompt)
        try:
            matches = _validate(raw, recipe_names, len(unmatched_items))
            return SemanticMatchResult(matches=matches, retry_occurred=True)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(
                f"semantic_match: schema validation failed after retry: {e}; "
                f"last response: {raw!r}"
            ) from e
