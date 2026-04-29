"""Tests for ingest_sales.transform_jsonl — sub-step 1.2 corrective pass.

All test fixtures are real-derived: extracted verbatim from the canonical
WatchTrack production fixture (watchtrack_full_final.jsonl, sha256
029238eb558a2aea...) per ADR-0005 and the post-mortem §5 mandatory rule.
No synthetic JSONL constructed from scratch.

Field-path assertions are verified against the three sample records
embedded in the 1.2 rebuild prompt (TEY1083, TEYPA1061, TEY1048).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    LedgerRow,
    SchemaShiftDetected,
    transform_jsonl,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ingest_sales"


# ─── RES matched join (TEY1083 Sale + TEYPA1061 Purchase) ────────────────
#
# TEY1083: Fulfilled Grailzee Sale, Platform fee actual_cost=99 → RES,
#          line_items[0].stock_id="57238". Created 2026-03-02.
# TEYPA1061: Purchase, line_items[0].stock_id="57238" (matching),
#            single payment 2026-02-02, line_items[0].delivered_date=2026-02-04.


class TestRESMatchedJoin:
    def _row(self) -> LedgerRow:
        rows, skipped = transform_jsonl(FIXTURES / "fixture_res_matched.jsonl")
        assert len(rows) == 1
        assert skipped == []
        return rows[0]

    def test_returns_one_row(self):
        rows, _ = transform_jsonl(FIXTURES / "fixture_res_matched.jsonl")
        assert len(rows) == 1

    def test_row_is_ledger_row(self):
        assert isinstance(self._row(), LedgerRow)

    def test_stock_id(self):
        assert self._row().stock_id == "57238"

    def test_brand(self):
        assert self._row().brand == "Tudor"

    def test_reference(self):
        assert self._row().reference == "M79360N-0024"

    def test_account_res_from_99(self):
        assert self._row().account == "RES"

    def test_buy_price_from_sale_line_item(self):
        # TEY1083.line_items[0].cost_of_item = 8900
        assert self._row().buy_price == 8900.0

    def test_sell_price_from_sale_line_item(self):
        # TEY1083.line_items[0].unit_price = 9850
        assert self._row().sell_price == 9850.0

    def test_sell_date_from_sale_created_at(self):
        # TEY1083.created_at = "2026-03-02T18:56:45Z"
        assert self._row().sell_date == date(2026, 3, 2)

    def test_sell_cycle_id(self):
        assert self._row().sell_cycle_id == "cycle_2026-05"

    def test_sell_delivered_date(self):
        # TEY1083.line_items[0].delivered_date = "2026-03-04T15:30:10.61Z"
        assert self._row().sell_delivered_date == date(2026, 3, 4)

    def test_buy_date_from_purchase_created_at(self):
        # TEYPA1061.created_at = "2026-02-02T14:31:25Z"
        assert self._row().buy_date == date(2026, 2, 2)

    def test_buy_cycle_id(self):
        assert self._row().buy_cycle_id == "cycle_2026-03"

    def test_buy_received_date_from_purchase_line_items_0(self):
        # TEYPA1061.line_items[0].delivered_date = "2026-02-04T18:45:18Z"
        assert self._row().buy_received_date == date(2026, 2, 4)

    def test_buy_paid_date_min_of_payments(self):
        # TEYPA1061.payments[0].payment_date = "2026-02-02T16:20:38Z" (only one)
        assert self._row().buy_paid_date == date(2026, 2, 2)


# ─── NR unmatched join (TEY1048 Sale, no matching Purchase) ─────────────
#
# TEY1048: Fulfilled Grailzee Sale, Platform fee actual_cost=49 → NR,
#          line_items[0].stock_id="297Z8". No Purchase with stock_id 297Z8
#          in the fixture. is_consignment=True — passes through unchanged.


class TestNRUnmatchedJoin:
    def _row(self) -> LedgerRow:
        rows, skipped = transform_jsonl(FIXTURES / "fixture_nr_unmatched.jsonl")
        assert len(rows) == 1
        return rows[0]

    def test_returns_one_row_no_skipped(self):
        rows, skipped = transform_jsonl(FIXTURES / "fixture_nr_unmatched.jsonl")
        assert len(rows) == 1
        assert skipped == []

    def test_account_nr_from_49(self):
        assert self._row().account == "NR"

    def test_stock_id(self):
        # TEY1048.line_items[0].stock_id = "297Z8"
        assert self._row().stock_id == "297Z8"

    def test_brand(self):
        assert self._row().brand == "Glashütte Original"

    def test_reference(self):
        assert self._row().reference == "1-37-02-09-02-70"

    def test_buy_price(self):
        # TEY1048.line_items[0].cost_of_item = 12000
        assert self._row().buy_price == 12000.0

    def test_sell_price(self):
        # TEY1048.line_items[0].unit_price = 11000
        assert self._row().sell_price == 11000.0

    def test_sell_date(self):
        # TEY1048.created_at = "2026-01-12T14:35:47Z"
        assert self._row().sell_date == date(2026, 1, 12)

    def test_sell_cycle_id(self):
        assert self._row().sell_cycle_id == "cycle_2026-01"

    def test_sell_delivered_date(self):
        # TEY1048.line_items[0].delivered_date = "2026-01-14T15:10:08.983Z"
        assert self._row().sell_delivered_date == date(2026, 1, 14)

    def test_buy_date_is_none(self):
        assert self._row().buy_date is None

    def test_buy_cycle_id_is_none(self):
        assert self._row().buy_cycle_id is None

    def test_buy_received_date_is_none(self):
        assert self._row().buy_received_date is None

    def test_buy_paid_date_is_none(self):
        assert self._row().buy_paid_date is None

    def test_consignment_passes_through_unchanged(self):
        """TEY1048.line_items[0].is_consignment=True. The parser makes no
        special case for consignment; cost_of_item and unit_price pass through
        as recorded. Consignment in scope per spec v1.1 amendment."""
        row = self._row()
        # cost_of_item 12000 > unit_price 11000: consignment payout artifact.
        assert row.buy_price == 12000.0
        assert row.sell_price == 11000.0


# ─── NR matched join (TEY1103 Sale + TEYPA1085 Purchase) ─────────────────
#
# TEY1103: Fulfilled Grailzee Sale, Platform fee actual_cost=49 → NR,
#          line_items[0].stock_id="930UV". Created 2026-04-20.
# TEYPA1085: Purchase with 3 line_items (063E6, 930UV, 8337Z).
#            buy_received_date uses line_items[0] per spec = 063E6's date.
#            single payment 2026-04-08 (before created_at 2026-04-10; real data).


class TestNRMatchedJoin:
    def _row(self) -> LedgerRow:
        rows, skipped = transform_jsonl(FIXTURES / "fixture_nr_matched.jsonl")
        assert len(rows) == 1
        return rows[0]

    def test_returns_one_row(self):
        rows, _ = transform_jsonl(FIXTURES / "fixture_nr_matched.jsonl")
        assert len(rows) == 1

    def test_account_nr(self):
        assert self._row().account == "NR"

    def test_stock_id(self):
        assert self._row().stock_id == "930UV"

    def test_brand(self):
        assert self._row().brand == "Tudor"

    def test_reference(self):
        assert self._row().reference == "M28600-0009"

    def test_sell_date(self):
        # TEY1103.created_at = "2026-04-20T15:08:13Z"
        assert self._row().sell_date == date(2026, 4, 20)

    def test_sell_cycle_id(self):
        assert self._row().sell_cycle_id == "cycle_2026-08"

    def test_sell_delivered_date(self):
        # TEY1103.line_items[0].delivered_date = "2026-04-21T13:40:17.643Z"
        assert self._row().sell_delivered_date == date(2026, 4, 21)

    def test_buy_date(self):
        # TEYPA1085.created_at = "2026-04-10T18:02:45Z"
        assert self._row().buy_date == date(2026, 4, 10)

    def test_buy_cycle_id(self):
        assert self._row().buy_cycle_id == "cycle_2026-07"

    def test_buy_received_date_uses_line_items_0(self):
        # TEYPA1085 has 3 line_items; spec anchors buy_received_date to
        # line_items[0] (stock_id=063E6). delivered_date = "2026-04-15T13:54:08Z".
        assert self._row().buy_received_date == date(2026, 4, 15)

    def test_buy_paid_date(self):
        # TEYPA1085.payments[0].payment_date = "2026-04-08T18:54:34Z"
        # Payment precedes created_at (real data). min() of one payment.
        assert self._row().buy_paid_date == date(2026, 4, 8)


# ─── Pending Sale skip (TEY1092) ─────────────────────────────────────────
#
# TEY1092: Grailzee Sale with status="Pending". Parser skips it: no LedgerRow
# emitted, one entry in the skipped list with reason="pending".


class TestPendingSkip:
    def test_no_rows_emitted(self):
        rows, _ = transform_jsonl(FIXTURES / "fixture_pending.jsonl")
        assert rows == []

    def test_skip_entry_in_skipped_list(self):
        _, skipped = transform_jsonl(FIXTURES / "fixture_pending.jsonl")
        assert len(skipped) == 1
        assert skipped[0]["transaction_id"] == "TEY1092"
        assert skipped[0]["reason"] == "pending"

    def test_skipped_entry_has_required_keys(self):
        _, skipped = transform_jsonl(FIXTURES / "fixture_pending.jsonl")
        assert "transaction_id" in skipped[0]
        assert "reason" in skipped[0]


# ─── Trade silent skip ────────────────────────────────────────────────────
#
# TEY1098-TRADE-171Z8: type="Trade". Silently skipped — no row, no skip entry.


class TestTradeSilentSkip:
    def test_no_rows_emitted(self):
        rows, _ = transform_jsonl(FIXTURES / "fixture_trade.jsonl")
        assert rows == []

    def test_no_skipped_entry(self):
        _, skipped = transform_jsonl(FIXTURES / "fixture_trade.jsonl")
        assert skipped == []

    def test_trade_does_not_raise(self):
        transform_jsonl(FIXTURES / "fixture_trade.jsonl")


# ─── Multi-service Sale (TEY1081: Auction Fee + Platform fee 49) ──────────
#
# TEY1081 has two services: Auction Fee and Platform fee (actual_cost=49).
# The parser finds the Platform fee entry and maps to NR. Does not raise.


class TestMultiServiceSale:
    def _row(self) -> LedgerRow:
        rows, _ = transform_jsonl(FIXTURES / "fixture_multi_service.jsonl")
        assert len(rows) == 1
        return rows[0]

    def test_does_not_raise(self):
        transform_jsonl(FIXTURES / "fixture_multi_service.jsonl")

    def test_account_nr_from_platform_fee(self):
        assert self._row().account == "NR"

    def test_stock_id(self):
        assert self._row().stock_id == "856CH"

    def test_buy_price(self):
        # TEY1081.line_items[0].cost_of_item = 1750
        assert self._row().buy_price == 1750.0

    def test_sell_price(self):
        # TEY1081.line_items[0].unit_price = 2130
        assert self._row().sell_price == 2130.0


# ─── Non-Grailzee Sale filtered ──────────────────────────────────────────


class TestNonGrailzeeSaleFiltered:
    def test_non_grailzee_platform_returns_empty(self, tmp_path):
        """Sale with platform != ["Grailzee"] produces no row."""
        rec = {
            "type": "Sale",
            "transaction_id": "DIRECT-001",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Direct"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{
                "stock_id": "X001",
                "brand": "Tudor",
                "reference_number": "79830RB",
                "cost_of_item": 2750.0,
                "unit_price": 3200.0,
                "delivered_date": None,
            }],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        rows, skipped = transform_jsonl(p)
        assert rows == []
        assert skipped == []

    def test_empty_platform_returns_empty(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "UNKNOWN-001",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": [],
            "services": [],
            "line_items": [],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        rows, skipped = transform_jsonl(p)
        assert rows == []
        assert skipped == []

    def test_mixed_batch_returns_only_grailzee(self, tmp_path):
        """One Direct Sale + one Grailzee Sale → only the Grailzee row emitted."""
        lines = [
            json.dumps({
                "type": "Sale", "transaction_id": "D-001", "status": "Fulfilled",
                "created_at": "2026-04-20T10:00:00Z", "platform": ["Direct"],
                "services": [], "line_items": [],
            }),
            json.dumps({
                "type": "Sale", "transaction_id": "G-001", "status": "Fulfilled",
                "created_at": "2026-04-20T10:00:00Z", "platform": ["Grailzee"],
                "services": [{"name": "Platform fee", "actual_cost": 49}],
                "line_items": [{
                    "stock_id": "TEST01", "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0, "unit_price": 3200.0,
                    "delivered_date": None,
                }],
            }),
        ]
        p = tmp_path / "batch.jsonl"
        p.write_text("\n".join(lines))
        rows, _ = transform_jsonl(p)
        assert len(rows) == 1
        assert rows[0].stock_id == "TEST01"


# ─── Purchase-only file (no Sales) ───────────────────────────────────────


class TestPurchaseOnlyFile:
    def test_purchase_only_returns_empty(self, tmp_path):
        rec = {
            "type": "Purchase",
            "transaction_id": "TEYPA9999",
            "status": "Received",
            "created_at": "2026-04-10T10:00:00Z",
            "payments": [{"payment_date": "2026-04-11T10:00:00Z"}],
            "line_items": [{"stock_id": "X001", "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        rows, skipped = transform_jsonl(p)
        assert rows == []
        assert skipped == []


# ─── SchemaShiftDetected ─────────────────────────────────────────────────


class TestSchemaShiftDetected:
    def test_json_parse_error_raises(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text('{"type": "Sale", bad json here\n')
        with pytest.raises(SchemaShiftDetected, match="JSON parse error"):
            transform_jsonl(p)

    def test_json_parse_error_includes_line_number(self, tmp_path):
        lines = [
            json.dumps({"type": "Purchase", "transaction_id": "P1",
                        "payments": [], "line_items": []}),
            '{"type": "Sale", bad',
        ]
        p = tmp_path / "bad.jsonl"
        p.write_text("\n".join(lines))
        with pytest.raises(SchemaShiftDetected, match="2"):
            transform_jsonl(p)

    def test_missing_type_field_raises(self, tmp_path):
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps({"transaction_id": "X", "status": "Fulfilled"}))
        with pytest.raises(SchemaShiftDetected, match="type"):
            transform_jsonl(p)

    def test_unknown_type_value_raises(self, tmp_path):
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps({"type": "Refund", "transaction_id": "X"}))
        with pytest.raises(SchemaShiftDetected, match="Refund"):
            transform_jsonl(p)

    def test_missing_created_at_on_grailzee_sale_raises(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-001",
            "status": "Fulfilled",
            # created_at intentionally absent
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="created_at"):
            transform_jsonl(p)

    def test_missing_stock_id_on_grailzee_sale_raises(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-002",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"brand": "Tudor", "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
            # stock_id intentionally absent from line_item
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="stock_id"):
            transform_jsonl(p)

    def test_missing_cost_of_item_raises(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-003",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            # cost_of_item intentionally absent
                            "unit_price": 120.0, "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="cost_of_item"):
            transform_jsonl(p)

    def test_missing_unit_price_raises(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-004",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0,
                            # unit_price intentionally absent
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="unit_price"):
            transform_jsonl(p)

    def test_unknown_platform_fee_amount_raises(self, tmp_path):
        """actual_cost=75 is not in {49, 99}; raises SchemaShiftDetected."""
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-005",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 75}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="75"):
            transform_jsonl(p)

    def test_empty_services_raises(self, tmp_path):
        """services=[] cannot yield a Platform fee entry → SchemaShiftDetected.
        Extraction-agent territory per §11, but transform can't proceed without it."""
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-008",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="Platform fee"):
            transform_jsonl(p)

    def test_no_platform_fee_entry_raises(self, tmp_path):
        """services contains only non-Platform-fee entries."""
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-006",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Shipping", "actual_cost": 25}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="Platform fee"):
            transform_jsonl(p)

    def test_missing_line_items_raises(self, tmp_path):
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-007",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 49}],
            "line_items": [],  # empty
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected, match="line_items"):
            transform_jsonl(p)


