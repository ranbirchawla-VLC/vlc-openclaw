"""validate.py -- validate a GTD record against the data contract.

Internal module; imported by write.py and capture.py. Not registered with the gateway.
Returns ValidationResult (Pydantic model); never raises.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))  # scripts/
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode

sys.path.insert(0, str(Path(__file__).parent))  # scripts/gtd/
from _tools_common import ProfileStatus


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
# Field specification
# ---------------------------------------------------------------------------

@dataclass
class _F:
    required:     bool = True
    nullable:     bool = False
    types:        tuple = (str,)
    enum:         frozenset | None = None
    min_length:   int | None = None
    _allowed_str: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        if self.enum is not None:
            self._allowed_str = ", ".join(sorted(self.enum))


def _str(required: bool = True, nullable: bool = False,
         enum: frozenset | None = None, min_length: int | None = 1) -> _F:
    return _F(required=required, nullable=nullable, types=(str,), enum=enum, min_length=min_length)


def _str_null(required: bool = False, min_length: int | None = None) -> _F:
    return _F(required=required, nullable=True, types=(str,), min_length=min_length)


_PROFILE_STATUS_ENUM = frozenset(ProfileStatus)

_TASK_SPEC: dict[str, _F] = {
    "id":          _str(),
    "record_type": _str(enum=frozenset({"task"})),
    "title":       _str(),
    "context":     _str(),
    "due_date":    _str_null(required=False),
    "waiting_for": _str_null(required=False),
    "created_at":  _str(),
}

_IDEA_SPEC: dict[str, _F] = {
    "id":          _str(),
    "record_type": _str(enum=frozenset({"idea"})),
    "title":       _str(),
    "created_at":  _str(),
}

_PARKING_LOT_SPEC: dict[str, _F] = {
    "id":          _str(),
    "record_type": _str(enum=frozenset({"parking_lot"})),
    "title":       _str(),
    "created_at":  _str(),
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
            result = ValidationResult(valid=not errors, record_type=record_type, errors=errors)

        span.set_attribute("validate.valid", result.valid)
        span.set_attribute("validate.error_count", len(result.errors))
        if not result.valid:
            span.set_status(Status(StatusCode.ERROR, f"{len(result.errors)} validation error(s)"))
        return result


if __name__ == "__main__":
    import json
    if len(sys.argv) < 3:
        print("Usage: python validate.py <record_type> <file.json>", file=sys.stderr)
        sys.exit(1)
    _record_type = sys.argv[1]
    _record = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    _result = validate(_record_type, _record)
    print(_result.model_dump_json(indent=2))
    sys.exit(0 if _result.valid else 1)
