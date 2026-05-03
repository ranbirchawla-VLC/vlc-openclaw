"""validate.py -- validate a GTD record against the data contract.

Internal module; imported by write.py and capture.py. Not registered with the gateway.
Returns ValidationResult (Pydantic model); never raises.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/
from otel_common import get_tracer

# Load tools/common.py by path to avoid conflict with scripts/common.py
_spec = importlib.util.spec_from_file_location(
    "_gtd_tools",
    Path(__file__).parent.parent.parent / "tools" / "common.py",
)
_tools = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_tools)  # type: ignore[union-attr]

Energy            = _tools.Energy
IdeaStatus        = _tools.IdeaStatus
ParkingLotReason  = _tools.ParkingLotReason
Priority          = _tools.Priority
ProfileStatus     = _tools.ProfileStatus
PromotionState    = _tools.PromotionState
ReviewCadence     = _tools.ReviewCadence
Source            = _tools.Source
TaskStatus        = _tools.TaskStatus


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FieldError(BaseModel):
    field:   str
    message: str


class ValidationResult(BaseModel):
    valid:       bool
    record_type: str
    errors:      list[FieldError]


# ---------------------------------------------------------------------------
# Field specification (identical to legacy gtd_validate.py)
# ---------------------------------------------------------------------------

@dataclass
class _F:
    required:    bool = True
    nullable:    bool = False
    types:       tuple = (str,)
    enum:        frozenset | None = None
    min_length:  int | None = None
    _allowed_str: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        if self.enum is not None:
            object.__setattr__(self, "_allowed_str", ", ".join(sorted(self.enum)))


def _str(required: bool = True, nullable: bool = False,
         enum: frozenset | None = None, min_length: int | None = 1) -> _F:
    return _F(required=required, nullable=nullable, types=(str,), enum=enum, min_length=min_length)


def _str_null(required: bool = False, min_length: int | None = None) -> _F:
    return _F(required=required, nullable=True, types=(str,), min_length=min_length)


def _int_null(required: bool = False) -> _F:
    return _F(required=required, nullable=True, types=(int,))


_SOURCE_ENUM           = frozenset(Source)
_TASK_STATUS_ENUM      = frozenset(TaskStatus)
_IDEA_STATUS_ENUM      = frozenset(IdeaStatus)
_PRIORITY_ENUM         = frozenset(Priority)
_ENERGY_ENUM           = frozenset(Energy)
_REVIEW_CADENCE_ENUM   = frozenset(ReviewCadence)
_PROMOTION_STATE_ENUM  = frozenset(PromotionState)
_PARKING_LOT_REASON_ENUM = frozenset(ParkingLotReason)
_PROFILE_STATUS_ENUM   = frozenset(ProfileStatus)

_TASK_SPEC: dict[str, _F] = {
    "id":               _str(),
    "record_type":      _str(enum=frozenset({"task"})),
    "user_id":          _str(),
    "telegram_chat_id": _str(),
    "title":            _str(),
    "context":          _str(min_length=0),
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
# Validation logic
# ---------------------------------------------------------------------------

def _validate_fields(record: dict, spec: dict[str, _F]) -> list[FieldError]:
    errors: list[FieldError] = []
    for fname, rule in spec.items():
        present = fname in record
        value = record.get(fname)
        if not present:
            if rule.required:
                errors.append(FieldError(field=fname, message=f"{fname} is required"))
            continue
        if value is None:
            if not rule.nullable:
                errors.append(FieldError(field=fname, message=f"{fname} must not be null"))
            continue
        if not isinstance(value, rule.types):
            type_names = " or ".join(t.__name__ for t in rule.types)
            errors.append(FieldError(field=fname, message=f"{fname} must be {type_names}"))
            continue
        if rule.enum is not None and value not in rule.enum:
            errors.append(FieldError(field=fname, message=f"{fname} must be one of: {rule._allowed_str}"))
        if rule.min_length is not None and isinstance(value, str) and len(value) < rule.min_length:
            errors.append(FieldError(field=fname, message=f"{fname} must not be empty"))
    return errors


def _task_rules(record: dict) -> list[FieldError]:
    errors: list[FieldError] = []
    status = record.get("status")
    if status == TaskStatus.active and not record.get("context", "").strip():
        errors.append(FieldError(field="context", message="Actionable task requires context"))
    if record.get("completed_at") is not None and status != TaskStatus.done:
        errors.append(FieldError(field="completed_at", message="completed_at must be null unless status is done"))
    if status == TaskStatus.delegated and not record.get("delegate_to"):
        errors.append(FieldError(field="delegate_to", message="delegate_to is required when status is delegated"))
    if status == TaskStatus.waiting and not record.get("waiting_for"):
        errors.append(FieldError(field="waiting_for", message="waiting_for is required when status is waiting"))
    return errors


def _ownership_rules(record: dict) -> list[FieldError]:
    errors: list[FieldError] = []
    for fname in ("user_id", "telegram_chat_id"):
        val = record.get(fname)
        if isinstance(val, str) and not val.strip():
            errors.append(FieldError(field=fname, message=f"{fname} must not be empty"))
    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(record_type: str, record: dict) -> ValidationResult:
    """Validate a record dict against the GTD data contract.

    Returns ValidationResult with valid=True and empty errors on success.
    Returns ValidationResult with valid=False and populated errors on failure.
    Never raises.
    """
    tracer = get_tracer("gtd.validate")
    with tracer.start_as_current_span("gtd.validate") as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("validate.record_type", record_type)

        spec = _SPECS.get(record_type)
        if spec is None:
            result = ValidationResult(
                valid=False,
                record_type=record_type,
                errors=[FieldError(field="record_type", message=f"Unknown record_type: {record_type}")],
            )
        else:
            errors = _validate_fields(record, spec)
            if not errors:
                errors.extend(_ownership_rules(record))
                if record_type == "task":
                    errors.extend(_task_rules(record))
            result = ValidationResult(valid=not errors, record_type=record_type, errors=errors)

        span.set_attribute("validate.valid", result.valid)
        span.set_attribute("validate.error_count", len(result.errors))
        return result
