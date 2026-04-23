"""Tests for scripts.ingest (Phase 2a v3 canonical row layer)."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest import (
    BASE_COLOR_VOCABULARY,
    CanonicalRow,
    EXPECTED_CSV_COLUMNS,
    IngestSummary,
    NAMED_SPECIAL_SOURCE_PATTERNS,
    NAMED_SPECIAL_VOCABULARY,
    NUMERALS_CANONICAL,
    canonicalize_dial_numerals,
    detect_auction_type,
    detect_named_special,
    ingest_and_archive,
    is_handbag,
    load_and_canonicalize,
    parse_dial_color,
)


NBSP = " "


# ─── Test fixture helpers ─────────────────────────────────────────────


CSV_HEADER = ",".join([
    "date_sold", "make", "reference", "title", "condition",
    "papers", "sold_price", "sell_through_pct",
    "model", "year", "box", "dial_numerals_raw", "url",
])


def _row(
    *,
    date_sold: str = "2026-04-01",
    make: str = "Rolex",
    reference: str = "126610LN",
    title: str = "Rolex Submariner Date 41MM Black Dial Oyster Bracelet (126610LN)",
    condition: str = "Very Good",
    papers: str = "Yes",
    sold_price: str = "12000.0",
    sell_through_pct: str = "0.45",
    model: str = "Rolex Submariner",
    year: str = "2025",
    box: str = "Yes",
    dial_numerals_raw: str = "No Numerals",
    url: str = "https://grailzee.com/x",
) -> dict[str, str]:
    return {
        "date_sold": date_sold, "make": make, "reference": reference,
        "title": title, "condition": condition, "papers": papers,
        "sold_price": sold_price, "sell_through_pct": sell_through_pct,
        "model": model, "year": year, "box": box,
        "dial_numerals_raw": dial_numerals_raw, "url": url,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER.split(","))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return path


# ─── Vocabulary sanity ────────────────────────────────────────────────


class TestVocabulary:
    def test_named_special_vocabulary_is_thirteen(self):
        assert len(NAMED_SPECIAL_VOCABULARY) == 13

    def test_every_source_pattern_maps_to_known_slug(self):
        for slug in NAMED_SPECIAL_SOURCE_PATTERNS.values():
            assert slug in NAMED_SPECIAL_VOCABULARY

    def test_csv_columns_match_post_patch_emission(self):
        assert EXPECTED_CSV_COLUMNS == {
            "date_sold", "make", "reference", "title", "condition",
            "papers", "sold_price", "sell_through_pct",
            "model", "year", "box", "dial_numerals_raw", "url",
        }


# ─── Numerals cascade ─────────────────────────────────────────────────


class TestNumeralsCascade:
    @pytest.mark.parametrize("raw,expected", [
        ("Arabic Numerals", "Arabic"),
        ("Roman Numerals", "Roman"),
        ("Diamond Numerals", "Diamond"),
        ("No Numerals", "No Numerals"),
        ("arabic numerals", "Arabic"),  # case
        ("ARABIC NUMERALS", "Arabic"),
        ("Arabic Numerals.", "Arabic"),  # trailing punct
        ("Arabic Numerals,", "Arabic"),
        ("Arabic", "Arabic"),  # singular bare
    ])
    def test_canonical_match(self, raw, expected):
        v, status = canonicalize_dial_numerals(raw)
        assert v == expected
        assert status == "ok"

    def test_blank_drops(self):
        for raw in (None, "", "   ", "\t"):
            v, status = canonicalize_dial_numerals(raw)
            assert v is None
            assert status == "blank_drop"

    def test_slash_combined_takes_first(self):
        # Decision 6
        v, status = canonicalize_dial_numerals("Arabic/Roman Numerals")
        assert v == "Arabic"
        assert status == "slash_canonicalized"
        v, status = canonicalize_dial_numerals("Roman/Arabic Numerals")
        assert v == "Roman"
        assert status == "slash_canonicalized"

    def test_slash_combined_diamond_first(self):
        v, status = canonicalize_dial_numerals("Diamond/Sapphire Numerals")
        assert v == "Diamond"
        assert status == "slash_canonicalized"

    def test_keyword_fallback(self):
        v, status = canonicalize_dial_numerals("Diamond")
        assert v == "Diamond"
        assert status == "ok"

    # Operator plan-review 2026-04-24 cascade extensions
    def test_no_numbers_typo_canonicalizes(self):
        v, status = canonicalize_dial_numerals("No Numbers")
        assert v == "No Numerals"
        assert status == "ok"

    def test_abaric_typo_canonicalizes(self):
        for raw in ("Abaric Numerals", "Abaric Numeral", "abaric numerals"):
            v, status = canonicalize_dial_numerals(raw)
            assert v == "Arabic"
            assert status == "ok"

    @pytest.mark.parametrize("raw", [
        "Sapphire Numerals", "Gemstone Numerals", "Plexiglass", "Other",
    ])
    def test_fallthrough_drops_per_operator_plan_review(self, raw):
        v, status = canonicalize_dial_numerals(raw)
        assert v is None
        assert status == "fallthrough_drop"


# ─── Asset-class filter ───────────────────────────────────────────────


class TestAssetClass:
    def test_louis_vuitton_handbag_matches(self):
        assert is_handbag(
            "2011 Louis Vuitton On My Side 9.6 x 12 x 5.5IN Leather"
        )
        assert is_handbag("Louis Vuitton Liv Pochette 5.3 x 9.6IN Damier")
        assert is_handbag("LV Neverfull Reversible 11 x 18IN Leather")

    def test_watch_with_mm_does_not_match(self):
        assert not is_handbag("Rolex Submariner 41MM Black Dial")
        assert not is_handbag("Tudor Black Bay 39MM Steel Bracelet")

    def test_single_dimension_does_not_match(self):
        # Multi-dimension is required by the regex
        assert not is_handbag("Some 7IN strap accessory")

    def test_lowercase_in_does_not_match(self):
        # Live data uses uppercase IN; structural exclusion
        assert not is_handbag("Random 11 x 18in Item")


# ─── Dial-color parsing ───────────────────────────────────────────────


class TestDialColor:
    def test_clean_base_color_before_dial(self):
        assert parse_dial_color(
            "Rolex Submariner 41MM Black Dial Oyster Bracelet"
        ) == "black"
        assert parse_dial_color(
            "Rolex Datejust 41MM Champagne Dial Oyster Bracelet"
        ) == "champagne"

    def test_color_in_model_name_creates_window_ambiguity(self):
        # "Tudor Black Bay" puts "black" in the window for "Blue Dial".
        # Two distinct colors -> "unknown". This is the conservative
        # parser behavior; Phase 1 stratified family parse rates
        # (tudor_sport 88%) reflect this kind of false-multi-hit.
        assert parse_dial_color(
            "Tudor Black Bay 41MM Blue Dial Steel Bracelet"
        ) == "unknown"

    def test_no_dial_anchor_returns_unknown(self):
        # No literal "dial" word
        assert parse_dial_color("Vintage Rolex no anchor word here") == "unknown"

    def test_no_color_in_window_returns_unknown(self):
        assert parse_dial_color("2010 Rolex GMT Master II Dial Edition") == "unknown"

    def test_color_outside_window_returns_unknown(self):
        # The "Black" is way before the 4-word window from "dial"
        assert parse_dial_color(
            "Black case 2010 some long descriptor here many extra words Dial"
        ) == "unknown"

    def test_multiple_distinct_colors_in_window_returns_unknown(self):
        # "Black White Dial" -> two base colors in the same 4-word window
        assert parse_dial_color("Rolex Black White Dial") == "unknown"

    def test_repeated_same_color_dedupes_to_one(self):
        assert parse_dial_color("Rolex Black Black Dial") == "black"

    def test_anchored_to_first_dial(self):
        # Two "dial" anchors; parser uses first
        result = parse_dial_color(
            "Rolex Black Dial Custom Aftermarket Blue Dial"
        )
        assert result == "black"

    def test_case_insensitive(self):
        assert parse_dial_color("Rolex BLUE DIAL") == "blue"
        assert parse_dial_color("Rolex blue dial") == "blue"


# ─── Named-special detection ──────────────────────────────────────────


class TestNamedSpecial:
    @pytest.mark.parametrize("descriptor,expected_slug", [
        ("Rolex Datejust Wimbledon Dial", "wimbledon"),
        ("Rolex Daytona Panda Dial", "panda"),
        ("Rolex Sky Dweller Tiffany Dial", "tiffany"),
        ("Audemars Piguet Skeleton Dial", "skeleton"),
        ("Patek Skeletonized Dial", "skeleton"),
        ("Rolex Day-Date Meteorite Dial", "meteorite"),
        ("Aventurine Dial Cartier", "aventurine"),
        ("Mother of Pearl Dial Lady Datejust", "mother_of_pearl"),
        ("Mother-of-pearl Dial", "mother_of_pearl"),
        ("MOP dial Datejust", "mother_of_pearl"),
        ("Tapestry Dial Rolex", "tapestry"),
        ("Pavé Diamond Dial", "pave"),
        ("Pave Diamond Dial", "pave"),
        ("Linen Dial Datejust", "linen"),
        ("Celebration Dial Oyster Perpetual", "celebration"),
        ("Tropical Dial vintage Sub", "tropical"),
    ])
    def test_each_compound_resolves_to_slug(self, descriptor, expected_slug):
        assert detect_named_special(descriptor) == expected_slug

    def test_no_compound_returns_none(self):
        assert detect_named_special(
            "Rolex Submariner 41MM Black Dial Oyster Bracelet"
        ) is None

    # OPERATOR PLAN-REVIEW PIN: longest-match-wins. Reverse Panda must NOT
    # silently parse to panda.
    def test_reverse_panda_not_panda(self):
        assert detect_named_special(
            "Rolex Daytona Reverse Panda Dial Steel Bracelet"
        ) == "reverse_panda"

    def test_reverse_panda_lowercased_input(self):
        assert detect_named_special("reverse panda dial") == "reverse_panda"

    def test_panda_alone_still_panda(self):
        assert detect_named_special("Daytona Panda Dial") == "panda"

    def test_skeleton_beats_no_other(self):
        # Skeletonized + Skeleton -> "skeletonized" longer but maps to "skeleton"
        assert detect_named_special("Skeletonized Dial Custom") == "skeleton"


# ─── Auction-type detection ───────────────────────────────────────────


class TestAuctionType:
    def test_nr_with_ascii_space(self):
        assert detect_auction_type("No Reserve - Rolex Submariner") == "NR"

    def test_nr_with_nbsp_after_hyphen(self):
        # The NBSP must be normalized to space before this function runs;
        # test the post-normalization behavior here (regex with \s).
        # Detection is robust to the regex's \s catching NBSP directly.
        assert detect_auction_type(
            f"No Reserve -{NBSP}Rolex Submariner"
        ) == "NR"

    def test_nr_with_no_hyphen_space(self):
        assert detect_auction_type("No Reserve-Rolex") == "NR"

    def test_res_when_no_prefix(self):
        assert detect_auction_type("Rolex Submariner 41MM") == "RES"

    def test_no_reserve_mid_string_is_res(self):
        # Mid-string "No Reserve" without leading anchor -> RES
        assert detect_auction_type(
            "Vintage Rolex offered with No Reserve language"
        ) == "RES"


# ─── Pipeline integration ────────────────────────────────────────────


class TestPipelineIntegration:
    def test_minimal_single_report(self, tmp_path):
        path = write_csv(tmp_path / "grailzee_2026-04-01.csv", [
            _row(),
            _row(reference="79830RB", title="Tudor Black Bay GMT 41MM Black Dial",
                 dial_numerals_raw="Arabic Numerals", sold_price="3200.0"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 2
        assert summary.source_rows_total == 2
        assert summary.canonical_rows_emitted == 2
        assert summary.asset_class_filtered == 0
        assert summary.numerals_blank_dropped == 0
        assert summary.within_report_duplicates == 0
        assert summary.cross_report_duplicates == 0

    def test_canonical_row_carries_all_fields(self, tmp_path):
        path = write_csv(tmp_path / "report.csv", [_row()])
        rows, _ = load_and_canonicalize([path])
        r = rows[0]
        assert r.reference == "126610LN"
        assert r.sold_at == date(2026, 4, 1)
        assert r.sold_for == 12000.0
        assert r.auction_type == "RES"
        assert r.dial_numerals == "No Numerals"
        assert r.dial_color == "black"
        assert r.named_special is None
        assert r.brand == "Rolex"
        assert r.model == "Rolex Submariner"
        assert r.condition == "Very Good"
        assert r.papers == "Yes"
        assert r.year == "2025"
        assert r.box == "Yes"
        assert r.sell_through_pct == 0.45
        assert r.url == "https://grailzee.com/x"
        assert r.source_report == "report.csv"
        assert r.source_row_index == 0

    def test_empty_report_paths_raises(self):
        with pytest.raises(ValueError, match="empty"):
            load_and_canonicalize([])

    def test_missing_csv_columns_raises(self, tmp_path):
        # Synthetic CSV missing the dial_numerals_raw column
        p = tmp_path / "broken.csv"
        with open(p, "w", encoding="utf-8") as f:
            f.write("date_sold,make,reference,title,condition,papers,"
                    "sold_price,sell_through_pct,model,year,box,url\n")
            f.write("2026-04-01,X,123,Title,VG,Yes,1000,0.5,M,2025,Yes,u\n")
        with pytest.raises(ValueError, match="missing expected columns"):
            load_and_canonicalize([p])

    def test_determinism_two_runs_identical_output(self, tmp_path):
        path = write_csv(tmp_path / "d.csv", [
            _row(reference="A", title="A 41MM Black Dial"),
            _row(reference="B", title="B 41MM Blue Dial",
                 sold_price="2000.0", date_sold="2026-04-02"),
            _row(reference="C", title="C 41MM Green Dial",
                 sold_price="3000.0", date_sold="2026-04-03"),
        ])
        rows1, _ = load_and_canonicalize([path])
        rows2, _ = load_and_canonicalize([path])
        assert rows1 == rows2

    def test_output_order_stable_by_source_then_index(self, tmp_path):
        path = write_csv(tmp_path / "ord.csv", [
            _row(reference=f"R{i}", title=f"R{i} 41MM Black Dial",
                 sold_price=f"{1000 + i}.0", date_sold=f"2026-04-{i+1:02d}")
            for i in range(5)
        ])
        rows, _ = load_and_canonicalize([path])
        # All from same source; index ascending preserves CSV order
        assert [r.source_row_index for r in rows] == [0, 1, 2, 3, 4]


# ─── NBSP normalization integration ───────────────────────────────────


class TestNBSPNormalization:
    def test_nbsp_in_title_normalizes_for_nr_detection(self, tmp_path):
        path = write_csv(tmp_path / "nbsp.csv", [
            _row(title=f"No Reserve -{NBSP}Tudor Black Bay 41MM Black Dial"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert rows[0].auction_type == "NR"
        # Descriptor on the canonical row is NBSP-normalized
        assert NBSP not in rows[0].auction_descriptor
        assert summary.nbsp_normalized_nr_rows == 1

    def test_nbsp_normalized_nr_counter_skipped_when_already_clean(self, tmp_path):
        path = write_csv(tmp_path / "clean_nr.csv", [
            _row(title="No Reserve - Tudor Black Bay 41MM Black Dial"),
        ])
        _, summary = load_and_canonicalize([path])
        assert summary.nbsp_normalized_nr_rows == 0


# ─── Within-report dedup ──────────────────────────────────────────────


class TestWithinReportDedup:
    def test_exact_duplicate_collapses_to_one(self, tmp_path):
        rows = [
            _row(reference="91650", title="Tudor 1926 41MM White Dial",
                 sold_price="2000.0", date_sold="2026-01-16"),
            _row(reference="91650", title="Tudor 1926 41MM White Dial",
                 sold_price="2000.0", date_sold="2026-01-16"),
        ]
        path = write_csv(tmp_path / "dup.csv", rows)
        result, summary = load_and_canonicalize([path])
        assert len(result) == 1
        assert summary.within_report_duplicates == 1
        assert summary.cross_report_duplicates == 0

    def test_first_seen_wins_within_report(self, tmp_path):
        rows = [
            _row(reference="X", title="X 41MM Black Dial", model="FirstModel"),
            _row(reference="X", title="X 41MM Black Dial", model="SecondModel"),
        ]
        path = write_csv(tmp_path / "fsw.csv", rows)
        result, _ = load_and_canonicalize([path])
        assert len(result) == 1
        # Both rows have same dedup key (model is not in key); first kept
        assert result[0].model == "FirstModel"
        assert result[0].source_row_index == 0


# ─── Cross-report dedup (validation path) ─────────────────────────────


class TestCrossReportDedup:
    def test_overlap_resolves_via_filename_sort(self, tmp_path):
        # ISO-date filenames: W2 (later) > W1 (earlier)
        w1 = write_csv(tmp_path / "grailzee_2026-04-06.csv", [
            _row(reference="OV1", title="OV1 41MM Black Dial",
                 sold_price="1000.0", date_sold="2026-04-01",
                 condition="Very Good"),
        ])
        w2 = write_csv(tmp_path / "grailzee_2026-04-21.csv", [
            _row(reference="OV1", title="OV1 41MM Black Dial",
                 sold_price="1000.0", date_sold="2026-04-01",
                 condition="Excellent"),
        ])
        rows, summary = load_and_canonicalize([w1, w2])
        assert len(rows) == 1
        assert summary.cross_report_duplicates == 1
        # Prefer most recent by filename sort: W2 wins
        assert rows[0].source_report == "grailzee_2026-04-21.csv"
        assert rows[0].condition == "Excellent"

    def test_unique_rows_in_each_report_both_kept(self, tmp_path):
        w1 = write_csv(tmp_path / "grailzee_2026-04-06.csv", [
            _row(reference="A", title="A 41MM Black Dial",
                 date_sold="2026-04-01"),
        ])
        w2 = write_csv(tmp_path / "grailzee_2026-04-21.csv", [
            _row(reference="B", title="B 41MM Black Dial",
                 date_sold="2026-04-02"),
        ])
        rows, summary = load_and_canonicalize([w1, w2])
        assert len(rows) == 2
        assert summary.cross_report_duplicates == 0


# ─── 3-tuple near-collision counter ───────────────────────────────────


class TestNearCollisions:
    def test_same_3tuple_different_descriptor_both_flow_through(self, tmp_path):
        # I.4 finding: same (ref, date, price) with differing descriptor
        # are kept as separate auctions; counted, not dropped.
        rows = [
            _row(reference="124300", title="Rolex Oyster Perpetual 41MM Red Dial",
                 sold_price="16900.0", date_sold="2026-03-30"),
            _row(reference="124300", title="Rolex Oyster Perpetual 41MM Yellow Dial",
                 sold_price="16900.0", date_sold="2026-03-30"),
        ]
        path = write_csv(tmp_path / "near.csv", rows)
        result, summary = load_and_canonicalize([path])
        assert len(result) == 2
        assert summary.within_report_near_collisions == 1
        assert summary.within_report_duplicates == 0


# ─── Drop counters ────────────────────────────────────────────────────


class TestDropCounters:
    def test_asset_class_filtered_increments(self, tmp_path):
        path = write_csv(tmp_path / "lv.csv", [
            _row(make="Louis Vuitton",
                 title="Louis Vuitton Neverfull 11 x 18IN Leather",
                 reference="M28351"),
            _row(),  # one watch row
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert summary.asset_class_filtered == 1

    def test_numerals_blank_dropped_increments(self, tmp_path):
        path = write_csv(tmp_path / "blank.csv", [
            _row(dial_numerals_raw=""),
            _row(reference="X", dial_numerals_raw="Arabic Numerals"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert summary.numerals_blank_dropped == 1

    def test_fallthrough_drops_increments(self, tmp_path):
        path = write_csv(tmp_path / "ft.csv", [
            _row(dial_numerals_raw="Sapphire Numerals"),
            _row(reference="X", dial_numerals_raw="Plexiglass"),
            _row(reference="Y", dial_numerals_raw="Arabic Numerals"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert summary.fallthrough_drops == 2

    def test_slash_canonicalized_increments(self, tmp_path):
        path = write_csv(tmp_path / "slash.csv", [
            _row(dial_numerals_raw="Arabic/Roman Numerals"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert rows[0].dial_numerals == "Arabic"
        assert summary.numerals_slash_canonicalized == 1

    def test_dial_color_unknown_increments(self, tmp_path):
        path = write_csv(tmp_path / "unk.csv", [
            _row(title="Vintage piece without color anchor"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert len(rows) == 1
        assert rows[0].dial_color == "unknown"
        assert summary.dial_color_unknown == 1

    def test_named_special_detected_increments(self, tmp_path):
        path = write_csv(tmp_path / "ns.csv", [
            _row(title="Rolex Datejust Wimbledon Dial 41MM"),
            _row(reference="X", title="Rolex Submariner 41MM Black Dial"),
        ])
        rows, summary = load_and_canonicalize([path])
        assert summary.named_special_detected == 1
        wimb = next(r for r in rows if r.named_special == "wimbledon")
        assert wimb is not None


# ─── Arithmetic invariant ─────────────────────────────────────────────


class TestSummaryArithmetic:
    def test_emitted_equals_total_minus_drops(self, tmp_path):
        rows = [
            _row(reference="A", title="A 41MM Black Dial"),
            _row(reference="B", title="B 41MM Blue Dial",
                 dial_numerals_raw=""),                    # blank drop
            _row(reference="C", title="C 41MM Green Dial",
                 dial_numerals_raw="Sapphire Numerals"),   # fallthrough
            _row(reference="D", title="LV Bag 11 x 18IN"), # asset-class
            _row(reference="A", title="A 41MM Black Dial"), # within-report dup
        ]
        path = write_csv(tmp_path / "arith.csv", rows)
        result, s = load_and_canonicalize([path])
        assert s.source_rows_total == 5
        assert s.asset_class_filtered == 1
        assert s.numerals_blank_dropped == 1
        assert s.fallthrough_drops == 1
        assert s.within_report_duplicates == 1
        assert s.cross_report_duplicates == 0
        assert s.canonical_rows_emitted == len(result) == 1
        assert (s.canonical_rows_emitted ==
                s.source_rows_total - s.asset_class_filtered
                - s.numerals_blank_dropped - s.fallthrough_drops
                - s.within_report_duplicates - s.cross_report_duplicates)


# ─── Archival wrapper ─────────────────────────────────────────────────


class TestIngestAndArchive:
    def test_happy_path_archives_source(self, tmp_path):
        src = write_csv(tmp_path / "live" / "report.csv", [_row()])
        rows, summary, dest = ingest_and_archive(src)
        assert len(rows) == 1
        assert summary.canonical_rows_emitted == 1
        assert dest == tmp_path / "live" / "archive" / "report.csv"
        assert dest.exists()
        assert not src.exists()

    def test_explicit_archive_dir(self, tmp_path):
        src = write_csv(tmp_path / "live" / "report.csv", [_row()])
        custom = tmp_path / "custom_archive"
        _, _, dest = ingest_and_archive(src, archive_dir=custom)
        assert dest == custom / "report.csv"
        assert dest.exists()

    def test_idempotency_block_on_destination_exists(self, tmp_path):
        src = write_csv(tmp_path / "live" / "report.csv", [_row()])
        archive = tmp_path / "live" / "archive"
        archive.mkdir(parents=True)
        # Pre-existing destination
        (archive / "report.csv").write_text("preexisting")
        with pytest.raises(FileExistsError, match="already exists"):
            ingest_and_archive(src)
        # Source must NOT have moved
        assert src.exists()
        assert (archive / "report.csv").read_text() == "preexisting"

    def test_pure_function_no_filesystem_side_effect(self, tmp_path):
        src = write_csv(tmp_path / "report.csv", [_row()])
        # load_and_canonicalize should NOT create archive/ or move src
        load_and_canonicalize([src])
        assert src.exists()
        assert not (tmp_path / "archive").exists()


# ─── Float-key dedup safety ───────────────────────────────────────────


class TestDedupKeyStringification:
    def test_price_with_decimal_dedupes_as_expected(self, tmp_path):
        # Exact same price string-formatted to 2 decimals
        rows = [
            _row(reference="P", title="P 41MM Black Dial", sold_price="1234.5"),
            _row(reference="P", title="P 41MM Black Dial", sold_price="1234.50"),
        ]
        path = write_csv(tmp_path / "px.csv", rows)
        result, summary = load_and_canonicalize([path])
        # 1234.5 and 1234.50 stringify to "1234.50" via f"{:.2f}"
        assert len(result) == 1
        assert summary.within_report_duplicates == 1
