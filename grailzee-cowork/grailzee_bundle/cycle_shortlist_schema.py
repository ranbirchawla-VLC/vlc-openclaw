"""Hand-rolled validator for cycle_shortlist_v1.json schema and CSV payloads.

The canonical spec lives at ``grailzee-cowork/schema/cycle_shortlist_v1.json``.
This module implements two validation modes in pure Python with human-readable
error messages keyed by dotted path. The JSON Schema file is the reference for
external validation; this is the runtime validator.

Decision log:
- Hand-rolled rather than importing jsonschema; mirrors strategy_schema.py
  pattern. No non-stdlib dependencies; plugin must be self-contained.
- Two modes: schema-level (validate the schema JSON file itself) and CSV-level
  (validate a CSV against a schema file).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

CSV_VERSION = 1
SHAPE = "bucket_row"
COLUMN_REQUIRED_KEYS = ("name", "type", "nullable", "level")
VALID_TYPES = {"string", "integer", "number", "boolean"}
VALID_LEVELS = {"reference", "bucket", "trend", "metadata"}


class CycleShortlistValidationError(ValueError):
    """Raised when a schema file or CSV payload fails validation."""


def _fail(path: str, reason: str) -> None:
    raise CycleShortlistValidationError(f"{path}: {reason}")


# ─── Schema-level validation ──────────────────────────────────────────────────


def validate_schema_file(schema_path: Path | str) -> None:
    """Validate that a cycle_shortlist schema JSON file is well-formed.

    Checks: required top-level keys present, csv_version == 1, shape ==
    "bucket_row", columns is an array, each column entry has the four required
    keys. Raises ``CycleShortlistValidationError`` on first failure.
    """
    schema_path = Path(schema_path)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("$", f"schema file not found: {schema_path}")
    except json.JSONDecodeError as exc:
        _fail("$", f"schema file is not valid JSON: {exc}")

    if not isinstance(schema, dict):
        _fail("$", "schema must be a JSON object")

    for key in ("csv_version", "shape", "columns"):
        if key not in schema:
            _fail(f"$.{key}", f"required key {key!r} missing from schema file")

    if schema["csv_version"] != CSV_VERSION:
        _fail(
            "$.csv_version",
            f"must be {CSV_VERSION}, got {schema['csv_version']!r}",
        )

    if schema["shape"] != SHAPE:
        _fail(
            "$.shape",
            f"must be {SHAPE!r}, got {schema['shape']!r}",
        )

    columns = schema["columns"]
    if not isinstance(columns, list):
        _fail("$.columns", f"must be an array, got {type(columns).__name__}")

    for i, col in enumerate(columns):
        col_path = f"$.columns[{i}]"
        if not isinstance(col, dict):
            _fail(col_path, f"each column entry must be an object, got {type(col).__name__}")
        for req in COLUMN_REQUIRED_KEYS:
            if req not in col:
                _fail(col_path, f"missing required key {req!r}")
        if col.get("type") not in VALID_TYPES:
            _fail(f"{col_path}.type", f"must be one of {sorted(VALID_TYPES)!r}, got {col.get('type')!r}")
        if col.get("level") not in VALID_LEVELS:
            _fail(f"{col_path}.level", f"must be one of {sorted(VALID_LEVELS)!r}, got {col.get('level')!r}")
        if not isinstance(col.get("nullable"), bool):
            _fail(f"{col_path}.nullable", f"must be a boolean, got {type(col.get('nullable')).__name__}")


# ─── CSV-level validation ─────────────────────────────────────────────────────


def _check_type(value: str, col_type: str, path: str) -> None:
    """Validate a non-empty CSV cell string against a column type.

    ``string`` always passes. ``number`` must parse as float. ``integer``
    must parse as int (no decimal point allowed).
    """
    if col_type == "string":
        return
    if col_type == "number":
        try:
            float(value)
        except ValueError:
            _fail(path, f"expected number, got {value!r}")
    elif col_type == "integer":
        try:
            int_val = int(value)
            if str(int_val) != value.lstrip("+"):
                raise ValueError
        except ValueError:
            _fail(path, f"expected integer, got {value!r}")


def validate_csv(
    csv_path: Path | str,
    schema_path: Path | str,
) -> None:
    """Validate a cycle_shortlist CSV against a schema file.

    Checks:
    - Header row column names match schema columns in exact order.
    - Header column count matches schema column count.
    - First data row (if present): non-empty cells type-check; non-nullable
      columns must not be empty.

    Raises ``CycleShortlistValidationError`` with a dotted-path error
    message on first failure.
    """
    csv_path = Path(csv_path)
    schema_path = Path(schema_path)

    validate_schema_file(schema_path)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    columns: list[dict[str, Any]] = schema["columns"]

    try:
        raw_text = csv_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _fail("$", f"CSV file not found: {csv_path}")

    reader = csv.reader(raw_text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        _fail("$.header", "CSV file is empty (no header row)")

    if len(header) != len(columns):
        _fail(
            "$.header",
            f"expected {len(columns)} columns, got {len(header)}",
        )

    for i, (cell, col) in enumerate(zip(header, columns)):
        if cell != col["name"]:
            _fail(
                f"$.header[{i}]",
                f"expected column {col['name']!r}, got {cell!r}",
            )

    try:
        first_row = next(reader)
    except StopIteration:
        return

    if len(first_row) != len(columns):
        _fail(
            "$.rows[0]",
            f"expected {len(columns)} cells, got {len(first_row)}",
        )

    for cell, col in zip(first_row, columns):
        col_name = col["name"]
        row_path = f"$.rows[0].{col_name}"
        if cell == "":
            if not col["nullable"]:
                _fail(row_path, f"column is not nullable but cell is empty")
        else:
            _check_type(cell, col["type"], row_path)
