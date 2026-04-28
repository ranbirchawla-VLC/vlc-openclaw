"""estimate_macros: LLM-backed macro estimator from food description.

Usage: python3 estimate_macros.py '<json_args>'
"""

from __future__ import annotations
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Literal

sys.path.insert(0, os.path.dirname(__file__))
from common import err, ok

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

try:
    from opentelemetry import trace as _otel_trace
    _TRACER = _otel_trace.get_tracer(__name__)
except ImportError:
    _TRACER = None

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0
_MAX_TOKENS = 256

_SYSTEM_PROMPT = (
    "You are a nutrition data lookup tool. Return ONLY a valid JSON object; "
    "no prose, no markdown, no caveats.\n\n"
    "Given a food description, return exactly:\n"
    '{"calories": <int>, "protein_g": <float>, '
    '"fat_g": <float>, "carbs_g": <float>, '
    '"confidence": <"high"|"medium"|"low">}\n\n'
    "Rules:\n"
    "- calories: integer, rounded to nearest whole number\n"
    "- protein_g, fat_g, carbs_g: floats >= 0\n"
    "- confidence: 'high' for specific well-known foods; "
    "'medium' for reasonable guesses; 'low' for vague descriptions\n"
    "- Return ONLY the JSON object. No markdown fences. No explanation."
)


class _Input(BaseModel):
    model_config = ConfigDict(strict=True)
    description: str

    @field_validator("description")
    @classmethod
    def description_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        return v


class EstimateResult(BaseModel):
    calories: int
    protein_g: float
    fat_g: float
    carbs_g: float
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def all_non_negative(self) -> "EstimateResult":
        for field in ("calories", "protein_g", "fat_g", "carbs_g"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} must be >= 0, got {getattr(self, field)}")
        return self


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


def _call_llm(client: anthropic.Anthropic, description: str) -> str:
    resp = client.messages.create(
        model=_MODEL,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    return resp.content[0].text


def estimate_macros_from_description(description: str) -> dict:
    """Estimate macros from a natural-language food description via LLM.

    Returns dict: calories, protein_g, fat_g, carbs_g, confidence.
    Retries once on schema failure; raises ValueError if both attempts fail.
    """
    # base_url hardcoded to bypass the mnemo proxy, which has a body-read bug
    # with the current anthropic SDK version. The LLM tests already bypass mnemo
    # implicitly (no ANTHROPIC_BASE_URL in test env). When called as an OpenClaw
    # subprocess the gateway env sets ANTHROPIC_BASE_URL to the mnemo endpoint;
    # the explicit base_url here overrides that.
    client = anthropic.Anthropic(
        api_key=_load_api_key(),
        base_url="https://api.anthropic.com",
    )
    retried = False

    span_ctx = (
        _TRACER.start_as_current_span("meal.estimate_macros")
        if _TRACER is not None
        else nullcontext()
    )

    with span_ctx as span:
        raw = _call_llm(client, description)
        try:
            result = EstimateResult(**json.loads(raw))
        except (json.JSONDecodeError, ValidationError):
            retried = True
            raw = _call_llm(client, description)
            try:
                result = EstimateResult(**json.loads(raw))
            except (json.JSONDecodeError, ValidationError) as e:
                raise ValueError(
                    f"estimate_macros_from_description: schema validation failed after retry: {e}; "
                    f"last response: {raw!r}"
                ) from e

        if _TRACER is not None and span is not None:
            span.set_attribute("description_length", len(description))
            span.set_attribute("confidence", result.confidence)
            span.set_attribute("retried", retried)

    return result.model_dump()


def main() -> None:
    if len(sys.argv) < 2:
        err("missing args: expected JSON string as sys.argv[1]")
        return
    try:
        raw = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        err(f"invalid JSON args: {e}")
        return
    try:
        inp = _Input(**raw)
    except Exception as e:
        err(f"invalid input: {e}")
        return
    try:
        result = estimate_macros_from_description(inp.description)
    except ValueError as e:
        err(f"estimation failed: {e}")
        return
    except RuntimeError as e:
        err(f"configuration error: {e}")
        return
    except anthropic.AnthropicError as e:
        err(f"API error: {e}")
        return
    ok(result)


if __name__ == "__main__":
    main()
