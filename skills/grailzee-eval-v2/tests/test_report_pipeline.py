"""Tests for scripts.report_pipeline; ingest + glob + analyze wrapper.

Phase 19.5. The wrapper's own logic is the ingest call, the glob, and the
trend_window slice; the four tests below cover those three behaviors plus
propagation of ingest failures. Span emission is not unit-tested (matches
the existing precedent in test_run_analysis.py, which does not assert on
its 12 orchestrator spans either).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts import report_pipeline
from tests._fixture_builders import build_minimal_report

V2_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = V2_ROOT / "tests" / "fixtures"
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")
FIXTURE_CSVS = [
    FIXTURES / "grailzee_2026-04-06.csv",
    FIXTURES / "grailzee_2026-03-23.csv",
    FIXTURES / "grailzee_2026-03-09.csv",
]


def _seed_csv_dir(tmp_path: Path, count: int = 3) -> Path:
    """Copy `count` fixture CSVs (newest first) into a tmp csv_dir."""
    csv_dir = tmp_path / "reports_csv"
    csv_dir.mkdir()
    for src in FIXTURE_CSVS[:count]:
        shutil.copy2(src, csv_dir / src.name)
    return csv_dir


def _common_kwargs(tmp_path: Path, csv_dir: Path) -> dict:
    output = tmp_path / "output"
    output.mkdir()
    ledger = tmp_path / "trade_ledger.csv"
    ledger.write_text("date_closed,cycle_id,brand,reference,account,buy_price,sell_price\n")
    return {
        "output_folder": str(output),
        "csv_dir": str(csv_dir),
        "ledger_path": str(ledger),
        "cache_path": str(tmp_path / "state" / "analysis_cache.json"),
        "backup_path": str(tmp_path / "backup"),
        "name_cache_path": NAME_CACHE,
        "cycle_focus_path": str(tmp_path / "no_focus.json"),
    }


class TestHappyPath:
    def test_ingest_glob_analyze_end_to_end(self, tmp_path):
        """Real workbook + 3 existing CSVs: returns well-formed dict."""
        from datetime import datetime as _dt

        csv_dir = _seed_csv_dir(tmp_path, count=3)
        xlsx = tmp_path / "input.xlsx"
        # Pin sale dates to 2026-04-20 — guaranteed distinct from the
        # seeded fixture dates (03-09/03-23/04-06), so ingest never
        # collides with a FileExistsError.
        rows = [
            {
                "sold_at": _dt(2026, 4, 20, 12, 0, 0),
                "title": "Test 79830RB",
                "make": "Tudor",
                "model": "Tudor Black Bay GMT",
                "reference": "79830RB",
                "sold_for": 3200,
                "condition": "Very Good",
                "year": 2020,
                "papers": "Yes",
                "box": "Yes",
            },
        ]
        build_minimal_report(xlsx, sales_rows=rows)

        kwargs = _common_kwargs(tmp_path, csv_dir)
        result = report_pipeline.run_pipeline(str(xlsx), **kwargs)

        assert set(result.keys()) == {"summary_path", "unnamed", "cycle_id"}
        assert Path(result["summary_path"]).exists()
        assert result["cycle_id"].startswith("cycle_")
        csv_files = sorted(csv_dir.glob("grailzee_*.csv"))
        assert len(csv_files) == 4
        assert (csv_dir / "grailzee_2026-04-20.csv").exists()


class TestEmptyGlob:
    def test_raises_with_dir_and_pattern(self, tmp_path, monkeypatch):
        """csv_dir is empty after ingest -> ValueError names dir + pattern."""
        csv_dir = tmp_path / "reports_csv"
        csv_dir.mkdir()  # empty

        def _fake_ingest(input_path, output_dir, overwrite=False):
            return {
                "output_csv": "/dev/null/not-a-real-path.csv",
                "rows_written": 0,
                "sheets": {},
                "warnings": [],
            }

        monkeypatch.setattr(report_pipeline.ingest_report, "ingest", _fake_ingest)

        xlsx = tmp_path / "input.xlsx"
        xlsx.write_bytes(b"unused")

        kwargs = _common_kwargs(tmp_path, csv_dir)
        with pytest.raises(ValueError) as excinfo:
            report_pipeline.run_pipeline(str(xlsx), **kwargs)
        msg = str(excinfo.value)
        assert str(csv_dir) in msg
        assert "grailzee_*.csv" in msg


class TestIngestFailurePropagates:
    def test_non_xlsx_input_raises(self, tmp_path):
        """Ingest failure (wrong file extension) propagates unchanged.

        openpyxl raises InvalidFileException for a non-.xlsx input.
        The wrapper must propagate it, not swallow or rewrap it.
        """
        from openpyxl.utils.exceptions import InvalidFileException

        csv_dir = _seed_csv_dir(tmp_path, count=1)
        bad = tmp_path / "not-an-xlsx.txt"
        bad.write_text("this is not an Excel workbook")

        kwargs = _common_kwargs(tmp_path, csv_dir)
        with pytest.raises(InvalidFileException):
            report_pipeline.run_pipeline(str(bad), **kwargs)


class TestTrendWindow:
    def test_slice_respects_trend_window(self, tmp_path, monkeypatch):
        """trend_window=2 -> only 2 newest CSVs reach run_analysis."""
        csv_dir = _seed_csv_dir(tmp_path, count=3)

        # Stub ingest so we control the CSV set exactly (no extra file added).
        def _fake_ingest(input_path, output_dir, overwrite=False):
            return {
                "output_csv": str(csv_dir / FIXTURE_CSVS[0].name),
                "rows_written": 0,
                "sheets": {},
                "warnings": [],
            }

        captured: dict = {}

        def _fake_run_analysis(csv_paths, output_folder, **kw):
            captured["csv_paths"] = list(csv_paths)
            return {
                "summary_path": str(tmp_path / "summary.md"),
                "unnamed": [],
                "cycle_id": "cycle_2026-08",
            }

        monkeypatch.setattr(report_pipeline.ingest_report, "ingest", _fake_ingest)
        monkeypatch.setattr(
            report_pipeline.run_analysis, "run_analysis", _fake_run_analysis,
        )

        xlsx = tmp_path / "input.xlsx"
        xlsx.write_bytes(b"unused")
        kwargs = _common_kwargs(tmp_path, csv_dir)
        report_pipeline.run_pipeline(str(xlsx), trend_window=2, **kwargs)

        assert len(captured["csv_paths"]) == 2
        # Newest first
        assert captured["csv_paths"][0].endswith("grailzee_2026-04-06.csv")
        assert captured["csv_paths"][1].endswith("grailzee_2026-03-23.csv")
