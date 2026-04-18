"""Tests for scripts.query_targets — two-section Strong/Normal lookup (Phase 19).

Phase 17's cycle-gated test suite (34 tests across 8 categories) was
removed in this phase because D3 + D4 supersede the cycle-gated contract.
This replacement file covers the five behaviors specified in the Phase
19 deliverable 5 spec:

    1. Happy path: Strong + Normal present, Reserve/Careful/Pass excluded
    2. Empty Strong: header emitted with no entries
    3. Empty Normal: header emitted with no entries
    4. Both empty: fallback single-line message
    5. Sort correctness: max_buy_nr DESC within each tier
"""

import json

import pytest

from scripts.grailzee_common import CACHE_SCHEMA_VERSION
from scripts.query_targets import EMPTY_MESSAGE, query_targets


# ─── Fixture helpers ─────────────────────────────────────────────────


def _ref(brand, model, reference, max_buy_nr, signal):
    return {
        "brand": brand,
        "model": model,
        "reference": reference,
        "max_buy_nr": max_buy_nr,
        "signal": signal,
    }


def _write_cache(tmp_path, refs):
    cache = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "references": refs,
    }
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(cache))
    return str(p)


# ─── Tests ───────────────────────────────────────────────────────────


def test_happy_path_mix_of_tiers(tmp_path):
    """Strong/Normal included and sorted DESC; Reserve/Careful/Pass excluded."""
    refs = {
        "Tudor|BB GMT": _ref("Tudor", "BB GMT Pepsi", "79830RB", 2910, "Strong"),
        "Omega|SMD": _ref("Omega", "SMD 300M", "210.30", 4200, "Strong"),
        "Rolex|Sub": _ref("Rolex", "Submariner", "124060", 5500, "Normal"),
        "Breitling|Avi": _ref("Breitling", "Avenger", "A17320", 2000, "Normal"),
        "Cartier|Santos": _ref("Cartier", "Santos", "WSSA", 3000, "Reserve"),
        "Panerai|Lum": _ref("Panerai", "Luminor", "PAM00", 1500, "Careful"),
        "Hamilton|Khaki": _ref("Hamilton", "Khaki Field", "H68", 500, "Pass"),
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)
    lines = out.splitlines()

    assert lines[0] == "STRONG"
    # Strong sorted DESC: Omega 4200 before Tudor 2910
    assert lines[1] == "Omega SMD 300M — 210.30 — $4200"
    assert lines[2] == "Tudor BB GMT Pepsi — 79830RB — $2910"
    assert lines[3] == ""
    assert lines[4] == "NORMAL"
    # Normal sorted DESC: Rolex 5500 before Breitling 2000
    assert lines[5] == "Rolex Submariner — 124060 — $5500"
    assert lines[6] == "Breitling Avenger — A17320 — $2000"
    assert len(lines) == 7

    for excluded in ("Cartier", "Panerai", "Hamilton"):
        assert excluded not in out


def test_empty_strong_header_present_with_no_entries(tmp_path):
    """Only-Normal cache: STRONG header emitted with zero entries."""
    refs = {
        "Rolex|Sub": _ref("Rolex", "Submariner", "124060", 5500, "Normal"),
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)
    lines = out.splitlines()

    assert lines[0] == "STRONG"
    assert lines[1] == ""
    assert lines[2] == "NORMAL"
    assert lines[3] == "Rolex Submariner — 124060 — $5500"
    assert len(lines) == 4


def test_empty_normal_header_present_with_no_entries(tmp_path):
    """Only-Strong cache: NORMAL header emitted with zero entries."""
    refs = {
        "Tudor|BB GMT": _ref("Tudor", "BB GMT", "79830RB", 2910, "Strong"),
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)
    lines = out.splitlines()

    assert lines[0] == "STRONG"
    assert lines[1] == "Tudor BB GMT — 79830RB — $2910"
    assert lines[2] == ""
    assert lines[3] == "NORMAL"
    assert len(lines) == 4


def test_both_tiers_empty_falls_back_to_message(tmp_path):
    """Only Reserve/Careful/Pass refs: collapses to EMPTY_MESSAGE."""
    refs = {
        "Cartier|Santos": _ref("Cartier", "Santos", "WSSA", 3000, "Reserve"),
        "Panerai|Lum": _ref("Panerai", "Luminor", "PAM00", 1500, "Careful"),
        "Hamilton|Khaki": _ref("Hamilton", "Khaki", "H68", 500, "Pass"),
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)

    assert out == EMPTY_MESSAGE
    assert "STRONG" not in out
    assert "NORMAL" not in out


def test_sort_correctness_desc_within_tier(tmp_path):
    """Multiple Strong refs with distinct max_buy_nr values sort DESC."""
    values = [1000, 5000, 3000, 2000, 4000]
    refs = {
        f"Tudor|M{i}": _ref("Tudor", f"Model {i}", f"R{i}", mbnr, "Strong")
        for i, mbnr in enumerate(values)
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)
    lines = out.splitlines()

    # Lines 1..5 are the 5 Strong entries (line 0 is STRONG header)
    dollar_values = [int(line.rsplit("$", 1)[1]) for line in lines[1:6]]
    assert dollar_values == sorted(values, reverse=True)


def test_float_max_buy_nr_renders_as_int(tmp_path):
    """Cache stores max_buy_nr as float (e.g. 1950.0); output must render as int."""
    refs = {
        "Tudor|A": _ref("Tudor", "Royal 41mm", "M28300", 1950.0, "Strong"),
    }
    path = _write_cache(tmp_path, refs)
    out = query_targets(cache_path=path)

    assert "$1950" in out
    assert "1950.0" not in out


def test_missing_cache_raises_file_not_found(tmp_path):
    """Missing cache file → FileNotFoundError with path in message."""
    missing = str(tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError, match="does_not_exist.json"):
        query_targets(cache_path=missing)


def test_stale_schema_raises_value_error(tmp_path):
    """Schema version below required → ValueError naming the mismatch."""
    stale = {"schema_version": CACHE_SCHEMA_VERSION - 1, "references": {}}
    p = tmp_path / "analysis_cache.json"
    p.write_text(json.dumps(stale))

    with pytest.raises(ValueError, match="schema version"):
        query_targets(cache_path=str(p))
