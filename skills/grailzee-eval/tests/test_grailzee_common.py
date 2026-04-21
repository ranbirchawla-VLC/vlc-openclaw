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
    cycle_outcome_path,
    ensure_ledger_exists,
    get_ad_budget,
    is_cycle_focus_current,
    is_quality_sale,
    load_cycle_focus,
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
# 10b. cycle_outcome_path tests (Phase A.5)
# ═══════════════════════════════════════════════════════════════════════


class TestCycleOutcomePath:
    """Phase A.5: per-cycle outcome filenames replace single-file constant."""

    def test_cycle_outcome_path_per_cycle(self):
        """Expected path embeds the full cycle_id in the filename."""
        p = cycle_outcome_path("cycle_2026-07")
        assert p.endswith("/state/cycle_outcome_cycle_2026-07.json")

    def test_cycle_outcome_path_distinct_per_cycle(self):
        """Different cycle_ids produce different files (no collision)."""
        assert cycle_outcome_path("cycle_2026-06") != cycle_outcome_path("cycle_2026-08")

    def test_cycle_outcome_path_year_boundary(self):
        """Year boundary cycle_ids are handled as opaque strings."""
        p = cycle_outcome_path("cycle_2025-26")
        assert p.endswith("cycle_outcome_cycle_2025-26.json")


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

    def test_starter_sentinel_never_matches_real_cycle(self):
        """Phase A.5: ``cycle_id="starter"`` is the installer sentinel.
        is_cycle_focus_current returns False for any real cycle_id so
        agent-side freshness gates treat the starter file as 'not yet
        strategy-set' — which is exactly the intended behavior."""
        focus = {"cycle_id": "starter", "targets": []}
        assert is_cycle_focus_current("cycle_2026-08", focus=focus) is False
        assert is_cycle_focus_current("cycle_2026-04", focus=focus) is False


# ═══════════════════════════════════════════════════════════════════════
# 11b. load_cycle_focus v1-shape compatibility (Phase A.5)
# ═══════════════════════════════════════════════════════════════════════


class TestLoadCycleFocusV1Shape:
    """Phase A.5: the installer ships a v1-shape cycle_focus.json.
    load_cycle_focus is a simple json loader with no schema_version
    check; verify it reads the installer's v1 content cleanly."""

    def test_load_cycle_focus_reads_installer_shape(self, tmp_path):
        """Write the installer's exact factory content to a tmp path;
        load_cycle_focus reads it without error and returns all fields."""
        from scripts.install_cycle_focus import CYCLE_FOCUS_FACTORY_CONTENT

        payload = dict(CYCLE_FOCUS_FACTORY_CONTENT)
        payload["last_updated"] = "2026-04-21T00:00:00Z"
        payload["updated_by"] = "phase_a_install"
        payload["defaulted_fields"] = [
            "brand_emphasis",
            "brand_pullback",
            "capital_target",
            "cycle_date_range",
            "cycle_id",
            "notes",
            "target_margin_fraction",
            "targets",
            "volume_target",
        ]
        target = tmp_path / "cycle_focus.json"
        target.write_text(json.dumps(payload))

        loaded = load_cycle_focus(str(target))
        assert loaded is not None
        assert loaded["schema_version"] == 1
        assert loaded["cycle_id"] == "starter"
        assert loaded["cycle_date_range"] == {
            "start": "1970-01-01",
            "end": "1970-01-01",
        }
        assert loaded["capital_target"] == 15000
        assert loaded["volume_target"] == 4
        assert loaded["targets"] == []
        assert loaded["brand_emphasis"] == []

    def test_load_cycle_focus_missing_returns_none(self, tmp_path):
        """Absent file yields None (existing contract); starter behavior
        should match the absent-file path downstream."""
        missing = tmp_path / "absent.json"
        assert load_cycle_focus(str(missing)) is None


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


class TestNoOpSpan:
    """A.cleanup.2 Item 11: _NoOpSpan implements add_event.

    Future code that emits events on a span must not AttributeError
    when opentelemetry is absent and the fallback _NoOpSpan is in use.
    """

    def test_add_event_no_args(self):
        from scripts.grailzee_common import _NoOpSpan
        span = _NoOpSpan()
        span.add_event("something_happened")

    def test_add_event_with_attributes(self):
        from scripts.grailzee_common import _NoOpSpan
        span = _NoOpSpan()
        span.add_event(
            "batch_flushed",
            attributes={"count": 3, "bytes": 1024},
        )

    def test_add_event_with_timestamp(self):
        from scripts.grailzee_common import _NoOpSpan
        span = _NoOpSpan()
        span.add_event(
            "synthetic",
            attributes={"k": "v"},
            timestamp=1_700_000_000_000_000_000,
        )

    def test_add_event_positional_attributes(self):
        from scripts.grailzee_common import _NoOpSpan
        span = _NoOpSpan()
        span.add_event("ok", {"k": "v"})


