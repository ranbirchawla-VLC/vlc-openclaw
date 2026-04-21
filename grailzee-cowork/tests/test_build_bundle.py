"""Tests for grailzee_bundle.build_bundle (OUTBOUND)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from grailzee_bundle.build_bundle import (
    MAX_PREVIOUS_CYCLE_LOOKBACK,
    PREVIOUS_OUTCOME_ARCNAME,
    PREVIOUS_OUTCOME_META_ARCNAME,
    _detect_boundaries,
    _filename_timestamp,
    _parse_cycle_id,
    _quarter_of,
    _read_full_ledger,
    build_outbound_bundle,
    resolve_previous_cycle_outcome,
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
            # A.5: renamed from cycle_focus_current to match analyzer-native
            # naming; archive name is cycle_focus.json.
            "cycle_focus",
            "monthly_goals",
            "quarterly_allocation",
            "trade_ledger",
            "sourcing_brief",
            "latest_report_csv",
            # A.5: three workspace-state configs bundled alongside Drive
            # files so strategy sessions see the full config surface.
            "analyzer_config",
            "brand_floors",
            "sourcing_rules",
            # A.7: meta file is always bundled — carries source_cycle_id:null
            # when no prior cycle has trade data, as in this fixture's tree.
            "previous_cycle_outcome_meta",
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


# ─── full ledger bundling (Phase A.8) ───────────────────────────────


def test_bundled_ledger_matches_source_verbatim(tmp_path):
    """Bundled trade_ledger.csv is byte-identical to state/trade_ledger.csv.

    Phase A.8 replaced the cycle-scoped slice with a pass-through read;
    no filtering, no rewriting of CSV quoting. The bundle consumer
    (strategist) sees exactly what's on disk.
    """
    paths = build_fake_grailzee_tree(tmp_path)
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        bundled = zf.read("trade_ledger.csv")
    assert bundled == paths["ledger"].read_bytes()


def test_bundle_ledger_includes_all_cycles(tmp_path):
    """Populate a ledger spanning multiple cycles; bundle for any target
    cycle; assert every row is present.
    """
    ledger_rows = [
        {"cycle_id": FAKE_PRIOR_CYCLE_ID, "reference": "210.30", "net_profit": "800", "roi_pct": "22.0"},
        {"cycle_id": FAKE_CYCLE_ID, "reference": "79830RB", "net_profit": "340", "roi_pct": "14.5"},
        {"cycle_id": FAKE_CYCLE_ID, "reference": "124060", "net_profit": "950", "roi_pct": "30.0"},
        {"cycle_id": "cycle_2026-02", "reference": "116610LN", "net_profit": "1200", "roi_pct": "18.0"},
    ]
    build_fake_grailzee_tree(tmp_path, ledger_rows=ledger_rows)
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        bundled = zf.read("trade_ledger.csv").decode("utf-8")
    lines = [ln for ln in bundled.splitlines() if ln]
    # header + 4 rows across three distinct cycles
    assert lines[0].startswith("cycle_id,")
    assert len(lines) == 5
    # Every cycle_id the fixture seeded must survive into the bundle
    assert FAKE_PRIOR_CYCLE_ID in bundled
    assert FAKE_CYCLE_ID in bundled
    assert "cycle_2026-02" in bundled


def test_bundle_ledger_empty_ledger_bundles_header_only(tmp_path):
    """Header-only ledger (first deployment, no closes yet) passes through
    to the bundle as a header-only CSV. No filtering, no synthetic rows.
    """
    build_fake_grailzee_tree(tmp_path, ledger_rows=[])
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        bundled = zf.read("trade_ledger.csv").decode("utf-8")
    lines = [ln for ln in bundled.splitlines() if ln]
    assert len(lines) == 1
    assert lines[0].startswith("cycle_id,")


def test_read_full_ledger_returns_bytes_verbatim(tmp_path):
    """Unit test: _read_full_ledger is a byte-exact pass-through read."""
    ledger = tmp_path / "ledger.csv"
    content = b"cycle_id,reference,net_profit\ncycle_2026-04,79830RB,340\n"
    ledger.write_bytes(content)
    assert _read_full_ledger(ledger) == content


def test_read_full_ledger_missing_file_raises(tmp_path):
    """Unit test: missing ledger raises FileNotFoundError with path."""
    ledger = tmp_path / "nonexistent.csv"
    with pytest.raises(FileNotFoundError, match="trade ledger"):
        _read_full_ledger(ledger)


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
    # cycle_2026-06 starts Mar 16 (Q1); cycle_2026-08 starts Apr 13 (Q2).
    # Crossing biweekly cycles that span the quarter boundary. Previous
    # version of this test used cycle_2026-03 -> cycle_2026-04 assuming
    # NN == month; that's the A.6 bug — biweekly cycles 03 and 04 both
    # start in February.
    build_fake_grailzee_tree(
        tmp_path,
        cycle_id="cycle_2026-08",
        run_history={
            "runs": [
                {"cycle_id": "cycle_2026-06", "generated_at": "2026-03-18T00:00:00Z"},
                {"cycle_id": "cycle_2026-08", "generated_at": "2026-04-14T00:00:00Z"},
            ]
        },
        cache={
            "schema_version": 2,
            "cycle_id": "cycle_2026-08",
            "generated_at": "2026-04-14T12:00:00Z",
            "references": {},
        },
        cycle_focus={"cycle_id": "cycle_2026-08"},
        brief={"cycle_id": "cycle_2026-08", "headline": "", "sections": []},
    )
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["scope"] == {"month_boundary": True, "quarter_boundary": True}


def test_prior_cycle_within_same_quarter_only_month_boundary(tmp_path):
    # cycle_2026-04 starts Feb 16 (Q1); cycle_2026-05 starts Mar 2 (Q1).
    # Feb -> Mar = month boundary, same quarter. Unlike the quarter-
    # boundary test above, this pair was accidentally correct under the
    # A.6 bug and stays correct under the fix.
    paths = build_fake_grailzee_tree(
        tmp_path,
        cycle_id="cycle_2026-05",
        run_history={
            "runs": [
                {"cycle_id": "cycle_2026-04", "generated_at": "2026-02-16T00:00:00Z"},
                {"cycle_id": "cycle_2026-05", "generated_at": "2026-03-02T00:00:00Z"},
            ]
        },
        cache={
            "schema_version": 2,
            "cycle_id": "cycle_2026-05",
            "generated_at": "2026-03-02T12:00:00Z",
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
    to the next-older DIFFERENT entry to detect the boundary.

    Uses the cycle_2026-06 (Mar start, Q1) -> cycle_2026-08 (Apr start,
    Q2) pair so the boundary is both month and quarter under the correct
    biweekly semantics."""
    build_fake_grailzee_tree(
        tmp_path,
        cycle_id="cycle_2026-08",
        run_history={
            "runs": [
                {"cycle_id": "cycle_2026-06", "generated_at": "2026-03-18T00:00:00Z"},
                {"cycle_id": "cycle_2026-08", "generated_at": "2026-04-14T00:00:00Z"},
                {"cycle_id": "cycle_2026-08", "generated_at": "2026-04-16T00:00:00Z"},
            ]
        },
        cache={
            "schema_version": 2,
            "cycle_id": "cycle_2026-08",
            "generated_at": "2026-04-14T12:00:00Z",
            "references": {},
        },
        cycle_focus={"cycle_id": "cycle_2026-08"},
        brief={"cycle_id": "cycle_2026-08", "headline": "", "sections": []},
    )
    bundle = build_outbound_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    # anchor = cycle_2026-06 (Mar start, Q1); current = cycle_2026-08 (Apr start, Q2)
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
    """Second tuple element is the biweekly cycle counter (01-26+), not
    a calendar month. A.6 fix: docstring and downstream consumers now
    treat NN as cycle_num."""
    assert _parse_cycle_id("cycle_2026-04") == (2026, 4)


