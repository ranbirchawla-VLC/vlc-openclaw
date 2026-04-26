"""Tests for grailzee_bundle.cycle_shortlist_schema.

Coverage:
- Schema-level validation: required keys, shape const, column entry shape.
- CSV-level validation: header order/names, type checking on first data row,
  nullable enforcement, header-only CSV.
- Error messages use dotted paths.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from grailzee_bundle.cycle_shortlist_schema import (
    CycleShortlistValidationError,
    validate_schema_file,
    validate_csv,
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "cycle_shortlist_v1.json"


# ─── helpers ─────────────────────────────────────────────────────────────────


def _minimal_schema(columns: list[dict] | None = None) -> dict:
    return {
        "csv_version": 1,
        "shape": "bucket_row",
        "columns": columns if columns is not None else [],
    }


def _col(name: str, type_: str = "string", nullable: bool = True, level: str = "bucket") -> dict:
    return {"name": name, "type": type_, "nullable": nullable, "level": level}


def _write_schema(tmp_path: Path, schema: dict) -> Path:
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(schema))
    return p


def _write_csv(tmp_path: Path, rows: list[list[str]], name: str = "shortlist.csv") -> Path:
    p = tmp_path / name
    with open(p, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)
    return p


# ─── schema-level: validate_schema_file ──────────────────────────────────────


class TestValidateSchemaFile:
    def test_canonical_schema_file_passes(self) -> None:
        validate_schema_file(SCHEMA_PATH)

    def test_minimal_valid_schema_passes(self, tmp_path: Path) -> None:
        p = _write_schema(tmp_path, _minimal_schema())
        validate_schema_file(p)

    def test_missing_csv_version_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        del schema["csv_version"]
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="csv_version"):
            validate_schema_file(p)

    def test_missing_shape_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        del schema["shape"]
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="shape"):
            validate_schema_file(p)

    def test_missing_columns_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        del schema["columns"]
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="columns"):
            validate_schema_file(p)

    def test_wrong_shape_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        schema["shape"] = "reference_row"
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="shape"):
            validate_schema_file(p)

    def test_wrong_csv_version_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        schema["csv_version"] = 2
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="csv_version"):
            validate_schema_file(p)

    def test_columns_not_array_rejected(self, tmp_path: Path) -> None:
        schema = _minimal_schema()
        schema["columns"] = {}
        p = _write_schema(tmp_path, schema)
        with pytest.raises(CycleShortlistValidationError, match="columns"):
            validate_schema_file(p)

    def test_column_entry_missing_name_rejected(self, tmp_path: Path) -> None:
        col = _col("brand")
        del col["name"]
        p = _write_schema(tmp_path, _minimal_schema([col]))
        with pytest.raises(CycleShortlistValidationError, match=r"columns\[0\]"):
            validate_schema_file(p)

    def test_column_entry_missing_type_rejected(self, tmp_path: Path) -> None:
        col = _col("brand")
        del col["type"]
        p = _write_schema(tmp_path, _minimal_schema([col]))
        with pytest.raises(CycleShortlistValidationError, match=r"columns\[0\]"):
            validate_schema_file(p)

    def test_column_entry_missing_nullable_rejected(self, tmp_path: Path) -> None:
        col = _col("brand")
        del col["nullable"]
        p = _write_schema(tmp_path, _minimal_schema([col]))
        with pytest.raises(CycleShortlistValidationError, match=r"columns\[0\]"):
            validate_schema_file(p)

    def test_column_entry_missing_level_rejected(self, tmp_path: Path) -> None:
        col = _col("brand")
        del col["level"]
        p = _write_schema(tmp_path, _minimal_schema([col]))
        with pytest.raises(CycleShortlistValidationError, match=r"columns\[0\]"):
            validate_schema_file(p)

    def test_schema_path_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises((CycleShortlistValidationError, FileNotFoundError)):
            validate_schema_file(tmp_path / "nonexistent.json")


# ─── csv-level: validate_csv ─────────────────────────────────────────────────


def _schema_with_cols(*cols: dict) -> dict:
    return _minimal_schema(list(cols))


class TestValidateCsvHeader:
    def test_correct_header_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"), _col("signal"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand", "reference", "signal"], ["Tudor", "79830RB", "Strong"]])
        validate_csv(cp, sp)

    def test_wrong_column_name_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand", "ref"], ["Tudor", "79830RB"]])
        with pytest.raises(CycleShortlistValidationError, match=r"header\[1\]"):
            validate_csv(cp, sp)

    def test_wrong_column_order_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["reference", "brand"], ["79830RB", "Tudor"]])
        with pytest.raises(CycleShortlistValidationError, match=r"header\[0\]"):
            validate_csv(cp, sp)

    def test_missing_column_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"), _col("signal"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand", "reference"], ["Tudor", "79830RB"]])
        with pytest.raises(CycleShortlistValidationError, match="header"):
            validate_csv(cp, sp)

    def test_extra_column_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand", "reference", "extra"], ["Tudor", "79830RB", "x"]])
        with pytest.raises(CycleShortlistValidationError, match="header"):
            validate_csv(cp, sp)

    def test_header_only_csv_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"), _col("reference"))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand", "reference"]])
        validate_csv(cp, sp)


class TestValidateCsvTypes:
    def test_number_column_with_valid_float_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("median", type_="number", nullable=True))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["median"], ["3550.0"]])
        validate_csv(cp, sp)

    def test_number_column_with_integer_string_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("median", type_="number", nullable=True))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["median"], ["3550"]])
        validate_csv(cp, sp)

    def test_number_column_with_non_numeric_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("median", type_="number", nullable=True))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["median"], ["not_a_number"]])
        with pytest.raises(CycleShortlistValidationError, match=r"rows\[0\]\.median"):
            validate_csv(cp, sp)

    def test_integer_column_with_valid_int_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("volume", type_="integer", nullable=False))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["volume"], ["30"]])
        validate_csv(cp, sp)

    def test_integer_column_with_float_string_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("volume", type_="integer", nullable=False))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["volume"], ["30.5"]])
        with pytest.raises(CycleShortlistValidationError, match=r"rows\[0\]\.volume"):
            validate_csv(cp, sp)

    def test_integer_column_with_non_numeric_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("volume", type_="integer", nullable=False))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["volume"], ["abc"]])
        with pytest.raises(CycleShortlistValidationError, match=r"rows\[0\]\.volume"):
            validate_csv(cp, sp)

    def test_string_column_always_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand", type_="string", nullable=False))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["brand"], ["Tudor"]])
        validate_csv(cp, sp)


class TestValidateCsvNullability:
    def test_nullable_column_empty_cell_passes(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("median", type_="number", nullable=True))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["median"], [""]])
        validate_csv(cp, sp)

    def test_non_nullable_column_empty_cell_rejected(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("signal", type_="string", nullable=False))
        sp = _write_schema(tmp_path, schema)
        cp = _write_csv(tmp_path, [["signal"], [""]])
        with pytest.raises(CycleShortlistValidationError, match=r"rows\[0\]\.signal"):
            validate_csv(cp, sp)

    def test_csv_path_not_found_raises(self, tmp_path: Path) -> None:
        schema = _schema_with_cols(_col("brand"))
        sp = _write_schema(tmp_path, schema)
        with pytest.raises((CycleShortlistValidationError, FileNotFoundError)):
            validate_csv(tmp_path / "nonexistent.csv", sp)
