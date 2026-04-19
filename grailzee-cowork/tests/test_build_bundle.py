"""Tests for grailzee_bundle.build_bundle (OUTBOUND)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from grailzee_bundle.build_bundle import (
    _detect_boundaries,
    _filename_timestamp,
    _parse_cycle_id,
    _quarter_of,
    _slice_ledger,
    build_outbound_bundle,
)
from _fixtures import (
    FAKE_CYCLE_ID,
    FAKE_PRIOR_CYCLE_ID,
    build_fake_grailzee_tree,
)


# ─── happy path ──────────────────────────────────────────────────────


def test_happy_path_builds_bundle_with_all_roles(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    now = datetime(2026, 4, 15, 13, 30, 45, 123456, tzinfo=timezone.utc)

    bundle = build_outbound_bundle(tmp_path, now=now)

    assert bundle.exists()
    assert bundle.parent == paths["bundles"]
    assert bundle.name == f"grailzee_outbound_{FAKE_CYCLE_ID}_20260415_133045_123456.zip"

    with zipfile.ZipFile(bundle, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["manifest_version"] == 1
        assert manifest["bundle_kind"] == "outbound"
        assert manifest["cycle_id"] == FAKE_CYCLE_ID
        assert manifest["source"] == "grailzee-cowork/build_bundle"
        assert manifest["generated_at"].endswith("Z")

        roles = {f["role"] for f in manifest["files"]}
        assert roles == {
            "analysis_cache",
            "cycle_focus_current",
            "monthly_goals",
            "quarterly_allocation",
            "trade_ledger_snippet",
            "sourcing_brief",
            "latest_report_csv",
        }

        # sha256 + size match each archived member
        for entry in manifest["files"]:
            data = zf.read(entry["path"])
            assert len(data) == entry["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_bundle_filename_uses_microsecond_precision(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    a = datetime(2026, 4, 15, 13, 30, 45, 111111, tzinfo=timezone.utc)
    b = datetime(2026, 4, 15, 13, 30, 45, 222222, tzinfo=timezone.utc)
    ba = build_outbound_bundle(tmp_path, now=a)
    bb = build_outbound_bundle(tmp_path, now=b)
    assert ba != bb
    assert ba.exists() and bb.exists()


def test_bundle_written_to_bundles_dir_by_default(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    bundle = build_outbound_bundle(tmp_path)
    assert bundle.parent == paths["bundles"]
    assert paths["bundles"].name == "bundles"
    assert paths["bundles"].parent == tmp_path


def test_output_dir_override_respected(tmp_path):
    build_fake_grailzee_tree(tmp_path)
    custom = tmp_path / "alt_bundles_location"
    bundle = build_outbound_bundle(tmp_path, output_dir=custom)
    assert bundle.parent == custom
    assert custom.exists()


# ─── ledger slicing ─────────────────────────────────────────────────


def test_ledger_snippet_filters_to_current_cycle(tmp_path):
    ledger_rows = [
        {"cycle_id": FAKE_CYCLE_ID, "reference": "79830RB", "net_profit": "340", "roi_pct": "14.5"},
        {"cycle_id": FAKE_PRIOR_CYCLE_ID, "reference": "210.30", "net_profit": "800", "roi_pct": "22.0"},
        {"cycle_id": FAKE_CYCLE_ID, "reference": "124060", "net_profit": "950", "roi_pct": "30.0"},
    ]
    build_fake_grailzee_tree(tmp_path, ledger_rows=ledger_rows)
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        snippet = zf.read("trade_ledger_snippet.csv").decode("utf-8")
    lines = [ln for ln in snippet.splitlines() if ln]
    # header + 2 matching rows (prior-cycle row excluded)
    assert lines[0].startswith("cycle_id,")
    assert len(lines) == 3
    assert FAKE_PRIOR_CYCLE_ID not in snippet


def test_slice_ledger_rejects_missing_cycle_id_column(tmp_path):
    ledger = tmp_path / "bad_ledger.csv"
    ledger.write_text("reference,net_profit\n79830RB,340\n")
    with pytest.raises(ValueError, match="cycle_id"):
        _slice_ledger(ledger, FAKE_CYCLE_ID)


def test_slice_ledger_rejects_empty_file(tmp_path):
    ledger = tmp_path / "empty_ledger.csv"
    ledger.write_text("")
    with pytest.raises(ValueError, match="no header row"):
        _slice_ledger(ledger, FAKE_CYCLE_ID)


# ─── report csv selection ──────────────────────────────────────────


def test_latest_report_by_lexical_desc_of_iso_date(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    # default fixtures include 2026-04-15 and 2026-04-02 — newest wins
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        report_entry = next(f for f in manifest["files"] if f["role"] == "latest_report_csv")
    assert report_entry["path"].endswith("grailzee_2026-04-15.csv")


def test_missing_reports_dir_raises(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    # wipe the reports_csv directory
    for p in paths["reports_csv"].iterdir():
        p.unlink()
    paths["reports_csv"].rmdir()
    with pytest.raises(FileNotFoundError, match="reports_csv"):
        build_outbound_bundle(tmp_path)


def test_empty_reports_dir_raises(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    for p in paths["reports_csv"].iterdir():
        p.unlink()
    with pytest.raises(FileNotFoundError, match="grailzee_YYYY-MM-DD"):
        build_outbound_bundle(tmp_path)


# ─── boundary detection ────────────────────────────────────────────


def test_no_run_history_both_boundaries_false(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    paths["run_history"].unlink()
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": False, "quarter_boundary": False}


def test_only_current_cycle_in_history_both_false(tmp_path):
    # build_fake_grailzee_tree default: run_history contains only current
    build_fake_grailzee_tree(tmp_path, with_boundary=False)
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": False, "quarter_boundary": False}


def test_prior_cycle_in_different_quarter_both_true(tmp_path):
    # 2026-03 (Q1) → 2026-04 (Q2): month AND quarter boundary
    build_fake_grailzee_tree(tmp_path, with_boundary=True)
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": True, "quarter_boundary": True}


def test_prior_cycle_within_same_quarter_only_month_boundary(tmp_path):
    # 2026-04 (current) vs 2026-05 (prior) — same quarter, different month
    paths = build_fake_grailzee_tree(
        tmp_path,
        cycle_id="cycle_2026-05",
        run_history={
            "runs": [
                {"cycle_id": "cycle_2026-04", "generated_at": "2026-04-10T00:00:00Z"},
                {"cycle_id": "cycle_2026-05", "generated_at": "2026-05-10T00:00:00Z"},
            ]
        },
        cache={
            "schema_version": 2,
            "cycle_id": "cycle_2026-05",
            "generated_at": "2026-05-15T12:00:00Z",
            "references": {},
        },
        cycle_focus={"cycle_id": "cycle_2026-05"},
        brief={"cycle_id": "cycle_2026-05", "headline": "", "sections": []},
    )
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": True, "quarter_boundary": False}


def test_boundary_anchor_skips_current_cycle_entries(tmp_path):
    """Most recent history entry equals current cycle; anchor must skip
    to the next-older DIFFERENT entry to detect the boundary."""
    build_fake_grailzee_tree(
        tmp_path,
        run_history={
            "runs": [
                {"cycle_id": FAKE_PRIOR_CYCLE_ID, "generated_at": "2026-03-18T00:00:00Z"},
                {"cycle_id": FAKE_CYCLE_ID, "generated_at": "2026-04-10T00:00:00Z"},
                {"cycle_id": FAKE_CYCLE_ID, "generated_at": "2026-04-12T00:00:00Z"},
            ]
        },
    )
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    # anchor = cycle_2026-03 (Q1); current = cycle_2026-04 (Q2)
    assert manifest["scope"] == {"month_boundary": True, "quarter_boundary": True}


def test_malformed_run_history_degrades_gracefully(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    paths["run_history"].write_text("not json {")
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": False, "quarter_boundary": False}


# ─── required inputs ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "key,label",
    [
        ("cache", "analysis cache"),
        ("cycle_focus", "cycle_focus"),
        ("monthly_goals", "monthly_goals"),
        ("quarterly_allocation", "quarterly_allocation"),
        ("brief", "sourcing_brief"),
    ],
)
def test_missing_required_input_raises(tmp_path, key, label):
    paths = build_fake_grailzee_tree(tmp_path)
    paths[key].unlink()
    with pytest.raises(FileNotFoundError, match=label):
        build_outbound_bundle(tmp_path)


def test_missing_cycle_id_in_cache_raises(tmp_path):
    paths = build_fake_grailzee_tree(
        tmp_path,
        cache={"schema_version": 2, "references": {}},  # no cycle_id
    )
    with pytest.raises(ValueError, match="cycle_id"):
        build_outbound_bundle(tmp_path)


def test_tmp_file_cleaned_on_failure(tmp_path):
    paths = build_fake_grailzee_tree(tmp_path)
    paths["brief"].unlink()  # trigger FileNotFoundError mid-build
    with pytest.raises(FileNotFoundError):
        build_outbound_bundle(tmp_path)
    stray_tmps = list(paths["bundles"].glob("*.tmp"))
    assert stray_tmps == []


# ─── helper unit tests ─────────────────────────────────────────────


def test_parse_cycle_id_happy():
    assert _parse_cycle_id("cycle_2026-04") == (2026, 4)


def test_parse_cycle_id_malformed():
    with pytest.raises(ValueError):
        _parse_cycle_id("2026-04")


def test_quarter_of():
    assert _quarter_of(1) == 1
    assert _quarter_of(3) == 1
    assert _quarter_of(4) == 2
    assert _quarter_of(12) == 4


def test_filename_timestamp_naive_dt_treated_as_utc():
    naive = datetime(2026, 4, 15, 13, 30, 45, 123456)
    aware = datetime(2026, 4, 15, 13, 30, 45, 123456, tzinfo=timezone.utc)
    assert _filename_timestamp(naive) == _filename_timestamp(aware)


def test_detect_boundaries_missing_file():
    assert _detect_boundaries("cycle_2026-04", Path("/nonexistent/xyz.json")) == {
        "month_boundary": False,
        "quarter_boundary": False,
    }
