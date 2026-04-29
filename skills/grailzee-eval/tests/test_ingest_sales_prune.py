"""Tests for prune_by_sell_date (design v1 §10, sub-step 1.5)."""

from datetime import date, timedelta

import pytest

from scripts.ingest_sales import LedgerRow, prune_by_sell_date

TODAY = date(2026, 4, 29)
WINDOW = 180
BOUNDARY = TODAY - timedelta(days=WINDOW)  # 2025-10-31


def _row(stock_id: str, sell_date: date | None) -> LedgerRow:
    return LedgerRow(
        stock_id=stock_id,
        sell_date=sell_date,
        sell_cycle_id="2026-04",
        brand="Tudor",
        reference="79830RB",
        account="NR",
        buy_price=1000.00,
        sell_price=1200.00,
    )


_INSIDE = _row("INSIDE", BOUNDARY + timedelta(days=1))
_AT_BOUNDARY = _row("AT_BOUNDARY", BOUNDARY)
_BEFORE = _row("BEFORE", BOUNDARY - timedelta(days=1))
_FAR_PAST = _row("FAR_PAST", date(2020, 1, 1))
_NULL = _row("NULL_DATE", None)


class TestAllKept:
    def test_all_within_window(self) -> None:
        rows = [_INSIDE, _AT_BOUNDARY]
        kept, pruned = prune_by_sell_date(rows, TODAY)
        assert kept == rows
        assert pruned == 0

    def test_empty_input(self) -> None:
        kept, pruned = prune_by_sell_date([], TODAY)
        assert kept == []
        assert pruned == 0

    def test_single_row_kept(self) -> None:
        kept, pruned = prune_by_sell_date([_INSIDE], TODAY)
        assert kept == [_INSIDE]
        assert pruned == 0


class TestBoundarySemantics:
    def test_boundary_date_kept(self) -> None:
        """Row exactly at boundary date is kept; boundary is inclusive."""
        kept, pruned = prune_by_sell_date([_AT_BOUNDARY], TODAY)
        assert kept == [_AT_BOUNDARY]
        assert pruned == 0

    def test_one_day_before_boundary_pruned(self) -> None:
        kept, pruned = prune_by_sell_date([_BEFORE], TODAY)
        assert kept == []
        assert pruned == 1

    def test_all_outside_window(self) -> None:
        rows = [_BEFORE, _FAR_PAST]
        kept, pruned = prune_by_sell_date(rows, TODAY)
        assert kept == []
        assert pruned == 2


class TestNullSellDate:
    def test_null_sell_date_always_kept(self) -> None:
        """Rows with sell_date=None are never pruned regardless of today."""
        kept, pruned = prune_by_sell_date([_NULL], TODAY)
        assert kept == [_NULL]
        assert pruned == 0

    def test_null_kept_when_other_rows_pruned(self) -> None:
        kept, pruned = prune_by_sell_date([_NULL, _FAR_PAST], TODAY)
        assert kept == [_NULL]
        assert pruned == 1


class TestOrderPreservation:
    def test_kept_rows_preserve_input_order(self) -> None:
        row_a = _row("A", BOUNDARY + timedelta(days=10))
        row_b = _row("B", BOUNDARY + timedelta(days=5))
        row_c = _row("C", BOUNDARY + timedelta(days=20))
        kept, _ = prune_by_sell_date([row_a, row_b, row_c], TODAY)
        assert kept == [row_a, row_b, row_c]

    def test_pruned_rows_removed_relative_order_unchanged(self) -> None:
        row_k1 = _row("K1", BOUNDARY + timedelta(days=1))
        row_p1 = _row("P1", BOUNDARY - timedelta(days=1))
        row_k2 = _row("K2", BOUNDARY + timedelta(days=5))
        kept, pruned = prune_by_sell_date([row_k1, row_p1, row_k2], TODAY)
        assert kept == [row_k1, row_k2]
        assert pruned == 1


class TestCustomWindow:
    def test_30_day_window(self) -> None:
        """Non-default window_days=30 is applied; 180-day default is not assumed."""
        boundary_30 = TODAY - timedelta(days=30)
        inside_30 = _row("IN30", boundary_30)
        outside_30 = _row("OUT30", boundary_30 - timedelta(days=1))
        kept, pruned = prune_by_sell_date([inside_30, outside_30], TODAY, window_days=30)
        assert kept == [inside_30]
        assert pruned == 1

    def test_zero_day_window_keeps_today(self) -> None:
        """window_days=0 means boundary=today; row sold today is kept (inclusive)."""
        today_row = _row("TODAY", TODAY)
        yesterday_row = _row("YESTERDAY", TODAY - timedelta(days=1))
        kept, pruned = prune_by_sell_date([today_row, yesterday_row], TODAY, window_days=0)
        assert kept == [today_row]
        assert pruned == 1


class TestOTELSpan:
    def test_span_created(self, span_exporter) -> None:
        prune_by_sell_date([_INSIDE], TODAY)
        names = [s.name for s in span_exporter.get_finished_spans()]
        assert "ingest_sales.prune_by_sell_date" in names

    def test_span_attributes(self, span_exporter) -> None:
        rows = [_INSIDE, _BEFORE]
        prune_by_sell_date(rows, TODAY)
        span = next(
            s for s in span_exporter.get_finished_spans()
            if s.name == "ingest_sales.prune_by_sell_date"
        )
        assert span.attributes["input_count"] == 2
        assert span.attributes["kept_count"] == 1
        assert span.attributes["pruned_count"] == 1
        assert span.attributes["today"] == TODAY.isoformat()
        assert span.attributes["window_days"] == 180
