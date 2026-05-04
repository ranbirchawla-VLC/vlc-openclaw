"""validate.py -- validate GTD records against submission and storage contracts.

Internal module; imported by write.py and capture.py. Not registered with gateway.
Single source of truth for D-F error code vocabulary.

Two public functions:
  validate_submission(record_type, record) -- checks LLM-supplied fields only
  validate_storage(record_type, record)   -- checks all storage fields (post-stamp)

Both return ValidationResult; never raise.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))  # scripts/
from otel_common import get_tracer
from opentelemetry.trace import Status, StatusCode


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class FieldError(BaseModel):
    field:   str
    message: str


class ValidationResult(BaseModel):
    valid:       bool
    record_type: str
    code:        str           # D-F error code; "" when valid=True
    errors:      list[FieldError]


# ---------------------------------------------------------------------------
# NonEmptyStr — enforces Q5: source and telegram_chat_id must be non-empty
# ---------------------------------------------------------------------------

NonEmptyStr = Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# Pydantic models per record_type × contract
# ---------------------------------------------------------------------------

class TaskSubmission(BaseModel):
    record_type: Literal["task"]
    title:       NonEmptyStr
    context:     str | None = None
    project:     str | None = None
    priority:    str | None = None
    waiting_for: str | None = None
    due_date:    str | None = None
    notes:       str | None = None


class TaskStorage(TaskSubmission):
    id:               str
    status:           Literal["open", "completed"]
    created_at:       str
    updated_at:       str
    last_reviewed:    str | None = None
    completed_at:     str | None = None
    source:           NonEmptyStr
    telegram_chat_id: NonEmptyStr


class IdeaSubmission(BaseModel):
    record_type: Literal["idea"]
    title:       NonEmptyStr
    content:     NonEmptyStr
    topic:       str | None = None


class IdeaStorage(IdeaSubmission):
    id:               str
    status:           Literal["open", "completed"]
    created_at:       str
    updated_at:       str
    last_reviewed:    str | None = None
    completed_at:     str | None = None
    source:           NonEmptyStr
    telegram_chat_id: NonEmptyStr


class ParkingLotSubmission(BaseModel):
    record_type: Literal["parking_lot"]
    content:     NonEmptyStr
    reason:      str | None = None


class ParkingLotStorage(ParkingLotSubmission):
    id:               str
    status:           Literal["open"]      # widened in 2d
    created_at:       str
    updated_at:       str
    last_reviewed:    str | None = None
    completed_at:     str | None = None
    source:           NonEmptyStr
    telegram_chat_id: NonEmptyStr


_SUBMISSION_MODELS: dict[str, type[BaseModel]] = {
    "task":        TaskSubmission,
    "idea":        IdeaSubmission,
    "parking_lot": ParkingLotSubmission,
}

_STORAGE_MODELS: dict[str, type[BaseModel]] = {
    "task":        TaskStorage,
    "idea":        IdeaStorage,
    "parking_lot": ParkingLotStorage,
}


# ---------------------------------------------------------------------------
# Internal validation engine
# ---------------------------------------------------------------------------

def _run_validate(
    record_type: str,
    record: dict,
    model_map: dict[str, type[BaseModel]],
    code_on_error: str,
    span_name: str,
) -> ValidationResult:
    tracer = get_tracer(span_name)
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("agent.id", "gtd")
        span.set_attribute("validate.record_type", record_type)

        model = model_map.get(record_type)
        if model is None:
            result = ValidationResult(
                valid=False,
                record_type=record_type,
                code="unknown_record_type",
                errors=[FieldError(
                    field="record_type",
                    message=f"Unknown record_type: {record_type!r}",
                )],
            )
        else:
            try:
                model.model_validate(record)
                result = ValidationResult(
                    valid=True, record_type=record_type, code="", errors=[],
                )
            except ValidationError as exc:
                errors = [
                    FieldError(field=str(e["loc"][-1]), message=e["msg"])
                    for e in exc.errors()
                ]
                result = ValidationResult(
                    valid=False, record_type=record_type,
                    code=code_on_error, errors=errors,
                )

        span.set_attribute("validate.valid", result.valid)
        span.set_attribute("validate.error_count", len(result.errors))
        if not result.valid:
            span.set_status(Status(StatusCode.ERROR, result.code))
        return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_submission(record_type: str, record: dict) -> ValidationResult:
    """Validate LLM-supplied fields against the submission contract.

    Code on failure: submission_invalid, or unknown_record_type.
    Never raises.
    """
    return _run_validate(
        record_type, record, _SUBMISSION_MODELS,
        "submission_invalid", "gtd.validate_submission",
    )


def validate_storage(record_type: str, record: dict) -> ValidationResult:
    """Validate a fully-stamped record against the storage contract.

    Code on failure: missing_required_field, or unknown_record_type.
    Never raises.
    """
    return _run_validate(
        record_type, record, _STORAGE_MODELS,
        "missing_required_field", "gtd.validate_storage",
    )


if __name__ == "__main__":
    import json
    if len(sys.argv) < 3:
        print("Usage: python validate.py <record_type> <file.json>", file=sys.stderr)
        sys.exit(1)
    _record_type = sys.argv[1]
    _record = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    _result = validate_storage(_record_type, _record)
    print(_result.model_dump_json(indent=2))
    sys.exit(0 if _result.valid else 1)
