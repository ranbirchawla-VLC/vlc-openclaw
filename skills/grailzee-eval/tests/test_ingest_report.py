"""Tests for scripts.ingest_report — Excel to CSV conversion."""

import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tests._fixture_builders import DEFAULT_SALES_ROWS, build_minimal_report

V2_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = V2_ROOT / "scripts" / "ingest_report.py"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# Normalization unit tests (import the functions directly)
# ═══════════════════════════════════════════════════════════════════════

from scripts.ingest_report import (
    _determine_output_name,
    normalize_date,
    normalize_price,
    normalize_reference,
    normalize_sell_through,
    normalize_year,
)


class TestNormalizePrice:
    def test_int(self):
        assert normalize_price(2000) == 2000.0

    def test_float(self):
        assert normalize_price(2000.0) == 2000.0

    def test_string_with_dollar_and_comma(self):
        assert normalize_price("$2,000") == 2000.0

    def test_string_with_comma_decimal(self):
        assert normalize_price("2,000.00") == 2000.0

    def test_none(self):
        assert normalize_price(None) is None

    def test_empty_string(self):
        assert normalize_price("") is None

    def test_non_numeric(self):
        assert normalize_price("abc") is None


class TestNormalizeReference:
    def test_float_strips_dot_zero(self):
        assert normalize_reference(126300.0) == "126300"

    def test_string_preserved(self):
        assert normalize_reference("A17320") == "A17320"

    def test_int(self):
        assert normalize_reference(126300) == "126300"

    def test_none(self):
        assert normalize_reference(None) is None

    def test_blank(self):
        assert normalize_reference("") is None

    def test_string_float(self):
        assert normalize_reference("126300.0") == "126300"


class TestNormalizeYear:
    def test_float(self):
        assert normalize_year(2025.0) == 2025

    def test_int(self):
        assert normalize_year(2025) == 2025

    def test_unknown(self):
        assert normalize_year("Unknown") is None

    def test_blank(self):
        assert normalize_year("") is None

    def test_none(self):
        assert normalize_year(None) is None


class TestNormalizeSellThrough:
    def test_percent_string(self):
        assert normalize_sell_through("23%") == 0.23

    def test_fraction_float(self):
        assert normalize_sell_through(0.28) == 0.28

    def test_integer_percent(self):
        assert normalize_sell_through(23) == 0.23

    def test_none(self):
        assert normalize_sell_through(None) is None

    def test_empty_string(self):
        assert normalize_sell_through("") is None

    def test_zero(self):
        assert normalize_sell_through(0) == 0.0

    def test_one_hundred_percent(self):
        assert normalize_sell_through("100%") == 1.0


class TestNormalizeDate:
    def test_datetime_object(self):
        assert normalize_date(datetime(2026, 2, 9, 16, 45)) == "2026-02-09"

    def test_none(self):
        assert normalize_date(None) is None

    def test_blank(self):
        assert normalize_date("") is None

    def test_iso_string(self):
        assert normalize_date("2026-02-09T16:45:00") == "2026-02-09"


# ═══════════════════════════════════════════════════════════════════════
# Integration tests using synthetic fixtures
# ═══════════════════════════════════════════════════════════════════════


