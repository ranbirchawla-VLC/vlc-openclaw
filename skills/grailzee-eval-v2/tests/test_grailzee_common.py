"""Tests for scripts.grailzee_common — Grailzee Eval v2 shared module.

Each test category documents the v1 behavior it validates so future
changes can't silently drift from the extracted logic.
"""

import json
import os
from datetime import date

from scripts.grailzee_common import (
    LEDGER_COLUMNS,
    LedgerRow,
    NR_FIXED,
    RES_FIXED,
    adjusted_max_buy,
    append_ledger_row,
    append_name_cache_entry,
    breakeven_nr,
    breakeven_reserve,
    calculate_presentation_premium,
    classify_dj_config,
    cycle_date_range,
    cycle_id_from_date,
    ensure_ledger_exists,
    get_ad_budget,
    is_cycle_focus_current,
    is_quality_sale,
    load_name_cache,
    match_reference,
    max_buy_nr,
    max_buy_reserve,
    normalize_ref,
    parse_ledger_csv,
    prev_cycle,
    save_name_cache,
    strip_ref,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. Formula tests
# ═══════════════════════════════════════════════════════════════════════


class TestFormulas:
    """v1 formula: round((median - FIXED) / 1.05, nearest $10)."""

    def test_max_buy_nr_basic(self):
        # (3000 - 149) / 1.05 = 2715.238... rounds to 2720
        assert max_buy_nr(3000) == 2720

    def test_max_buy_nr_rounds_to_ten(self):
        # (3150 - 149) / 1.05 = 2858.095... rounds to 2860
        assert max_buy_nr(3150) == 2860

    def test_max_buy_reserve_basic(self):
        # (3000 - 199) / 1.05 = 2667.619... rounds to 2670
        assert max_buy_reserve(3000) == 2670

    def test_breakeven_roundtrip(self):
        """max_buy + fixed_cost = breakeven by definition."""
        mb = max_buy_nr(3000)
        assert breakeven_nr(mb) == mb + NR_FIXED
        mb_r = max_buy_reserve(3000)
        assert breakeven_reserve(mb_r) == mb_r + RES_FIXED

    def test_adjusted_max_buy(self):
        # median=3000, premium=10% => adjusted_median=3300
        # (3300 - 149) / 1.05 = 3000.952... rounds to 3000
        assert adjusted_max_buy(3000, NR_FIXED, 10.0) == 3000


class TestAdBudget:
    """get_ad_budget brackets extracted from v1 evaluate_deal.py."""

    def test_below_first_threshold(self):
        assert get_ad_budget(2500) == "$37\u201350"

    def test_highest_bracket(self):
        assert get_ad_budget(15000) == "$250 cap"


# ═══════════════════════════════════════════════════════════════════════
# 2. normalize_ref tests
#    v1 behavior (analyze_report.py lines 231-234):
#      str(s).strip().upper(), then strip trailing '.0' (Excel artifact)
# ═══════════════════════════════════════════════════════════════════════


class TestNormalizeRef:
    def test_strips_whitespace(self):
        assert normalize_ref("  79830RB  ") == "79830RB"

    def test_uppercases(self):
        """v1 uppercases all references for case-insensitive matching."""
        assert normalize_ref("m79830rb") == "M79830RB"

    def test_handles_empty(self):
        assert normalize_ref("") == ""

    def test_preserves_valid_refs(self):
        assert normalize_ref("79830RB") == "79830RB"

    def test_strips_excel_decimal(self):
        """v1 strips trailing '.0' from Excel numeric-to-string artifacts."""
        assert normalize_ref("126300.0") == "126300"


# ═══════════════════════════════════════════════════════════════════════
# 3. strip_ref tests
#    v1 behavior (evaluate_deal.py lines 53-62):
#      normalize first, strip leading M (if len>5), strip trailing -XXXX,
#      remove all hyphens/dots/spaces
# ═══════════════════════════════════════════════════════════════════════


class TestStripRef:
    def test_prefix_removal(self):
        """Tudor M-prefix stripped: M79830RB => 79830RB (no separators)."""
        assert strip_ref("M79830RB") == "79830RB"

    def test_suffix_removal(self):
        """Trailing -0001 suffix stripped."""
        result = strip_ref("M79830RB-0001")
        assert result == "79830RB"

    def test_idempotent(self):
        """strip_ref(strip_ref(x)) == strip_ref(x)."""
        val = "M79830RB-0001"
        assert strip_ref(strip_ref(val)) == strip_ref(val)

    def test_omega_dots_removed(self):
        """Omega dot-separated refs have dots stripped."""
        assert strip_ref("210.30.42.20.03.001") == "21030422003001"


# ═══════════════════════════════════════════════════════════════════════
# 4. match_reference tests
#    v1 behavior (analyze_report.py lines 236-244):
#      Normalized substring match in either direction, then
#      separator-stripped substring match in either direction.
# ═══════════════════════════════════════════════════════════════════════


class TestMatchReference:
    def test_exact_match(self):
        assert match_reference("79830RB", "79830RB") is True

    def test_no_match(self):
        assert match_reference("79830RB", "126300") is False

    def test_against_list(self):
        """Matches if any item in the target list matches."""
        assert match_reference("79830RB", ["79830RB", "M79830RB"]) is True

    def test_normalizes_both_sides(self):
        """Case and whitespace differences are normalized away."""
        assert match_reference("  m79830rb  ", "79830RB") is True

    def test_substring_match(self):
        """v1 matches if either normalized form is a substring of the other."""
        assert match_reference("M79830RB-0001", "79830RB") is True


# ═══════════════════════════════════════════════════════════════════════
# 5. classify_dj_config tests
#    v1 behavior (analyze_report.py lines 246-252):
#      Lowercase title, check dial keywords, then bracelet keywords if
#      required. v1 returned "Other"; v2 returns None for unclassifiable.
#    DJ_CONFIGS has 9 entries:
#      Black/Oyster: 1 dial kw, 1 bracelet kw
#      Blue/Jubilee: 1 dial kw, 1 bracelet kw
#      Blue/Oyster: 1 dial kw, 1 bracelet kw
#      Slate/Jubilee: 1 dial kw, 1 bracelet kw
#      Slate/Oyster: 1 dial kw, 1 bracelet kw
#      Green: 1 dial kw, bracelet=None
#      Wimbledon: 1 dial kw, bracelet=None
#      White/Oyster: 1 dial kw, 1 bracelet kw
#      Silver: 1 dial kw, bracelet=None
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyDjConfig:
    def test_known_variant(self):
        title = "Rolex Datejust 41 126300 Black Dial Oyster Bracelet"
        assert classify_dj_config(title) == "Black/Oyster"

    def test_unclassifiable(self):
        """Generic title with no dial/bracelet keywords returns None."""
        assert classify_dj_config("Rolex Datejust 41 126300") is None

    def test_case_insensitive(self):
        title = "ROLEX DATEJUST 41 SILVER DIAL"
        assert classify_dj_config(title) == "Silver"

    def test_bracelet_required_when_specified(self):
        """Blue dial without bracelet keyword doesn't match Blue/Jubilee or Blue/Oyster."""
        title = "Rolex Datejust 41 Blue Dial Fluted Bezel"
        # Blue matches dial, but no bracelet keyword => no match for either config
        assert classify_dj_config(title) is None

    def test_no_bracelet_needed_for_green(self):
        """Green config has bracelet=None, so any green dial matches."""
        title = "Rolex Datejust 41 Green Dial President Bracelet"
        assert classify_dj_config(title) == "Green"


# ═══════════════════════════════════════════════════════════════════════
# 6. is_quality_sale tests
#    v1 behavior (analyze_report.py lines 255-258):
#      condition must contain a QUALITY_CONDITIONS substring AND
#      papers must be in ('yes', 'y', 'true', '1', 'included').
#    QUALITY_CONDITIONS = {'very good', 'like new', 'new', 'excellent'}
# ═══════════════════════════════════════════════════════════════════════


class TestIsQualitySale:
    def test_passes(self):
        sale = {"condition": "Very Good", "papers": "Yes"}
        assert is_quality_sale(sale) is True

    def test_fails_condition(self):
        sale = {"condition": "Poor", "papers": "Yes"}
        assert is_quality_sale(sale) is False

    def test_fails_papers(self):
        """v1 requires papers to be exactly one of the allowed values."""
        sale = {"condition": "Excellent", "papers": "No"}
        assert is_quality_sale(sale) is False

    def test_missing_fields_returns_false(self):
        """Empty dict; both condition and papers default to empty string."""
        assert is_quality_sale({}) is False

    def test_condition_substring_match(self):
        """v1 uses substring: 'new' matches 'Like New' (both 'new' and 'like new')."""
        sale = {"condition": "Like New with Tags", "papers": "yes"}
        assert is_quality_sale(sale) is True


# ═══════════════════════════════════════════════════════════════════════
# 7. Name cache I/O tests
# ═══════════════════════════════════════════════════════════════════════


class TestNameCache:
    def test_load_missing_returns_empty(self, empty_name_cache):
        result = load_name_cache(str(empty_name_cache))
        assert result == {}

    def test_save_then_load_roundtrip(self, empty_name_cache):
        data = {"79830RB": {"brand": "Tudor", "model": "BB GMT Pepsi"}}
        save_name_cache(data, str(empty_name_cache))
        loaded = load_name_cache(str(empty_name_cache))
        assert loaded == data

    def test_append_new_entry(self, empty_name_cache):
        append_name_cache_entry(
            "79830RB", "Tudor", "BB GMT Pepsi",
            alt_refs=["M79830RB"],
            cache_path=str(empty_name_cache),
        )
        loaded = load_name_cache(str(empty_name_cache))
        assert "79830RB" in loaded
        assert loaded["79830RB"]["brand"] == "Tudor"
        assert loaded["79830RB"]["alt_refs"] == ["M79830RB"]

    def test_append_existing_is_idempotent(self, seeded_name_cache):
        """Appending an existing reference does not overwrite it."""
        original = load_name_cache(str(seeded_name_cache))
        original_entry = original["79830RB"].copy()
        # Attempt to append with different model name
        append_name_cache_entry(
            "79830RB", "Tudor", "CHANGED MODEL",
            cache_path=str(seeded_name_cache),
        )
        reloaded = load_name_cache(str(seeded_name_cache))
        assert reloaded["79830RB"]["model"] == original_entry["model"]

    def test_save_sorts_keys(self, empty_name_cache):
        data = {"Z_ref": {"brand": "Z"}, "A_ref": {"brand": "A"}}
        save_name_cache(data, str(empty_name_cache))
        raw = empty_name_cache.read_text()
        a_pos = raw.index('"A_ref"')
        z_pos = raw.index('"Z_ref"')
        assert a_pos < z_pos


# ═══════════════════════════════════════════════════════════════════════
# 8. cycle_id_from_date tests
#    Cycle 01 starts the first Monday of the year.
#    2026: Jan 1 = Thursday, first Monday = Jan 5
#    2025: Jan 1 = Wednesday, first Monday = Jan 6
# ═══════════════════════════════════════════════════════════════════════


class TestCycleIdFromDate:
    def test_first_monday_of_year(self):
        """First Monday of 2026 is Jan 5; that date is cycle 01."""
        assert cycle_id_from_date(date(2026, 1, 5)) == "cycle_2026-01"

    def test_mid_year(self):
        """Apr 16 2026: delta from Jan 5 = 101 days, 101//14 = 7, cycle 08."""
        assert cycle_id_from_date(date(2026, 4, 16)) == "cycle_2026-08"

    def test_jan_1_before_first_monday(self):
        """Jan 1 2026 (Thursday) falls before first Monday (Jan 5).
        Should resolve to the last cycle of 2025.
        2025 first Monday = Jan 6; Dec 31 2025 delta = 359; 359//14 = 25; cycle 26.
        """
        assert cycle_id_from_date(date(2026, 1, 1)) == "cycle_2025-26"

    def test_last_day_of_year(self):
        """Dec 31 2026: delta from Jan 5 = 360 days, 360//14 = 25, cycle 26."""
        assert cycle_id_from_date(date(2026, 12, 31)) == "cycle_2026-26"

    def test_zero_padding(self):
        """Format is cycle_YYYY-NN with 2-digit zero-padded NN."""
        cid = cycle_id_from_date(date(2026, 1, 5))
        assert cid == "cycle_2026-01"
        assert len(cid.split("-")[1]) == 2

    def test_jul_1_2026(self):
        """Jul 1 2026: delta from Jan 5 = 177 days, 177//14 = 12, cycle 13."""
        assert cycle_id_from_date(date(2026, 7, 1)) == "cycle_2026-13"


# ═══════════════════════════════════════════════════════════════════════
# 9. cycle_date_range tests
# ═══════════════════════════════════════════════════════════════════════


class TestCycleDateRange:
    def test_roundtrip(self):
        """cycle_id_from_date on the start of a range returns same cycle_id."""
        cid = "cycle_2026-08"
        start, end = cycle_date_range(cid)
        assert cycle_id_from_date(start) == cid

    def test_duration_is_14_days(self):
        """Each cycle spans exactly 14 days (end - start = 13 inclusive)."""
        start, end = cycle_date_range("cycle_2026-05")
        assert (end - start).days == 13


# ═══════════════════════════════════════════════════════════════════════
# 10. prev_cycle tests
# ═══════════════════════════════════════════════════════════════════════


class TestPrevCycle:
    def test_same_year(self):
        assert prev_cycle("cycle_2026-05") == "cycle_2026-04"

    def test_year_boundary(self):
        """cycle_2026-01 predecessor is the last cycle of 2025 (cycle_2025-26)."""
        assert prev_cycle("cycle_2026-01") == "cycle_2025-26"

    def test_preserves_format(self):
        result = prev_cycle("cycle_2026-05")
        assert result.startswith("cycle_")
        assert len(result.split("-")[1]) == 2


# ═══════════════════════════════════════════════════════════════════════
# 11. is_cycle_focus_current tests
# ═══════════════════════════════════════════════════════════════════════


class TestIsCycleFocusCurrent:
    def test_no_file_returns_false(self, tmp_state_dir):
        """No cycle_focus.json on disk => False."""
        path = str(tmp_state_dir / "cycle_focus.json")
        assert is_cycle_focus_current("cycle_2026-08", focus=None) is False

    def test_matching(self):
        focus = {"cycle_id": "cycle_2026-08", "targets": []}
        assert is_cycle_focus_current("cycle_2026-08", focus=focus) is True

    def test_mismatched(self):
        focus = {"cycle_id": "cycle_2026-07", "targets": []}
        assert is_cycle_focus_current("cycle_2026-08", focus=focus) is False


# ═══════════════════════════════════════════════════════════════════════
# 12. calculate_presentation_premium tests
# ═══════════════════════════════════════════════════════════════════════


class TestPresentationPremium:
    def test_empty_trades(self):
        result = calculate_presentation_premium([])
        assert result["threshold_met"] is False
        assert result["adjustment"] == 0
        assert result["trade_count"] == 0

    def test_threshold_met(self):
        """10 trades at +10% => threshold_met True, adjustment = 5.0."""
        rows = [{"premium_vs_median": 10.0, "median_at_trade": 3000}] * 10
        result = calculate_presentation_premium(rows)
        assert result["threshold_met"] is True
        assert result["adjustment"] == 5.0
        assert result["avg_premium"] == 10.0

    def test_volume_gate(self):
        """9 trades at +10% => threshold_met False (need 10)."""
        rows = [{"premium_vs_median": 10.0, "median_at_trade": 3000}] * 9
        result = calculate_presentation_premium(rows)
        assert result["threshold_met"] is False
        assert result["adjustment"] == 0

    def test_magnitude_gate(self):
        """10 trades at +6% => threshold_met False (need +8%)."""
        rows = [{"premium_vs_median": 6.0, "median_at_trade": 3000}] * 10
        result = calculate_presentation_premium(rows)
        assert result["threshold_met"] is False
        assert result["adjustment"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 13. Ledger I/O tests
# ═══════════════════════════════════════════════════════════════════════


class TestLedgerIO:
    def test_parse_missing_file_returns_empty(self, tmp_path):
        assert parse_ledger_csv(str(tmp_path / "nope.csv")) == []

    def test_ensure_creates_header_only(self, tmp_path):
        path = str(tmp_path / "ledger.csv")
        ensure_ledger_exists(path)
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert content.strip() == ",".join(LEDGER_COLUMNS)

    def test_ensure_is_idempotent(self, tmp_path):
        path = str(tmp_path / "ledger.csv")
        ensure_ledger_exists(path)
        ensure_ledger_exists(path)
        rows = parse_ledger_csv(path)
        assert rows == []

    def test_append_and_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "ledger.csv")
        row = LedgerRow(
            date_closed=date(2026, 4, 16),
            cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750,
            sell_price=3200,
        )
        append_ledger_row(row, path)
        loaded = parse_ledger_csv(path)
        assert len(loaded) == 1
        assert loaded[0].brand == "Tudor"
        assert loaded[0].buy_price == 2750

    def test_sequential_writes_preserved(self, tmp_path):
        path = str(tmp_path / "ledger.csv")
        for i in range(3):
            append_ledger_row(LedgerRow(
                date_closed=date(2026, 1, 5 + i),
                cycle_id="cycle_2026-01",
                brand="Tudor",
                reference="79830RB",
                account="NR",
                buy_price=2700 + i * 100,
                sell_price=3100 + i * 100,
            ), path)
        loaded = parse_ledger_csv(path)
        assert len(loaded) == 3
        assert loaded[0].buy_price == 2700
        assert loaded[2].buy_price == 2900

    def test_append_creates_parent_directory(self, tmp_path):
        path = str(tmp_path / "subdir" / "ledger.csv")
        append_ledger_row(LedgerRow(
            date_closed=date(2026, 4, 16),
            cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750,
            sell_price=3200,
        ), path)
        assert os.path.exists(path)

    def test_parse_malformed_row_raises(self, tmp_path):
        path = str(tmp_path / "bad.csv")
        with open(path, "w") as f:
            f.write(",".join(LEDGER_COLUMNS) + "\n")
            f.write("not-a-date,cycle,brand,ref,NR,abc,3200\n")
        import pytest
        with pytest.raises(ValueError, match="Malformed row"):
            parse_ledger_csv(path)


# ═══════════════════════════════════════════════════════════════════════
# 14. Tracer tests
# ═══════════════════════════════════════════════════════════════════════


class TestTracer:
    def test_get_tracer_without_env_returns_usable_tracer(self, monkeypatch):
        """Without OTEL_EXPORTER_OTLP_ENDPOINT, tracer is a no-op but
        still satisfies the context-manager span interface."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        from scripts.grailzee_common import get_tracer
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test_span") as span:
            span.set_attribute("foo", "bar")
        assert True

    def test_get_tracer_is_idempotent(self):
        """Multiple calls return usable tracers without crashing."""
        from scripts.grailzee_common import get_tracer
        t1 = get_tracer("test")
        t2 = get_tracer("test")
        with t1.start_as_current_span("a"):
            pass
        with t2.start_as_current_span("b"):
            pass

    def test_tracer_name_accepts_module_style(self):
        """Dotted module names work as tracer names."""
        from scripts.grailzee_common import get_tracer
        tracer = get_tracer("grailzee_common.submodule.operation")
        with tracer.start_as_current_span("op") as span:
            assert span is not None
