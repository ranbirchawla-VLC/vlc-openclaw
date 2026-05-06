"""Tests for scripts.analyze_buckets; v3 four-axis bucket construction and scoring.

Phase 2b; new module. Covers:
- bucket_key serialization (auction_type lowercasing, format)
- build_buckets grouping (correct groups, no empty buckets)
- score_bucket: below-threshold carries Low data with correct field set
- score_bucket: above-threshold delegates to analyze_reference
- named_special threading (longest-slug-wins, alphabetical tiebreak)
- _st_pct_for_rows: mean and None-fallback
- score_all_references: OTel span attributes, references/dj_configs/unnamed shape
- DJ config path: classify_dj_config classifies; buckets per config
- color=unknown treated as valid keying value
- W2-scale smoke test via load_and_canonicalize on real fixture CSV
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = V2_ROOT / "tests" / "fixtures"
CSV_APR = str(FIXTURES / "grailzee_2026-04-06.csv")
NAME_CACHE = str(FIXTURES / "name_cache_seed.json")

from scripts.analyze_buckets import (
    _named_special_for_bucket,
    _row_to_sale,
    _score_dj_configs,
    _st_pct_for_rows,
    bucket_key,
    build_buckets,
    run,
    score_all_references,
    score_bucket,
)
from scripts.ingest import CanonicalRow


# ─── Helpers ──────────────────────────────────────────────────────────


def _row(
    reference: str = "79830RB",
    dial_numerals: str = "Arabic",
    auction_type: str = "NR",
    dial_color: str = "black",
    sold_for: float = 3200.0,
    condition: str = "Excellent",
    papers: str = "Yes",
    brand: str = "Tudor",
    sell_through_pct: float | None = 0.6,
    named_special: str | None = None,
    auction_descriptor: str = "Tudor BB GMT Arabic Black NR",
) -> CanonicalRow:
    return CanonicalRow(
        reference=reference,
        sold_at=date(2026, 4, 6),
        sold_for=sold_for,
        auction_type=auction_type,  # type: ignore[arg-type]
        auction_descriptor=auction_descriptor,
        dial_numerals=dial_numerals,  # type: ignore[arg-type]
        dial_color=dial_color,
        named_special=named_special,
        brand=brand,
        model="BB GMT",
        condition=condition,
        papers=papers,
        year="2022",
        box="Yes",
        sell_through_pct=sell_through_pct,
        url="",
        source_report="grailzee_2026-04-06.csv",
        source_row_index=0,
    )


def _rows(n: int, **kwargs) -> list[CanonicalRow]:
    """Build n rows with optional field overrides; sold_for steps by 100."""
    return [_row(sold_for=3000.0 + i * 100.0, **kwargs) for i in range(n)]


# ─── bucket_key ───────────────────────────────────────────────────────


class TestBucketKey:
    def test_format(self):
        r = _row(dial_numerals="Arabic", auction_type="NR", dial_color="black")
        assert bucket_key(r) == "arabic|nr|black"

    def test_auction_type_lowercased(self):
        assert bucket_key(_row(auction_type="NR")) == "arabic|nr|black"
        assert bucket_key(_row(auction_type="RES")) == "arabic|res|black"

    def test_dial_numerals_lowercased(self):
        """Bug 1 fix: all three axes lowercased in serialized key."""
        assert bucket_key(_row(dial_numerals="Roman")) == "roman|nr|black"
        assert bucket_key(_row(dial_numerals="Diamond")) == "diamond|nr|black"
        assert bucket_key(_row(dial_numerals="No Numerals")) == "no numerals|nr|black"

    def test_unknown_color(self):
        assert bucket_key(_row(dial_color="unknown")) == "arabic|nr|unknown"

    def test_multiword_color(self):
        assert bucket_key(_row(dial_color="blue sunburst")) == "arabic|nr|blue sunburst"

    def test_body_case_preserved_key_lowered(self):
        """Bucket dict key is all-lowercase; bucket body fields keep
        canonical case on dial_numerals. Strong regression guard: if a
        future change lowers the body too, this catches it."""
        rows = _rows(3, dial_numerals="Arabic", auction_type="NR", dial_color="black")
        buckets = build_buckets(rows)
        assert list(buckets.keys()) == ["arabic|nr|black"]
        bd = score_bucket(rows)
        assert bd["dial_numerals"] == "Arabic"  # body preserves canonical case
        assert bd["auction_type"] == "nr"
        assert bd["dial_color"] == "black"


# ─── build_buckets ────────────────────────────────────────────────────


class TestBuildBuckets:
    def test_single_group(self):
        rows = _rows(3)
        buckets = build_buckets(rows)
        assert len(buckets) == 1
        assert "arabic|nr|black" in buckets
        assert len(buckets["arabic|nr|black"]) == 3

    def test_two_groups_by_auction_type(self):
        nr_rows = _rows(2, auction_type="NR")
        res_rows = _rows(2, auction_type="RES")
        buckets = build_buckets(nr_rows + res_rows)
        assert len(buckets) == 2
        assert len(buckets["arabic|nr|black"]) == 2
        assert len(buckets["arabic|res|black"]) == 2

    def test_two_groups_by_dial_numerals(self):
        arabic = _rows(2, dial_numerals="Arabic")
        roman = _rows(2, dial_numerals="Roman")
        buckets = build_buckets(arabic + roman)
        assert len(buckets) == 2

    def test_two_groups_by_dial_color(self):
        black = _rows(2, dial_color="black")
        blue = _rows(2, dial_color="blue")
        buckets = build_buckets(black + blue)
        assert len(buckets) == 2

    def test_no_empty_buckets(self):
        rows = _rows(3)
        buckets = build_buckets(rows)
        assert all(len(v) > 0 for v in buckets.values())

    def test_empty_input(self):
        assert build_buckets([]) == {}

    def test_unknown_color_is_own_bucket(self):
        known = _rows(2, dial_color="black")
        unknown = _rows(2, dial_color="unknown")
        buckets = build_buckets(known + unknown)
        assert "arabic|nr|unknown" in buckets
        assert "arabic|nr|black" in buckets


# ─── _named_special_for_bucket ────────────────────────────────────────


class TestNamedSpecialForBucket:
    def test_none_when_all_absent(self):
        rows = _rows(3, named_special=None)
        assert _named_special_for_bucket(rows) is None

    def test_single_value_returned(self):
        rows = _rows(3, named_special="panda")
        assert _named_special_for_bucket(rows) == "panda"

    def test_longest_wins(self):
        rows = [
            _row(named_special="panda"),
            _row(named_special="mother_of_pearl"),
            _row(named_special="panda"),
        ]
        assert _named_special_for_bucket(rows) == "mother_of_pearl"

    def test_alphabetical_tiebreak(self):
        rows = [
            _row(named_special="panda"),
            _row(named_special="tapestry"),  # same length as "skeleton" but different
            _row(named_special="aventurine"),  # same length as "tapestry"
        ]
        # "tapestry" and "aventurine" are both 9 chars; "aventurine" < "tapestry" alpha
        assert _named_special_for_bucket(rows) == "aventurine"

    def test_none_mixed_with_values(self):
        rows = [
            _row(named_special=None),
            _row(named_special="panda"),
            _row(named_special=None),
        ]
        assert _named_special_for_bucket(rows) == "panda"


# ─── _st_pct_for_rows ─────────────────────────────────────────────────


class TestStPctForRows:
    def test_mean_of_populated(self):
        rows = [_row(sell_through_pct=0.4), _row(sell_through_pct=0.6)]
        assert _st_pct_for_rows(rows) == pytest.approx(0.5)

    def test_none_when_all_absent(self):
        rows = [_row(sell_through_pct=None), _row(sell_through_pct=None)]
        assert _st_pct_for_rows(rows) is None

    def test_partial_population(self):
        rows = [_row(sell_through_pct=None), _row(sell_through_pct=0.8)]
        assert _st_pct_for_rows(rows) == pytest.approx(0.8)


# ─── score_bucket ─────────────────────────────────────────────────────


class TestScoreBucket:
    def test_below_threshold_carries_low_data(self):
        rows = _rows(2)
        bd = score_bucket(rows)
        assert bd["signal"] == "Low data"
        assert bd["median"] is None
        assert bd["max_buy_nr"] is None
        assert bd["max_buy_res"] is None

    def test_below_threshold_volume_populated(self):
        rows = _rows(2)
        bd = score_bucket(rows)
        assert bd["volume"] == 2

    def test_below_threshold_condition_mix_populated(self):
        rows = _rows(2)
        bd = score_bucket(rows)
        assert isinstance(bd["condition_mix"], dict)
        assert len(bd["condition_mix"]) > 0

    def test_above_threshold_has_median(self):
        rows = _rows(5)
        bd = score_bucket(rows)
        assert bd["signal"] != "Low data"
        assert bd["median"] is not None

    def test_above_threshold_key_fields(self):
        rows = _rows(5)
        bd = score_bucket(rows)
        expected = {
            "dial_numerals", "auction_type", "dial_color", "named_special",
            "volume", "st_pct", "condition_mix", "signal", "median",
            "max_buy_nr", "max_buy_res", "risk_nr", "capital_required_nr",
            "capital_required_res", "expected_net_at_median_nr",
            "expected_net_at_median_res",
        }
        assert expected <= set(bd.keys())

    def test_named_special_threaded(self):
        rows = _rows(3, named_special="panda")
        bd = score_bucket(rows)
        assert bd["named_special"] == "panda"

    def test_named_special_none_when_absent(self):
        rows = _rows(3, named_special=None)
        bd = score_bucket(rows)
        assert bd["named_special"] is None

    def test_axes_on_bucket(self):
        rows = _rows(3, dial_numerals="Roman", auction_type="RES", dial_color="blue")
        bd = score_bucket(rows)
        assert bd["dial_numerals"] == "Roman"
        assert bd["auction_type"] == "res"
        assert bd["dial_color"] == "blue"

    def test_st_pct_mean(self):
        rows = [
            _row(sell_through_pct=0.4),
            _row(sell_through_pct=0.6),
            _row(sell_through_pct=0.8),
        ]
        bd = score_bucket(rows)
        assert bd["st_pct"] == pytest.approx(0.6)

    def test_unknown_color_scores(self):
        rows = _rows(5, dial_color="unknown")
        bd = score_bucket(rows)
        assert bd["dial_color"] == "unknown"
        assert bd["signal"] != "Low data"
        assert bd["median"] is not None


# ─── score_all_references ─────────────────────────────────────────────


class TestScoreAllReferences:
    def test_return_shape(self):
        rows = _rows(3)
        result = score_all_references(rows, {})
        assert set(result.keys()) == {"references", "dj_configs", "unnamed"}

    def test_reference_present(self):
        rows = _rows(3)
        result = score_all_references(rows, {})
        assert "79830RB" in result["references"]

    def test_reference_shape(self):
        rows = _rows(3)
        result = score_all_references(rows, {})
        rd = result["references"]["79830RB"]
        assert "brand" in rd
        assert "model" in rd
        assert "buckets" in rd
        assert isinstance(rd["buckets"], dict)

    def test_bucket_inside_reference(self):
        rows = _rows(3)
        result = score_all_references(rows, {})
        rd = result["references"]["79830RB"]
        assert len(rd["buckets"]) == 1
        bk = "arabic|nr|black"
        assert bk in rd["buckets"]

    def test_named_from_name_cache(self):
        rows = _rows(3)
        name_cache = {"79830RB": {"brand": "Tudor", "model": "BB GMT"}}
        result = score_all_references(rows, name_cache)
        rd = result["references"]["79830RB"]
        assert rd["named"] is True

    def test_not_named_when_absent(self):
        rows = _rows(3)
        result = score_all_references(rows, {})
        rd = result["references"]["79830RB"]
        assert rd["named"] is False
        assert "79830RB" in result["unnamed"]

    def test_multi_reference(self):
        rows_a = _rows(3, reference="A")
        rows_b = _rows(3, reference="B")
        result = score_all_references(rows_a + rows_b, {})
        assert "A" in result["references"]
        assert "B" in result["references"]

    def test_below_threshold_bucket_in_result(self):
        rows = _rows(2)
        result = score_all_references(rows, {})
        rd = result["references"]["79830RB"]
        bd = next(iter(rd["buckets"].values()))
        assert bd["signal"] == "Low data"

    def test_two_buckets_for_two_auction_types(self):
        nr = _rows(3, auction_type="NR")
        res = _rows(3, auction_type="RES")
        result = score_all_references(nr + res, {})
        rd = result["references"]["79830RB"]
        assert len(rd["buckets"]) == 2

    def test_empty_rows_returns_empty_references(self):
        result = score_all_references([], {})
        assert result["references"] == {}
        assert result["dj_configs"] == {}
        assert result["unnamed"] == []


# ─── alt_refs expansion ───────────────────────────────────────────────


class TestAltRefsExpansion:
    """alt_refs in the name cache are expanded before the scoring loop.

    Regression guard: a Pro-report ref that appears under a different
    format than the cache primary key (e.g. M79830RB vs 79830RB) must
    still resolve to named=True when the curator listed it as an alt_ref.
    """

    def test_alt_ref_resolves_to_named(self):
        """Ref matching an alt_ref entry is marked named=True."""
        rows = _rows(3, reference="M79830RB")
        cache = {"79830RB": {"brand": "Tudor", "model": "BB GMT", "alt_refs": ["M79830RB"]}}
        result = score_all_references(rows, cache)
        rd = result["references"]["M79830RB"]
        assert rd["named"] is True

    def test_alt_ref_carries_brand_and_model(self):
        """Brand and model come from the primary cache entry, not the row."""
        rows = _rows(3, reference="M79830RB")
        cache = {"79830RB": {"brand": "Tudor", "model": "BB GMT Pepsi", "alt_refs": ["M79830RB"]}}
        result = score_all_references(rows, cache)
        rd = result["references"]["M79830RB"]
        assert rd["brand"] == "Tudor"
        assert rd["model"] == "BB GMT Pepsi"

    def test_alt_ref_not_in_unnamed(self):
        """A ref resolved via alt_refs does not appear in the unnamed list."""
        rows = _rows(3, reference="M79830RB")
        cache = {"79830RB": {"brand": "Tudor", "model": "BB GMT", "alt_refs": ["M79830RB"]}}
        result = score_all_references(rows, cache)
        assert "M79830RB" not in result["unnamed"]

    def test_primary_key_still_works(self):
        """Primary key lookup is unaffected by alt_refs expansion."""
        rows = _rows(3, reference="79830RB")
        cache = {"79830RB": {"brand": "Tudor", "model": "BB GMT", "alt_refs": ["M79830RB"]}}
        result = score_all_references(rows, cache)
        assert result["references"]["79830RB"]["named"] is True

    def test_primary_key_wins_over_alt_ref(self):
        """If a ref appears as both a primary key and an alt_ref of another
        entry, the primary key entry takes precedence."""
        rows = _rows(3, reference="SHARED")
        cache = {
            "SHARED": {"brand": "BrandA", "model": "ModelA"},
            "OTHER":  {"brand": "BrandB", "model": "ModelB", "alt_refs": ["SHARED"]},
        }
        result = score_all_references(rows, cache)
        rd = result["references"]["SHARED"]
        assert rd["brand"] == "BrandA"

    def test_entry_without_alt_refs_unaffected(self):
        """Entries with no alt_refs key work exactly as before."""
        rows = _rows(3, reference="126610LN")
        cache = {"126610LN": {"brand": "Rolex", "model": "Submariner Date"}}
        result = score_all_references(rows, cache)
        assert result["references"]["126610LN"]["named"] is True


# ─── DJ config path ────────────────────────────────────────────────────


class TestDJConfigPath:
    def test_no_dj_configs_when_126300_absent(self):
        rows = _rows(5, reference="79830RB")
        result = score_all_references(rows, {})
        assert result["dj_configs"] == {}

    def test_no_dj_configs_when_config_breakout_not_set(self):
        rows = _rows(5, reference="126300", auction_descriptor="DJ 41 Black/Oyster NR")
        name_cache = {"126300": {"brand": "Rolex", "model": "DJ 41"}}
        result = score_all_references(rows, name_cache)
        assert result["dj_configs"] == {}

    def test_dj_configs_when_config_breakout_set(self):
        rows = _rows(
            5, reference="126300",
            auction_descriptor="Rolex Datejust 41 Black/Oyster Strap NR",
        )
        name_cache = {"126300": {"brand": "Rolex", "model": "DJ 41", "config_breakout": True}}
        result = score_all_references(rows, name_cache)
        assert len(result["dj_configs"]) >= 1

    def test_dj_config_entry_has_buckets(self):
        rows = _rows(
            5, reference="126300",
            auction_descriptor="Rolex Datejust 41 Black/Oyster Strap NR",
        )
        name_cache = {"126300": {"brand": "Rolex", "model": "DJ 41", "config_breakout": True}}
        result = score_all_references(rows, name_cache)
        for cfg_entry in result["dj_configs"].values():
            assert "buckets" in cfg_entry
            assert isinstance(cfg_entry["buckets"], dict)


# ─── _row_to_sale ──────────────────────────────────────────────────────


class TestRowToSale:
    def test_keys(self):
        sale = _row_to_sale(_row())
        assert set(sale.keys()) == {
            "price", "condition", "papers", "reference", "make", "title", "sell_through_pct",
        }

    def test_values(self):
        r = _row(sold_for=3500.0, condition="Very Good", papers="No", brand="Tudor")
        sale = _row_to_sale(r)
        assert sale["price"] == 3500.0
        assert sale["condition"] == "Very Good"
        assert sale["papers"] == "No"
        assert sale["make"] == "Tudor"


# ─── W2-scale smoke test ──────────────────────────────────────────────


class TestW2ScaleSmoke:
    """Light integration smoke test using real fixture CSV via ingest."""

    def test_run_on_fixture_csv(self):
        from scripts.ingest import load_and_canonicalize
        from scripts.grailzee_common import load_name_cache

        rows, summary = load_and_canonicalize([Path(CSV_APR)])
        assert summary.canonical_rows_emitted > 0

        name_cache = load_name_cache(NAME_CACHE)
        result = run(rows, NAME_CACHE)

        assert len(result["references"]) > 100
        assert isinstance(result["dj_configs"], dict)
        assert isinstance(result["unnamed"], list)

    def test_fixture_has_scored_buckets(self):
        from scripts.ingest import load_and_canonicalize

        rows, _ = load_and_canonicalize([Path(CSV_APR)])
        result = run(rows, NAME_CACHE)

        scored = sum(
            1 for rd in result["references"].values()
            for bd in rd["buckets"].values()
            if bd.get("signal") != "Low data"
        )
        assert scored >= 100

    def test_all_buckets_have_required_keys(self):
        from scripts.ingest import load_and_canonicalize

        rows, _ = load_and_canonicalize([Path(CSV_APR)])
        result = run(rows, NAME_CACHE)

        required = {
            "dial_numerals", "auction_type", "dial_color", "named_special",
            "volume", "st_pct", "condition_mix", "signal",
        }
        for ref, rd in result["references"].items():
            for bk, bd in rd["buckets"].items():
                missing = required - set(bd.keys())
                assert not missing, f"{ref}/{bk} missing keys: {missing}"