# ─── Empty file ──────────────────────────────────────────────────────────


class TestEmptyFile:
    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        rows, skipped = transform_jsonl(p)
        assert rows == []
        assert skipped == []

    def test_blank_lines_only_returns_empty(self, tmp_path):
        p = tmp_path / "blanks.jsonl"
        p.write_text("\n\n\n")
        rows, skipped = transform_jsonl(p)
        assert rows == []
        assert skipped == []


# ─── OTEL span ───────────────────────────────────────────────────────────


class TestOTELSpanAttributes:
    def test_rows_emitted_set_on_span_when_schema_shift_fires(
        self, span_exporter, tmp_path
    ):
        """rows_emitted is set in a finally block inside _transform_jsonl_inner.
        Confirms the attribute lands on the span even when SchemaShiftDetected fires
        mid-loop (unknown Platform fee amount, raised after zero rows emitted)."""
        rec = {
            "type": "Sale",
            "transaction_id": "TEST-OTEL",
            "status": "Fulfilled",
            "created_at": "2026-04-20T10:00:00Z",
            "platform": ["Grailzee"],
            "services": [{"name": "Platform fee", "actual_cost": 75}],
            "line_items": [{"stock_id": "X001", "brand": "Tudor",
                            "reference_number": "R01",
                            "cost_of_item": 100.0, "unit_price": 120.0,
                            "delivered_date": None}],
        }
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps(rec))
        with pytest.raises(SchemaShiftDetected):
            transform_jsonl(p)
        spans = span_exporter.get_finished_spans()
        tx_span = next(
            (s for s in spans if s.name == "ingest_sales.transform_jsonl"), None
        )
        assert tx_span is not None, "ingest_sales.transform_jsonl span not captured"
        assert "rows_emitted" in tx_span.attributes
        assert tx_span.attributes["rows_emitted"] == 0


class TestOTELSpanTransparency:
    def test_transform_works_under_no_op_tracer(self, monkeypatch):
        """No-op tracer (active when OTEL_EXPORTER_OTLP_ENDPOINT is unset)
        must be transparent to callers."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        rows, skipped = transform_jsonl(FIXTURES / "fixture_res_matched.jsonl")
        assert len(rows) == 1
        assert rows[0].stock_id == "57238"

    def test_transform_span_does_not_suppress_schema_shift(self, monkeypatch, tmp_path):
        """Span wrapper must not catch or swallow SchemaShiftDetected."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        p = tmp_path / "batch.jsonl"
        p.write_text(json.dumps({"type": "Refund", "transaction_id": "X"}))
        with pytest.raises(SchemaShiftDetected):
            transform_jsonl(p)