# ═══════════════════════════════════════════════════════════════════════
# Phase A.2 — config_path + load_analyzer_config
# ═══════════════════════════════════════════════════════════════════════


class TestConfigPath:
    """config_path resolves under the workspace state/ directory."""

    def test_resolves_to_workspace_state(self):
        from scripts.grailzee_common import config_path, WORKSPACE_STATE_PATH
        assert config_path("analyzer_config.json") == (
            f"{WORKSPACE_STATE_PATH}/analyzer_config.json"
        )

    def test_all_phase_a_filenames(self):
        """A.2-A.5 will create six files under STATE_PATH."""
        from scripts.grailzee_common import config_path, WORKSPACE_STATE_PATH
        names = [
            "analyzer_config.json",
            "brand_floors.json",
            "sourcing_rules.json",
            "cycle_focus.json",
            "monthly_goals.json",
            "quarterly_allocation.json",
        ]
        for name in names:
            resolved = config_path(name)
            assert resolved.startswith(WORKSPACE_STATE_PATH + "/")
            assert resolved.endswith("/" + name)

    def test_strips_leading_slash(self):
        from scripts.grailzee_common import config_path, WORKSPACE_STATE_PATH
        assert config_path("/analyzer_config.json") == (
            f"{WORKSPACE_STATE_PATH}/analyzer_config.json"
        )

    def test_strips_trailing_slash(self):
        from scripts.grailzee_common import config_path, WORKSPACE_STATE_PATH
        assert config_path("analyzer_config.json/") == (
            f"{WORKSPACE_STATE_PATH}/analyzer_config.json"
        )

    def test_empty_name_raises(self):
        import pytest
        from scripts.grailzee_common import config_path
        with pytest.raises(ValueError):
            config_path("")
        with pytest.raises(ValueError):
            config_path("   ")
        with pytest.raises(ValueError):
            config_path("/")

    def test_non_string_raises(self):
        import pytest
        from scripts.grailzee_common import config_path
        with pytest.raises(ValueError):
            config_path(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            config_path(123)  # type: ignore[arg-type]

    def test_rejects_parent_traversal(self):
        import pytest
        from scripts.grailzee_common import config_path
        with pytest.raises(ValueError):
            config_path("../secrets.json")
        with pytest.raises(ValueError):
            config_path("sub/../../etc/passwd")

    def test_workspace_state_path_absolute(self):
        """WORKSPACE_STATE_PATH must be an absolute path."""
        from scripts.grailzee_common import WORKSPACE_STATE_PATH
        assert os.path.isabs(WORKSPACE_STATE_PATH)
        assert WORKSPACE_STATE_PATH.endswith("/state")


class TestLoadAnalyzerConfig:
    """Cache-once-per-process memoized loader with file-absent fallback."""

    def setup_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def teardown_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def test_file_present_path(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            analyzer_config_source,
            load_analyzer_config,
        )
        p = tmp_path / "analyzer_config.json"
        content = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        content["margin"]["per_trade_target_margin_fraction"] = 0.07
        write_config(p, content, [], "test")

        cfg = load_analyzer_config(path=str(p))
        assert cfg["margin"]["per_trade_target_margin_fraction"] == 0.07
        assert analyzer_config_source() == "file"

    def test_file_absent_falls_back_to_defaults(self, tmp_path):
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            analyzer_config_source,
            load_analyzer_config,
        )
        missing = tmp_path / "does_not_exist.json"

        cfg = load_analyzer_config(path=str(missing))
        assert (
            cfg["margin"]["per_trade_target_margin_fraction"]
            == ANALYZER_CONFIG_FACTORY_DEFAULTS["margin"]["per_trade_target_margin_fraction"]
        )
        assert (
            cfg["scoring"]["signal_thresholds"]
            == ANALYZER_CONFIG_FACTORY_DEFAULTS["scoring"]["signal_thresholds"]
        )
        assert analyzer_config_source() == "fallback"

    def test_malformed_file_falls_back(self, tmp_path):
        from scripts.grailzee_common import (
            analyzer_config_source,
            load_analyzer_config,
        )
        p = tmp_path / "analyzer_config.json"
        p.write_text("{not valid json")

        cfg = load_analyzer_config(path=str(p))
        assert cfg["margin"]["per_trade_target_margin_fraction"] == 0.05
        assert analyzer_config_source() == "fallback"

    def test_cache_returns_same_dict_across_calls(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            load_analyzer_config,
        )
        p = tmp_path / "analyzer_config.json"
        content = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        write_config(p, content, [], "test")

        first = load_analyzer_config(path=str(p))
        second = load_analyzer_config(path=str(p))
        assert first is second

    def test_cache_ignores_path_after_first_call(self, tmp_path):
        """Second call with a different path returns cached content.

        Documents the 'first call wins' semantic: tests that want to
        exercise a new path must call _reset_analyzer_config_cache()
        first.
        """
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            load_analyzer_config,
        )
        first_path = tmp_path / "first.json"
        second_path = tmp_path / "second.json"
        c1 = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        c1["margin"]["per_trade_target_margin_fraction"] = 0.01
        write_config(first_path, c1, [], "test")
        c2 = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        c2["margin"]["per_trade_target_margin_fraction"] = 0.99
        write_config(second_path, c2, [], "test")

        cfg1 = load_analyzer_config(path=str(first_path))
        cfg2 = load_analyzer_config(path=str(second_path))
        assert cfg1["margin"]["per_trade_target_margin_fraction"] == 0.01
        assert cfg2["margin"]["per_trade_target_margin_fraction"] == 0.01

    def test_reset_allows_rereading(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            _reset_analyzer_config_cache,
            load_analyzer_config,
        )
        p = tmp_path / "analyzer_config.json"
        c1 = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        c1["margin"]["per_trade_target_margin_fraction"] = 0.01
        write_config(p, c1, [], "test")

        cfg1 = load_analyzer_config(path=str(p))
        assert cfg1["margin"]["per_trade_target_margin_fraction"] == 0.01

        c2 = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        c2["margin"]["per_trade_target_margin_fraction"] = 0.09
        write_config(p, c2, [], "test")

        _reset_analyzer_config_cache()
        cfg2 = load_analyzer_config(path=str(p))
        assert cfg2["margin"]["per_trade_target_margin_fraction"] == 0.09

    def test_missing_section_backfilled_from_defaults(self, tmp_path):
        """A partial config file gets unlisted sections from defaults."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import load_analyzer_config
        p = tmp_path / "analyzer_config.json"
        partial = {
            "schema_version": 1,
            "margin": {"per_trade_target_margin_fraction": 0.03},
            # other sections intentionally absent
        }
        write_config(p, partial, [], "test")

        cfg = load_analyzer_config(path=str(p))
        assert cfg["margin"]["per_trade_target_margin_fraction"] == 0.03
        # other margin field backfilled
        assert cfg["margin"]["monthly_return_target_fraction"] == 0.10
        # whole sections backfilled
        assert cfg["windows"]["pricing_reports"] == 2
        assert cfg["scoring"]["signal_thresholds"]["strong_max_risk_pct"] == 10

    def test_newer_schema_version_falls_back(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            analyzer_config_source,
            load_analyzer_config,
        )
        p = tmp_path / "analyzer_config.json"
        content = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        content["schema_version"] = 99
        write_config(p, content, [], "test")

        cfg = load_analyzer_config(path=str(p))
        # Fell back to factory defaults rather than parsing a newer file.
        assert cfg["schema_version"] == 1
        assert analyzer_config_source() == "fallback"

    def test_fallback_has_same_shape_as_factory(self, tmp_path):
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            load_analyzer_config,
        )
        missing = tmp_path / "nope.json"
        cfg = load_analyzer_config(path=str(missing))

        def shape(d, prefix=""):
            out = set()
            for k, v in d.items():
                p = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    out |= shape(v, p)
                else:
                    out.add(p)
            return out

        assert shape(cfg) == shape(ANALYZER_CONFIG_FACTORY_DEFAULTS)

    def test_fallback_does_not_leak_mutations(self, tmp_path):
        """Mutating the returned dict must not affect the next fallback."""
        from scripts.grailzee_common import (
            _reset_analyzer_config_cache,
            load_analyzer_config,
        )
        missing = tmp_path / "nope.json"
        cfg1 = load_analyzer_config(path=str(missing))
        cfg1["margin"]["per_trade_target_margin_fraction"] = 999

        _reset_analyzer_config_cache()
        cfg2 = load_analyzer_config(path=str(missing))
        assert cfg2["margin"]["per_trade_target_margin_fraction"] == 0.05

    def test_unexpected_exception_propagates(self, tmp_path, monkeypatch):
        """A.cleanup.2 Item 9: narrowed except tuple propagates types
        the loader is not prepared to handle. TypeError from read_config
        must reach the caller rather than being silently swallowed."""
        import pytest
        from scripts import config_helper
        from scripts.grailzee_common import load_analyzer_config

        p = tmp_path / "analyzer_config.json"
        p.write_text('{"schema_version": 1}')

        def _boom(_path):
            raise TypeError("synthetic unexpected")

        monkeypatch.setattr(config_helper, "read_config", _boom)
        with pytest.raises(TypeError, match="synthetic unexpected"):
            load_analyzer_config(path=str(p))


class TestMaxBuyFormulaReadsFromConfig:
    """max_buy_nr/max_buy_reserve/adjusted_max_buy read target margin
    from analyzer_config, not the TARGET_MARGIN constant."""

    def setup_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def teardown_method(self) -> None:
        from scripts.grailzee_common import _reset_analyzer_config_cache
        _reset_analyzer_config_cache()

    def test_max_buy_nr_uses_config_margin(self, tmp_path):
        """A 10% margin in the config shifts max_buy_nr correctly."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            ANALYZER_CONFIG_FACTORY_DEFAULTS,
            load_analyzer_config,
            max_buy_nr,
        )
        p = tmp_path / "analyzer_config.json"
        content = json.loads(json.dumps(ANALYZER_CONFIG_FACTORY_DEFAULTS))
        content["margin"]["per_trade_target_margin_fraction"] = 0.10
        write_config(p, content, [], "test")
        load_analyzer_config(path=str(p))  # prime cache

        # (3349 - 149) / 1.10 = 2909.09 -> rounded to 2910
        assert max_buy_nr(3349) == 2910

    def test_fallback_matches_05_constant(self, tmp_path):
        """With no config file, max_buy_nr uses the 0.05 factory default."""
        from scripts.grailzee_common import max_buy_nr
        # Same input as original test: (3200 - 149) / 1.05 = 2905.71 -> 2910
        assert max_buy_nr(3200) == 2910


