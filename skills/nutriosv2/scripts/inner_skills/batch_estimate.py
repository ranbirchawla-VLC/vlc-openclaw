"""batch_estimate inner skill; skeleton stub for log_meal_items sub-step 1.

Implemented in sub-step 3. Body raises NotImplementedError.

retry_occurred is the retry indicator communicated back to log_meal_items as a
dataclass field. log_meal_items checks this flag to append a system-level
warning without parsing strings.
"""

from __future__ import annotations
from dataclasses import dataclass


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
    raise NotImplementedError