def test_parse_cycle_id_malformed():
    with pytest.raises(ValueError):
        _parse_cycle_id("2026-04")


# ─── A.6 regression: biweekly-as-month bug ─────────────────────────


from grailzee_bundle.build_bundle import _cycle_calendar_position  # noqa: E402


class TestCycleIdBiweeklySemantics:
    """A.6 regression suite. Before the fix, _parse_cycle_id claimed to
    return (year, month) and _detect_boundaries compared NN as a month
    index. Because biweekly cycles drift relative to month boundaries,
    every boundary flag was wrong. Tests cover both sides of the fix:
    NN in the 1-12 range (misparsed as a month under the bug) and the
    13-26 range (produced invalid months like Q5 under the bug)."""

    def test_parse_cycle_id_13_through_26_returns_cycle_num(self):
        """Cycles 13-26 parse cleanly under the fix. Pre-fix,
        `_quarter_of` on these produced Q5..Q9, which are not real
        quarters."""
        for nn in range(13, 27):
            year, cycle_num = _parse_cycle_id(f"cycle_2026-{nn:02d}")
            assert (year, cycle_num) == (2026, nn)

    def test_parse_cycle_id_1_through_12_returns_cycle_num(self):
        """Cycles 1-12 parse to their cycle number, not to any month."""
        for nn in range(1, 13):
            year, cycle_num = _parse_cycle_id(f"cycle_2026-{nn:02d}")
            assert (year, cycle_num) == (2026, nn)

    def test_cycle_calendar_position_maps_to_start_date(self):
        """Calendar position anchors on the cycle's start date. Spot
        checks several cycles in 2026 to confirm month/quarter map from
        cycle_date_range, not from NN."""
        # cycle_2026-01 starts Jan 5 (Q1).
        assert _cycle_calendar_position("cycle_2026-01") == (2026, 1, 1)
        # cycle_2026-06 starts Mar 16 (Q1).
        assert _cycle_calendar_position("cycle_2026-06") == (2026, 3, 1)
        # cycle_2026-07 spans Mar 30 - Apr 12. Start = March = Q1. This
        # is the load-bearing assertion: the bug called cycle_2026-07
        # "July/Q3".
        assert _cycle_calendar_position("cycle_2026-07") == (2026, 3, 1)
        # cycle_2026-08 starts Apr 13 = April = Q2.
        assert _cycle_calendar_position("cycle_2026-08") == (2026, 4, 2)
        # cycle_2026-13 starts ~Jun 22 = Q2. Bug would have returned
        # month=13 (invalid) or quarter=5.
        year, month, quarter = _cycle_calendar_position("cycle_2026-13")
        assert (year, month, quarter) == (2026, 6, 2)
        # cycle_2026-26 falls in late Dec = Q4.
        year, month, quarter = _cycle_calendar_position("cycle_2026-26")
        assert year == 2026
        assert quarter == 4

    def test_month_spanning_cycle_anchors_on_start(self):
        """Cycle_2026-07 (Mar 30 - Apr 12) anchors to March. If its
        prior was cycle_2026-06 (also March), no month or quarter
        boundary."""
        y1, m1, q1 = _cycle_calendar_position("cycle_2026-06")
        y2, m2, q2 = _cycle_calendar_position("cycle_2026-07")
        assert (y1, m1, q1) == (y2, m2, q2)

    def test_detect_boundaries_for_cycles_past_12(self, tmp_path):
        """End-to-end: a cycle pair in the 13-26 range produces correct
        boundary flags. cycle_2026-13 (Jun start, Q2) -> cycle_2026-14
        (Jul start, Q3) is both a month and a quarter boundary."""
        build_fake_grailzee_tree(
            tmp_path,
            cycle_id="cycle_2026-14",
            run_history={
                "runs": [
                    {"cycle_id": "cycle_2026-13", "generated_at": "2026-06-22T00:00:00Z"},
                    {"cycle_id": "cycle_2026-14", "generated_at": "2026-07-06T00:00:00Z"},
                ]
            },
            cache={
                "schema_version": 2,
                "cycle_id": "cycle_2026-14",
                "generated_at": "2026-07-06T12:00:00Z",
                "references": {},
            },
            cycle_focus={"cycle_id": "cycle_2026-14"},
            brief={"cycle_id": "cycle_2026-14", "headline": "", "sections": []},
        )
        bundle = build_outbound_bundle(tmp_path)
        with zipfile.ZipFile(bundle, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["scope"] == {"month_boundary": True, "quarter_boundary": True}

    def test_detect_boundaries_adjacent_same_month_cycles(self, tmp_path):
        """cycle_2026-03 (Feb 2) -> cycle_2026-04 (Feb 16): same Feb,
        same Q1. No boundaries. Under the A.6 bug this would have
        reported quarter boundary=True (NN 3 -> 4, Q1 -> Q2)."""
        build_fake_grailzee_tree(
            tmp_path,
            cycle_id="cycle_2026-04",
            run_history={
                "runs": [
                    {"cycle_id": "cycle_2026-03", "generated_at": "2026-02-02T00:00:00Z"},
                    {"cycle_id": "cycle_2026-04", "generated_at": "2026-02-16T00:00:00Z"},
                ]
            },
            cache={
                "schema_version": 2,
                "cycle_id": "cycle_2026-04",
                "generated_at": "2026-02-16T12:00:00Z",
                "references": {},
            },
            cycle_focus={"cycle_id": "cycle_2026-04"},
            brief={"cycle_id": "cycle_2026-04", "headline": "", "sections": []},
        )
        bundle = build_outbound_bundle(tmp_path)
        with zipfile.ZipFile(bundle, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["scope"] == {"month_boundary": False, "quarter_boundary": False}


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


# ─── Phase A.7: resolve_previous_cycle_outcome ─────────────────────

def _write_outcome(state: Path, cycle_id: str, trades: list) -> Path:
    """Write a minimal cycle_outcome_<id>.json for tests."""
    path = state / f"cycle_outcome_{cycle_id}.json"
    path.write_text(json.dumps({
        "cycle_id": cycle_id,
        "date_range": {"start": "2026-01-01", "end": "2026-01-14"},
        "trades": trades,
        "summary": {
            "total_trades": len(trades),
            "profitable": sum(1 for t in trades if t.get("net", 0) > 0),
            "avg_roi": 0.0,
            "total_net": sum(t.get("net", 0) for t in trades),
        },
        "cycle_focus": {},
    }))
    return path


class TestResolvePreviousCycleOutcome:
    """Phase A.7: resolver used by the bundle builder to find the most
    recent cycle outcome with real trade data before the planning target.
    """

    def test_resolve_previous_cycle_finds_adjacent(self, tmp_path):
        """Target cycle_2026-07; cycle_2026-06 has trades → returns cycle_2026-06."""
        state = tmp_path / "state"
        state.mkdir()
        _write_outcome(state, "cycle_2026-06", [
            {"date": "2026-03-24", "reference": "79830RB", "net": 551.0},
        ])
        path, meta = resolve_previous_cycle_outcome(state, "cycle_2026-07")
        assert path == state / "cycle_outcome_cycle_2026-06.json"
        assert meta["source_cycle_id"] == "cycle_2026-06"
        assert meta["target_planning_cycle_id"] == "cycle_2026-07"
        assert meta["skipped_cycles"] == []
        assert "cycle_2026-06" in meta["resolution_note"]

    def test_resolve_previous_cycle_skips_empty(self, tmp_path):
        """Target cycle_2026-08; cycle_2026-07 empty, cycle_2026-06 has trades
        → returns cycle_2026-06 with skipped=[cycle_2026-07].
        """
        state = tmp_path / "state"
        state.mkdir()
        _write_outcome(state, "cycle_2026-07", [])  # empty trades array
        _write_outcome(state, "cycle_2026-06", [
            {"date": "2026-03-25", "reference": "M28500-0003", "net": 401.0},
        ])
        path, meta = resolve_previous_cycle_outcome(state, "cycle_2026-08")
        assert path == state / "cycle_outcome_cycle_2026-06.json"
        assert meta["source_cycle_id"] == "cycle_2026-06"
        assert meta["skipped_cycles"] == ["cycle_2026-07"]
        assert "skipped" in meta["resolution_note"]

    def test_resolve_previous_cycle_missing_file_not_counted_as_skip(self, tmp_path):
        """Missing outcome files are not listed in skipped_cycles — only
        existing-but-empty files are."""
        state = tmp_path / "state"
        state.mkdir()
        # cycle_2026-07 file DOES NOT exist; cycle_2026-06 has trades
        _write_outcome(state, "cycle_2026-06", [
            {"date": "2026-03-24", "reference": "116900", "net": 200.0},
        ])
        path, meta = resolve_previous_cycle_outcome(state, "cycle_2026-08")
        assert meta["source_cycle_id"] == "cycle_2026-06"
        assert meta["skipped_cycles"] == []  # missing file is not a skip

    def test_resolve_previous_cycle_no_history(self, tmp_path):
        """No outcome files exist anywhere → returns None + null source."""
        state = tmp_path / "state"
        state.mkdir()
        path, meta = resolve_previous_cycle_outcome(state, "cycle_2026-07")
        assert path is None
        assert meta["source_cycle_id"] is None
        assert meta["target_planning_cycle_id"] == "cycle_2026-07"
        assert "No cycle outcome" in meta["resolution_note"]

    def test_resolve_previous_cycle_bailout(self, tmp_path):
        """All cycles in the lookback window are empty → bailout without
        infinite loop.
        """
        state = tmp_path / "state"
        state.mkdir()
        # Pre-populate 30 empty cycles — more than MAX_PREVIOUS_CYCLE_LOOKBACK
        for i in range(26, 0, -1):
            _write_outcome(state, f"cycle_2026-{i:02d}", [])
        for i in range(26, 22, -1):
            _write_outcome(state, f"cycle_2025-{i:02d}", [])
        path, meta = resolve_previous_cycle_outcome(
            state, "cycle_2026-26", max_lookback=MAX_PREVIOUS_CYCLE_LOOKBACK,
        )
        assert path is None
        assert meta["source_cycle_id"] is None
        # All 26 lookback cycles should be in the skip list
        assert len(meta["skipped_cycles"]) == MAX_PREVIOUS_CYCLE_LOOKBACK

    def test_resolve_previous_cycle_malformed_outcome_treated_as_empty(self, tmp_path):
        """A cycle_outcome file that can't be parsed is treated as having no
        trades (not a hard failure — the resolver walks past it).
        """
        state = tmp_path / "state"
        state.mkdir()
        (state / "cycle_outcome_cycle_2026-07.json").write_text("not valid json")
        _write_outcome(state, "cycle_2026-06", [
            {"date": "2026-03-24", "reference": "79230B", "net": 151.0},
        ])
        path, meta = resolve_previous_cycle_outcome(state, "cycle_2026-08")
        assert meta["source_cycle_id"] == "cycle_2026-06"


# ─── Phase A.7: bundle integration ─────────────────────────────────

def test_bundle_includes_cycle_outcome_previous(tmp_path):
    """Bundle contains cycle_outcome_previous.json + .meta.json when a
    prior cycle with trades exists.
    """
    paths = build_fake_grailzee_tree(tmp_path)
    # FAKE_CYCLE_ID is cycle_2026-04; the prior cycle with trades should
    # be cycle_2026-03. Seed it.
    _write_outcome(paths["state"], "cycle_2026-03", [
        {"date": "2026-02-05", "reference": "216570", "net": 251.0},
    ])

    bundle_path = build_outbound_bundle(tmp_path)

    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        assert PREVIOUS_OUTCOME_ARCNAME in names
        assert PREVIOUS_OUTCOME_META_ARCNAME in names

        meta = json.loads(zf.read(PREVIOUS_OUTCOME_META_ARCNAME))
        assert meta["source_cycle_id"] == "cycle_2026-03"
        assert meta["target_planning_cycle_id"] == FAKE_CYCLE_ID
        assert meta["skipped_cycles"] == []

        outcome = json.loads(zf.read(PREVIOUS_OUTCOME_ARCNAME))
        assert outcome["cycle_id"] == "cycle_2026-03"
        assert len(outcome["trades"]) == 1

        # Manifest has both roles registered
        manifest = json.loads(zf.read("manifest.json"))
        roles = {f["role"] for f in manifest["files"]}
        assert "previous_cycle_outcome" in roles
        assert "previous_cycle_outcome_meta" in roles


def test_bundle_meta_only_when_no_previous_cycle_has_trades(tmp_path):
    """First-deployment case: no prior cycles have trade data. Bundle
    still includes the meta (with source_cycle_id: null) but NOT the
    outcome file itself.
    """
    paths = build_fake_grailzee_tree(tmp_path)
    # Do NOT seed any cycle_outcome files.

    bundle_path = build_outbound_bundle(tmp_path)

    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        assert PREVIOUS_OUTCOME_META_ARCNAME in names
        assert PREVIOUS_OUTCOME_ARCNAME not in names

        meta = json.loads(zf.read(PREVIOUS_OUTCOME_META_ARCNAME))
        assert meta["source_cycle_id"] is None
        assert meta["target_planning_cycle_id"] == FAKE_CYCLE_ID
        assert meta["skipped_cycles"] == []

        manifest = json.loads(zf.read("manifest.json"))
        roles = {f["role"] for f in manifest["files"]}
        assert "previous_cycle_outcome_meta" in roles
        assert "previous_cycle_outcome" not in roles


def test_bundle_skipped_cycles_surfaced_in_meta(tmp_path):
    """Bundle meta lists empty-but-existent cycles in skipped_cycles so
    the strategist can say 'your most recent cycle was empty; here's
    the last one with data.'
    """
    paths = build_fake_grailzee_tree(tmp_path, cycle_id="cycle_2026-05")
    _write_outcome(paths["state"], "cycle_2026-04", [])  # empty
    _write_outcome(paths["state"], "cycle_2026-03", [
        {"date": "2026-02-10", "reference": "28500", "net": 120.0},
    ])

    bundle_path = build_outbound_bundle(tmp_path)

    with zipfile.ZipFile(bundle_path) as zf:
        meta = json.loads(zf.read(PREVIOUS_OUTCOME_META_ARCNAME))
        assert meta["source_cycle_id"] == "cycle_2026-03"
        assert meta["skipped_cycles"] == ["cycle_2026-04"]


# ─── Phase A.5: config-file inclusion ──────────────────────────────


from grailzee_bundle.build_bundle import (  # noqa: E402
    CYCLE_FOCUS_LEGACY_ARCNAME,
    WORKSPACE_CONFIG_FILES,
)


def _seed_workspace_configs(workspace_state_dir: Path) -> dict[str, bytes]:
    """Write minimum-viable A.5 workspace configs to `workspace_state_dir`.

    Returns a dict mapping source filename → bytes written, for
    byte-faithful assertions downstream.
    """
    workspace_state_dir.mkdir(parents=True, exist_ok=True)
    blobs: dict[str, bytes] = {}
    fixtures = {
        "analyzer_config.json": {
            "schema_version": 1,
            "last_updated": "2026-04-21T00:00:00Z",
            "updated_by": "phase_a_install",
            "defaulted_fields": ["margin.per_trade_target_margin_fraction"],
            "windows": {"pricing_reports": 2, "trend_reports": 6},
            "margin": {
                "per_trade_target_margin_fraction": 0.05,
                "monthly_return_target_fraction": 0.10,
            },
            "labor": {"hours_per_piece": 1.5},
            "premium_model": {
                "lookback_days": 30,
                "close_count_floor": 5,
                "recent_weighted": True,
            },
            "scoring": {
                "min_sales_for_scoring": 3,
                "risk_reserve_threshold_fraction": 0.40,
                "signal_thresholds": {
                    "strong_max_risk_pct": 10,
                    "normal_max_risk_pct": 20,
                    "reserve_max_risk_pct": 30,
                    "careful_max_risk_pct": 50,
                },
            },
        },
        "brand_floors.json": {
            "schema_version": 1,
            "last_updated": "2026-04-21T00:00:00Z",
            "updated_by": "phase_a_install",
            "defaulted_fields": [
                "brands.Rolex.floor_pct",
                "brands.Tudor.floor_pct",
            ],
            "brands": {
                "Rolex": {"floor_pct": 5.0, "tradeable": True, "asset_class": "watch"},
                "Tudor": {"floor_pct": 10.0, "tradeable": True, "asset_class": "watch"},
            },
        },
        "sourcing_rules.json": {
            "schema_version": 1,
            "last_updated": "2026-04-21T00:00:00Z",
            "updated_by": "phase_a_install",
            "defaulted_fields": [
                "condition_minimum",
                "keyword_filters.exclude",
                "keyword_filters.include",
                "papers_required",
            ],
            "condition_minimum": "Very Good",
            "papers_required": True,
            "keyword_filters": {"include": ["full set"], "exclude": ["for parts"]},
        },
    }
    for name, payload in fixtures.items():
        blob = json.dumps(payload).encode("utf-8")
        (workspace_state_dir / name).write_bytes(blob)
        blobs[name] = blob
    return blobs


class TestPhaseA5ConfigInclusion:
    """Phase A.5: the six strategy-writable configs land in the bundle.

    Three from Drive state (cycle_focus, monthly_goals, quarterly_allocation)
    and three from workspace state (analyzer_config, brand_floors,
    sourcing_rules). Tests use an explicit tmp workspace_state_dir so
    they're hermetic — no coupling to repo state.
    """

    def test_six_config_roles_present(self, tmp_path):
        build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        roles = {f["role"] for f in manifest["files"]}
        assert "cycle_focus" in roles
        assert "monthly_goals" in roles
        assert "quarterly_allocation" in roles
        assert "analyzer_config" in roles
        assert "brand_floors" in roles
        assert "sourcing_rules" in roles

    def test_six_config_archives_have_analyzer_native_names(self, tmp_path):
        """No ``_current`` suffix anywhere in the manifest for the six
        strategy-writable configs."""
        build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        role_to_arcname = {f["role"]: f["path"] for f in manifest["files"]}
        assert role_to_arcname["cycle_focus"] == "cycle_focus.json"
        assert role_to_arcname["monthly_goals"] == "monthly_goals.json"
        assert (
            role_to_arcname["quarterly_allocation"] == "quarterly_allocation.json"
        )
        assert role_to_arcname["analyzer_config"] == "analyzer_config.json"
        assert role_to_arcname["brand_floors"] == "brand_floors.json"
        assert role_to_arcname["sourcing_rules"] == "sourcing_rules.json"
        # Confirm no manifest role uses the legacy _current archive name.
        for entry in manifest["files"]:
            assert entry["path"] != "cycle_focus_current.json"

    def test_workspace_config_bytes_preserved_verbatim(self, tmp_path):
        """Bundle contents match workspace-state file bytes exactly —
        schema_version, defaulted_fields, last_updated, updated_by all
        carry through without transformation."""
        build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        blobs = _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            for role, arcname, source_name in WORKSPACE_CONFIG_FILES:
                bundled = zf.read(arcname)
                assert bundled == blobs[source_name], (
                    f"{role} bytes diverged from source {source_name}"
                )
                # Parsing the bytes returns the full metadata envelope.
                parsed = json.loads(bundled)
                assert "schema_version" in parsed
                assert "defaulted_fields" in parsed
                assert "last_updated" in parsed
                assert "updated_by" in parsed

    def test_drive_config_bytes_preserved_verbatim(self, tmp_path):
        """cycle_focus/monthly_goals/quarterly_allocation bytes from Drive
        state land byte-faithful in the bundle."""
        paths = build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            assert zf.read("cycle_focus.json") == paths["cycle_focus"].read_bytes()
            assert zf.read("monthly_goals.json") == paths["monthly_goals"].read_bytes()
            assert (
                zf.read("quarterly_allocation.json")
                == paths["quarterly_allocation"].read_bytes()
            )

    def test_cycle_focus_legacy_alias_present(self, tmp_path):
        """Phase A.5 transitional alias: cycle_focus_current.json archive
        entry carries identical bytes to cycle_focus.json but is NOT a
        manifest role."""
        paths = build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            names = set(zf.namelist())
            assert CYCLE_FOCUS_LEGACY_ARCNAME in names
            legacy_bytes = zf.read(CYCLE_FOCUS_LEGACY_ARCNAME)
            canonical_bytes = zf.read("cycle_focus.json")
            assert legacy_bytes == canonical_bytes
            assert legacy_bytes == paths["cycle_focus"].read_bytes()

            manifest = json.loads(zf.read("manifest.json"))
            archive_paths = {f["path"] for f in manifest["files"]}
            assert CYCLE_FOCUS_LEGACY_ARCNAME not in archive_paths
            roles = {f["role"] for f in manifest["files"]}
            assert "cycle_focus_current" not in roles
            assert "cycle_focus" in roles

    @pytest.mark.parametrize(
        "missing_name,role_label",
        [
            ("analyzer_config.json", "analyzer_config"),
            ("brand_floors.json", "brand_floors"),
            ("sourcing_rules.json", "sourcing_rules"),
        ],
    )
    def test_missing_workspace_config_fails_loud(
        self, tmp_path, missing_name, role_label
    ):
        """Each workspace config is required; absence raises
        FileNotFoundError with the role label in the message."""
        build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)
        (workspace_state / missing_name).unlink()

        with pytest.raises(FileNotFoundError, match=role_label):
            build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

    def test_missing_workspace_dir_fails_loud(self, tmp_path):
        """Pointing at a non-existent workspace_state_dir surfaces the
        first missing config path as FileNotFoundError."""
        build_fake_grailzee_tree(tmp_path)
        nonexistent = tmp_path / "no_such_workspace_state"
        with pytest.raises(FileNotFoundError):
            build_outbound_bundle(tmp_path, workspace_state_dir=nonexistent)

    def test_default_workspace_state_dir_resolves(self):
        """DEFAULT_WORKSPACE_STATE_DIR points at the repo-backed state
        directory, not a Drive path."""
        from grailzee_bundle.build_bundle import DEFAULT_WORKSPACE_STATE_DIR

        assert DEFAULT_WORKSPACE_STATE_DIR.name == "state"
        # Must not resolve into GrailzeeData (the Drive-backed root).
        assert "GrailzeeData" not in str(DEFAULT_WORKSPACE_STATE_DIR)

    def test_config_files_included_count(self, tmp_path):
        """Six strategy-writable configs land in the manifest on a
        successful build (three from Drive, three from workspace)."""
        build_fake_grailzee_tree(tmp_path)
        workspace_state = tmp_path / "workspace_state"
        _seed_workspace_configs(workspace_state)

        bundle = build_outbound_bundle(tmp_path, workspace_state_dir=workspace_state)

        with zipfile.ZipFile(bundle, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        config_roles = {
            "cycle_focus",
            "monthly_goals",
            "quarterly_allocation",
            "analyzer_config",
            "brand_floors",
            "sourcing_rules",
        }
        bundled = {f["role"] for f in manifest["files"]} & config_roles
        assert bundled == config_roles
        assert len(bundled) == 6