# ═══════════════════════════════════════════════════════════════════════
# Phase A.4 — load_sourcing_rules
# ═══════════════════════════════════════════════════════════════════════


class TestLoadSourcingRules:
    """Memoized loader mirroring load_analyzer_config. file-absent
    fallback, cache-once-per-process, reset helper."""

    def setup_method(self) -> None:
        from scripts.grailzee_common import _reset_sourcing_rules_cache
        _reset_sourcing_rules_cache()

    def teardown_method(self) -> None:
        from scripts.grailzee_common import _reset_sourcing_rules_cache
        _reset_sourcing_rules_cache()

    def test_file_present_path(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
            sourcing_rules_source,
        )
        p = tmp_path / "sourcing_rules.json"
        content = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        content["condition_minimum"] = "Excellent"
        write_config(p, content, [], "test")

        cfg = load_sourcing_rules(path=str(p))
        assert cfg["condition_minimum"] == "Excellent"
        assert sourcing_rules_source() == "file"

    def test_file_absent_falls_back_to_defaults(self, tmp_path):
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
            sourcing_rules_source,
        )
        missing = tmp_path / "nope.json"

        cfg = load_sourcing_rules(path=str(missing))
        assert cfg["condition_minimum"] == SOURCING_RULES_FACTORY_DEFAULTS["condition_minimum"]
        assert cfg["keyword_filters"] == SOURCING_RULES_FACTORY_DEFAULTS["keyword_filters"]
        assert sourcing_rules_source() == "fallback"

    def test_malformed_file_falls_back(self, tmp_path):
        from scripts.grailzee_common import (
            load_sourcing_rules,
            sourcing_rules_source,
        )
        p = tmp_path / "sourcing_rules.json"
        p.write_text("{not valid json")

        cfg = load_sourcing_rules(path=str(p))
        assert cfg["condition_minimum"] == "Very Good"
        assert sourcing_rules_source() == "fallback"

    def test_cache_returns_same_dict_across_calls(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
        )
        p = tmp_path / "sourcing_rules.json"
        content = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        write_config(p, content, [], "test")

        first = load_sourcing_rules(path=str(p))
        second = load_sourcing_rules(path=str(p))
        assert first is second

    def test_cache_ignores_path_after_first_call(self, tmp_path):
        """First-call-wins. Documents the foot-gun for mid-process readers."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
        )
        p1 = tmp_path / "first.json"
        p2 = tmp_path / "second.json"
        c1 = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        c1["condition_minimum"] = "Like New"
        write_config(p1, c1, [], "test")
        c2 = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        c2["condition_minimum"] = "Fair"
        write_config(p2, c2, [], "test")

        cfg1 = load_sourcing_rules(path=str(p1))
        cfg2 = load_sourcing_rules(path=str(p2))
        assert cfg1["condition_minimum"] == "Like New"
        assert cfg2["condition_minimum"] == "Like New"

    def test_reset_allows_rereading(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            _reset_sourcing_rules_cache,
            load_sourcing_rules,
        )
        p = tmp_path / "sourcing_rules.json"
        c1 = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        c1["condition_minimum"] = "Like New"
        write_config(p, c1, [], "test")

        cfg1 = load_sourcing_rules(path=str(p))
        assert cfg1["condition_minimum"] == "Like New"

        c2 = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        c2["condition_minimum"] = "BNIB"
        write_config(p, c2, [], "test")

        _reset_sourcing_rules_cache()
        cfg2 = load_sourcing_rules(path=str(p))
        assert cfg2["condition_minimum"] == "BNIB"

    def test_missing_section_backfilled_from_defaults(self, tmp_path):
        """A partial file gets unlisted sections backfilled."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import load_sourcing_rules
        p = tmp_path / "sourcing_rules.json"
        partial = {
            "schema_version": 1,
            "condition_minimum": "Excellent",
            # papers_required + keyword_filters intentionally absent
        }
        write_config(p, partial, [], "test")

        cfg = load_sourcing_rules(path=str(p))
        assert cfg["condition_minimum"] == "Excellent"
        # backfilled from factory defaults
        assert cfg["papers_required"] is True
        assert "full set" in cfg["keyword_filters"]["include"]

    def test_newer_schema_version_falls_back(self, tmp_path):
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
            sourcing_rules_source,
        )
        p = tmp_path / "sourcing_rules.json"
        content = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        content["schema_version"] = 99
        write_config(p, content, [], "test")

        cfg = load_sourcing_rules(path=str(p))
        assert cfg["schema_version"] == 1
        assert sourcing_rules_source() == "fallback"

    def test_fallback_has_same_shape_as_factory(self, tmp_path):
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
        )
        cfg = load_sourcing_rules(path=str(tmp_path / "nope.json"))

        def shape(d, prefix=""):
            out = set()
            for k, v in d.items():
                p = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    out |= shape(v, p)
                else:
                    out.add(p)
            return out

        assert shape(cfg) == shape(SOURCING_RULES_FACTORY_DEFAULTS)

    def test_fallback_does_not_leak_mutations(self, tmp_path):
        """Mutating the returned dict must not poison the next fallback."""
        from scripts.grailzee_common import (
            _reset_sourcing_rules_cache,
            load_sourcing_rules,
        )
        missing = tmp_path / "nope.json"
        cfg1 = load_sourcing_rules(path=str(missing))
        cfg1["condition_minimum"] = "CLOBBERED"

        _reset_sourcing_rules_cache()
        cfg2 = load_sourcing_rules(path=str(missing))
        assert cfg2["condition_minimum"] == "Very Good"

    def test_mid_run_disk_edit_is_ignored(self, tmp_path):
        """Documents the cycle-boundary semantic: a strategy edit
        landing mid-run does not flip thresholds underneath the brief
        build loop. First call wins; re-read requires explicit reset."""
        from scripts.config_helper import write_config
        from scripts.grailzee_common import (
            SOURCING_RULES_FACTORY_DEFAULTS,
            load_sourcing_rules,
        )
        p = tmp_path / "sourcing_rules.json"
        original = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        write_config(p, original, [], "test")

        first = load_sourcing_rules(path=str(p))
        assert first["condition_minimum"] == "Very Good"

        # Simulate a strategy commit landing mid-run.
        mutated = json.loads(json.dumps(SOURCING_RULES_FACTORY_DEFAULTS))
        mutated["condition_minimum"] = "Excellent"
        write_config(p, mutated, [], "test")

        # No reset: cached dict still wins.
        second = load_sourcing_rules(path=str(p))
        assert second["condition_minimum"] == "Very Good"
        assert first is second

    def test_unexpected_exception_propagates(self, tmp_path, monkeypatch):
        """A.cleanup.2 Item 9: narrowed except tuple propagates types
        the loader is not prepared to handle. TypeError from read_config
        must reach the caller rather than being silently swallowed."""
        import pytest
        from scripts import config_helper
        from scripts.grailzee_common import load_sourcing_rules

        p = tmp_path / "sourcing_rules.json"
        p.write_text('{"schema_version": 1}')

        def _boom(_path):
            raise TypeError("synthetic unexpected")

        monkeypatch.setattr(config_helper, "read_config", _boom)
        with pytest.raises(TypeError, match="synthetic unexpected"):
            load_sourcing_rules(path=str(p))