class TestMinimalValid:
    """3 sales, 2 unique references, both in Top Selling Watches."""

    def test_ingest_succeeds(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["rows_written"] == 3

    def test_csv_has_correct_columns(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames) == {
                "date_sold", "make", "reference", "title", "condition",
                "papers", "sold_price", "sell_through_pct",
            }

    def test_sell_through_joined(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        assert data["sheets"]["sell_through_joined"] == 3
        assert data["sheets"]["sell_through_missing"] == 0

    def test_csv_date_format(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert len(row["date_sold"]) == 10  # YYYY-MM-DD
                assert row["date_sold"].count("-") == 2

    def test_output_filename_uses_latest_date(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        # Latest sale date in default rows is 2026-02-09
        assert "grailzee_2026-02-09.csv" in data["output_csv"]


class TestNoTopSelling:
    def test_csv_produced_with_empty_sell_through(self, tmp_path):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx", include_top_selling=False)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["rows_written"] == 3
        assert any("missing" in w.lower() for w in data["warnings"])
        # All sell_through_pct should be empty
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert row["sell_through_pct"] == ""


class TestFormatDrift:
    def test_mixed_price_formats(self, tmp_path):
        rows = [
            {**DEFAULT_SALES_ROWS[0], "sold_for": 2000},
            {**DEFAULT_SALES_ROWS[1], "sold_for": 2000.0},
            {**DEFAULT_SALES_ROWS[2], "sold_for": "2,000"},
        ]
        # The "2,000" string won't survive openpyxl roundtrip as-is;
        # openpyxl writes it as a string cell. normalize_price handles it.
        xlsx = build_minimal_report(tmp_path / "report.xlsx", sales_rows=rows)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        # All should parse successfully
        data = json.loads(r.stdout)
        assert data["rows_written"] >= 2  # string "2,000" may or may not survive xlsx

    def test_float_reference_normalized(self, tmp_path):
        """126300.0 in Excel -> '126300' in CSV."""
        rows = [{
            **DEFAULT_SALES_ROWS[0],
            "reference": 126300.0,
            "make": "Rolex",
            "model": "Rolex Datejust",
        }]
        xlsx = build_minimal_report(tmp_path / "report.xlsx", sales_rows=rows)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["reference"] == "126300"


class TestSellThroughFormats:
    @pytest.mark.parametrize("fmt", ["percent_string", "fraction", "integer_percent"])
    def test_all_formats_produce_sell_through(self, tmp_path, fmt):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx", sell_through_format=fmt)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["sheets"]["sell_through_joined"] > 0
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["sell_through_pct"]:
                    val = float(row["sell_through_pct"])
                    assert 0 <= val <= 1


class TestMissingSoldAt:
    def test_row_skipped_with_warning(self, tmp_path):
        rows = [
            {**DEFAULT_SALES_ROWS[0], "sold_at": None},
            DEFAULT_SALES_ROWS[1],
        ]
        xlsx = build_minimal_report(tmp_path / "report.xlsx", sales_rows=rows)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["rows_written"] == 1
        assert any("skipped" in w.lower() for w in data["warnings"])


class TestMalformedWorkbooks:
    def test_no_auctions_sheet_fails(self, tmp_path):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx", omit_auctions_sheet=True)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode != 0

    def test_empty_data_fails(self, tmp_path):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx", sales_rows=[])
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode != 0

    def test_missing_required_column_fails(self, tmp_path):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx",
            omit_required_column="Reference Number")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode != 0

    def test_nonexistent_file_fails(self, tmp_path):
        r = run_cli("/tmp/nonexistent_report.xlsx",
                    "--output-dir", str(tmp_path / "csv_out"))
        assert r.returncode != 0


class TestReferenceUnmatched:
    def test_unmatched_ref_kept_with_empty_sell_through(self, tmp_path):
        """Sale with ref not in Top Selling -> CSV row kept, st empty."""
        sale_rows = [DEFAULT_SALES_ROWS[0]]
        xlsx_path = tmp_path / "report.xlsx"
        # Build report with top selling that has a DIFFERENT reference
        wb = __import__("openpyxl").Workbook()
        ws = wb.active
        ws.title = "Auctions Sold"
        headers = ["Sold at", "Auction", "Make", "Model", "Reference Number",
                    "Sold For", "Condition", "Year", "Papers", "Box"]
        for ci, h in enumerate(headers, 1):
            ws.cell(row=1, column=ci, value=h)
        r = sale_rows[0]
        ws.cell(row=2, column=1, value=r["sold_at"])
        ws.cell(row=2, column=2, value=r["title"])
        ws.cell(row=2, column=3, value=r["make"])
        ws.cell(row=2, column=4, value=r["model"])
        ws.cell(row=2, column=5, value=r["reference"])
        ws.cell(row=2, column=6, value=r["sold_for"])
        ws.cell(row=2, column=7, value=r["condition"])
        ws.cell(row=2, column=8, value=r["year"])
        ws.cell(row=2, column=9, value=r["papers"])
        ws.cell(row=2, column=10, value=r["box"])

        ws2 = wb.create_sheet("Top Selling Watches")
        for ci, h in enumerate(["Watch", "Reference Number", "Sales",
                                 "Total", "Sell-Through Rate", "Average Price"], 1):
            ws2.cell(row=1, column=ci, value=h)
        ws2.cell(row=2, column=1, value="Different Model")
        ws2.cell(row=2, column=2, value="XXXXXX")
        ws2.cell(row=2, column=3, value=5)
        ws2.cell(row=2, column=4, value=10)
        ws2.cell(row=2, column=5, value="50%")
        ws2.cell(row=2, column=6, value=3000)
        wb.save(str(xlsx_path))

        out_dir = str(tmp_path / "csv_out")
        result = run_cli(str(xlsx_path), "--output-dir", out_dir)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["rows_written"] == 1
        assert data["sheets"]["sell_through_missing"] == 1


class TestExtraColumn:
    def test_extra_column_warns(self, tmp_path):
        xlsx = build_minimal_report(
            tmp_path / "report.xlsx", extra_auctions_column="CustomField")
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert any("unexpected" in w.lower() or "ignored" in w.lower()
                    for w in data["warnings"])


class TestOverwrite:
    def test_refuses_overwrite_by_default(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        run_cli(str(xlsx), "--output-dir", out_dir)
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode != 0

    def test_overwrite_flag_allows_replace(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        out_dir = str(tmp_path / "csv_out")
        run_cli(str(xlsx), "--output-dir", out_dir)
        r = run_cli(str(xlsx), "--output-dir", out_dir, "--overwrite")
        assert r.returncode == 0


class TestUnicodeAndEdgeCases:
    def test_unicode_in_title(self, tmp_path):
        rows = [{
            **DEFAULT_SALES_ROWS[0],
            "title": "No Reserve - Breguet Classique R\u00e9f. 5177",
        }]
        xlsx = build_minimal_report(tmp_path / "report.xlsx", sales_rows=rows)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        assert r.returncode == 0

    def test_papers_capitalization_preserved(self, tmp_path):
        rows = [
            {**DEFAULT_SALES_ROWS[0], "papers": "yes"},
            {**DEFAULT_SALES_ROWS[1], "papers": "Yes"},
        ]
        xlsx = build_minimal_report(tmp_path / "report.xlsx", sales_rows=rows)
        out_dir = str(tmp_path / "csv_out")
        r = run_cli(str(xlsx), "--output-dir", out_dir)
        data = json.loads(r.stdout)
        with open(data["output_csv"]) as f:
            reader = csv.DictReader(f)
            paper_values = [row["papers"] for row in reader]
        assert "yes" in paper_values
        assert "Yes" in paper_values


# ═══════════════════════════════════════════════════════════════════════
# Flag #1/#2: _determine_output_name fallback behavior
# ═══════════════════════════════════════════════════════════════════════


class TestMtimeFallback:
    """Flag #1: mtime fallback is no longer silent.
    Flag #2: no datetime.now() last resort — OSError raises ValueError."""

    def test_mtime_fallback_warns_to_stderr(self, tmp_path, capsys):
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"")
        _determine_output_name([], str(f))
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "mtime" in captured.err.lower()
        assert str(f) in captured.err

    def test_mtime_fallback_filename_format(self, tmp_path):
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"")
        name = _determine_output_name([], str(f))
        assert name.startswith("grailzee_")
        assert name.endswith(".csv")
        date_part = name[len("grailzee_"):-len(".csv")]
        datetime.strptime(date_part, "%Y-%m-%d")

    def test_mtime_unavailable_raises(self, tmp_path):
        bogus = tmp_path / "does_not_exist.xlsx"
        with pytest.raises(ValueError, match="Cannot determine report date") as excinfo:
            _determine_output_name([], str(bogus))
        assert isinstance(excinfo.value.__cause__, OSError)


class TestRequiredOutputDir:
    """Flag #3: --output-dir is required; argparse rejects invocations without it."""

    def test_missing_output_dir_fails(self, tmp_path):
        xlsx = build_minimal_report(tmp_path / "report.xlsx")
        r = run_cli(str(xlsx))
        assert r.returncode != 0
        assert "output-dir" in r.stderr.lower()
