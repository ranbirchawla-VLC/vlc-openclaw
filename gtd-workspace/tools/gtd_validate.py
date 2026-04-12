"""Validate candidate records against the GTD data contract.

No external dependencies. Validation is implemented directly against
the field specs derived from IMPLEMENTATION.md and the shared enums
in common.py. The JSON schemas in references/schemas/ serve as
documentation and can be used with jsonschema if added later.

Usage: python3 gtd_validate.py <record_type> <file.json>
Types: task, idea, parking_lot, profile
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from common import (
    Energy, IdeaStatus, ParkingLotReason, Priority, ProfileStatus,
    PromotionState, ReviewCadence, Source, TaskStatus,
)


# ---------------------------------------------------------------------------
# Field specification
# ---------------------------------------------------------------------------

@dataclass
class _F:
    """Field validation rule."""
    required: bool = True
    nullable: bool = False
    types: tuple[type, ...] = (str,)
    enum: frozenset | None = None
    min_length: int | None = None  # strings only
    _allowed_str: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        # Pre-compute the sorted display string for enum errors once at spec build time
        if self.enum is not None:
            object.__setattr__(self, "_allowed_str", ", ".join(sorted(self.enum)))


# Shorthand helpers
def _str(required: bool = True, nullable: bool = False, enum: frozenset | None = None, min_length: int | None = 1) -> _F:
    return _F(required=required, nullable=nullable, types=(str,), enum=enum, min_length=min_length)

def _str_null(required: bool = False, min_length: int | None = None) -> _F:
    return _F(required=required, nullable=True, types=(str,), min_length=min_length)

def _int_null(required: bool = False) -> _F:
    return _F(required=required, nullable=True, types=(int,))


# ---------------------------------------------------------------------------
# Record specs
# ---------------------------------------------------------------------------

# Enum frozensets — since enums are str,Enum their string values ARE the members
_SOURCE_ENUM          = frozenset(Source)
_TASK_STATUS_ENUM     = frozenset(TaskStatus)
_IDEA_STATUS_ENUM     = frozenset(IdeaStatus)
_PRIORITY_ENUM        = frozenset(Priority)
_ENERGY_ENUM          = frozenset(Energy)
_REVIEW_CADENCE_ENUM  = frozenset(ReviewCadence)
_PROMOTION_STATE_ENUM = frozenset(PromotionState)
_PARKING_LOT_REASON_ENUM = frozenset(ParkingLotReason)
_PROFILE_STATUS_ENUM  = frozenset(ProfileStatus)

_TASK_SPEC: dict[str, _F] = {
    "id":               _str(),
    "record_type":      _str(enum=frozenset({"task"})),
    "user_id":          _str(),
    "telegram_chat_id": _str(),
    "title":            _str(),
    "context":          _str(min_length=0),   # empty allowed; active-task rule enforces non-empty
    "area":             _str(min_length=0),
    "priority":         _str(enum=_PRIORITY_ENUM),
    "energy":           _str(enum=_ENERGY_ENUM),
    "duration_minutes": _int_null(),
    "status":           _str(enum=_TASK_STATUS_ENUM),
    "delegate_to":      _str_null(),
    "waiting_for":      _str_null(),
    "notes":            _str_null(),
    "source":           _str(enum=_SOURCE_ENUM),
    "created_at":       _str(),
    "updated_at":       _str(),
    "completed_at":     _str_null(),
}

_IDEA_SPEC: dict[str, _F] = {
    "id":               _str(),
    "record_type":      _str(enum=frozenset({"idea"})),
    "user_id":          _str(),
    "telegram_chat_id": _str(),
    "title":            _str(),
    "domain":           _str(),
    "context":          _str(),
    "review_cadence":   _str(enum=_REVIEW_CADENCE_ENUM),
    "promotion_state":  _str(enum=_PROMOTION_STATE_ENUM),
    "spark_note":       _str_null(),
    "status":           _str(enum=_IDEA_STATUS_ENUM),
    "source":           _str(enum=_SOURCE_ENUM),
    "created_at":       _str(),
    "updated_at":       _str(),
    "last_reviewed_at": _str_null(),
    "promoted_task_id": _str_null(),
}

_PARKING_LOT_SPEC: dict[str, _F] = {
    "id":               _str(),
    "record_type":      _str(enum=frozenset({"parking_lot"})),
    "user_id":          _str(),
    "telegram_chat_id": _str(),
    "raw_text":         _str(),
    "source":           _str(enum=_SOURCE_ENUM),
    "reason":           _str(enum=_PARKING_LOT_REASON_ENUM),
    # Parking-lot items reuse TaskStatus: active → not yet triaged, done/cancelled → resolved
    "status":           _str(enum=_TASK_STATUS_ENUM),
    "created_at":       _str(),
    "updated_at":       _str(),
}

_PROFILE_SPEC: dict[str, _F] = {
    "user_id":          _str(),
    "telegram_bot":     _str(),
    "telegram_chat_id": _str(),
    "display_name":     _str(),
    "status":           _str(enum=_PROFILE_STATUS_ENUM),
    "alexa_linked":     _F(required=True, nullable=False, types=(bool,)),
    "created_at":       _str(),
    "updated_at":       _str(),
}

_SPECS: dict[str, dict[str, _F]] = {
    "task":        _TASK_SPEC,
    "idea":        _IDEA_SPEC,
    "parking_lot": _PARKING_LOT_SPEC,
    "profile":     _PROFILE_SPEC,
}


# ---------------------------------------------------------------------------
# Schema-level validation
# ---------------------------------------------------------------------------

def _validate_fields(record: dict, spec: dict[str, _F]) -> list[dict]:
    errors: list[dict] = []

    for fname, rule in spec.items():
        present = fname in record
        value = record.get(fname)

        if not present:
            if rule.required:
                errors.append({"field": fname, "message": f"{fname} is required"})
            continue

        if value is None:
            if not rule.nullable:
                errors.append({"field": fname, "message": f"{fname} must not be null"})
            continue

        if not isinstance(value, rule.types):
            type_names = " or ".join(t.__name__ for t in rule.types)
            errors.append({"field": fname, "message": f"{fname} must be {type_names}"})
            continue

        if rule.enum is not None and value not in rule.enum:
            errors.append({"field": fname, "message": f"{fname} must be one of: {rule._allowed_str}"})

        if rule.min_length is not None and isinstance(value, str) and len(value) < rule.min_length:
            errors.append({"field": fname, "message": f"{fname} must not be empty"})

    return errors


# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------

def _task_rules(record: dict) -> list[dict]:
    errors: list[dict] = []
    status = record.get("status")

    if status == TaskStatus.active and not record.get("context", "").strip():
        errors.append({"field": "context", "message": "Actionable task requires context"})

    if record.get("completed_at") is not None and status != TaskStatus.done:
        errors.append({
            "field": "completed_at",
            "message": "completed_at must be null unless status is done",
        })

    if status == TaskStatus.delegated and not record.get("delegate_to"):
        errors.append({
            "field": "delegate_to",
            "message": "delegate_to is required when status is delegated",
        })

    if status == TaskStatus.waiting and not record.get("waiting_for"):
        errors.append({
            "field": "waiting_for",
            "message": "waiting_for is required when status is waiting",
        })

    return errors


def _ownership_rules(record: dict) -> list[dict]:
    """user_id and telegram_chat_id must be non-empty strings on every record type."""
    errors: list[dict] = []
    for fname in ("user_id", "telegram_chat_id"):
        val = record.get(fname)
        if isinstance(val, str) and not val.strip():
            errors.append({"field": fname, "message": f"{fname} must not be empty"})
    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(record: dict, record_type: str) -> dict:
    """Validate a record dict against the GTD data contract.

    Returns the validation output contract:
      { status, record_type, valid, errors: [{field, message}] }

    Never performs reasoning, makes workflow decisions, or calls any LLM.
    """
    spec = _SPECS.get(record_type)
    if spec is None:
        return {
            "status": "error",
            "record_type": record_type,
            "valid": False,
            "errors": [{"field": "record_type", "message": f"Unknown record_type: {record_type}"}],
        }

    errors = _validate_fields(record, spec)

    # Business rules run only when schema passes, so error messages are unambiguous
    if not errors:
        errors.extend(_ownership_rules(record))
        if record_type == "task":
            errors.extend(_task_rules(record))

    valid = not errors
    return {
        "status": "ok" if valid else "error",
        "record_type": record_type,
        "valid": valid,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: gtd_validate.py <record_type> <file.json>")
        sys.exit(1)
    record_type = sys.argv[1]
    path = Path(sys.argv[2])
    record = json.loads(path.read_text(encoding="utf-8"))
    result = validate(record, record_type)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
