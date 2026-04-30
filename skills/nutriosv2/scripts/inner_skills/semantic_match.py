"""semantic_match inner skill; skeleton stub for log_meal_items sub-step 1.

Implemented in sub-step 2. Body raises NotImplementedError.

retry_occurred is the retry indicator communicated back to log_meal_items as a
dataclass field. log_meal_items checks this flag to append a system-level
warning without parsing strings.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SemanticMatchResult:
    matches: list[str | None]
    retry_occurred: bool


def match_recipes(
    unmatched_items: list[str],
    recipe_names: list[str],
) -> SemanticMatchResult:
    raise NotImplementedError
