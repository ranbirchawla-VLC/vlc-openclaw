"""Tests for ingest_sales.transform_jsonl — sub-step 1.2.

Single-file ingest transformation. No I/O beyond reading fixture files.
No plugin, no Telegram, no MCP.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.ingest_sales import (
    ERPBatchInvalid,
    LedgerRow,
    SchemaShiftDetected,
    transform_jsonl,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ingest_sales"


# ─── Clean Grailzee sale (TEY1104-style) ─────────────────────────────


class TestCleanGrailzeeSale:
    def test_returns_one_row(self):
        rows = transform_jsonl(FIXTURES / "tey1104_clean.json")
        assert len(rows) == 1

    def test_row_is_ledger_row(self):
        rows = transform_jsonl(FIXTURES / "tey1104_clean.json")
        assert isinstance(rows[0], LedgerRow)

    def test_stock_id(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.stock_id == "TEY1104"

    def test_sell_date(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.sell_date == date(2026, 4, 25)

    def test_sell_cycle_id(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.sell_cycle_id == "cycle_2026-08"

    def test_brand(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.brand == "Tudor"

    def test_reference(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.reference == "79830RB"

    def test_account_nr_from_49(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.account == "NR"

    def test_buy_price(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.buy_price == 2750.0

    def test_sell_price(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.sell_price == 3200.0

    def test_buy_date_from_purchase(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.buy_date == date(2026, 4, 10)

    def test_buy_cycle_id(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.buy_cycle_id == "cycle_2026-07"

    def test_buy_received_date(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.buy_received_date == date(2026, 4, 12)

    def test_sell_delivered_date(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.sell_delivered_date == date(2026, 4, 27)

    def test_buy_paid_date_single_payment(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        assert row.buy_paid_date == date(2026, 4, 11)


class TestBuyPriceSource:
    def test_buy_price_from_sale_not_purchase(self, tmp_path):
        """B1: buy_price is always Sale line_item.cost_of_item, never Purchase."""
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY1104",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,   # Sale value
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [{
                "created_at": "2026-04-10",
                "line_item": {
                    "stock_id": "TEY1104",
                    "cost_of_item": 2600.0,   # deliberately different from Sale
                    "delivered_date": None,
                },
                "payments": [],
            }],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        row = transform_jsonl(p)[0]
        assert row.buy_price == 2750.0   # Sale value wins
        assert row.buy_price != 2600.0   # Purchase value not used


class TestResSaleAccount:
    def test_account_res_from_99(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY1048",
                    "brand": "Rolex",
                    "reference_number": "126300",
                    "cost_of_item": 8200.0,
                    "unit_price": 9400.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 99}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        row = transform_jsonl(p)[0]
        assert row.account == "RES"


# ─── Unmatched Purchase (TEY1048-style) ──────────────────────────────


class TestUnmatchedPurchase:
    def test_returns_one_row(self):
        rows = transform_jsonl(FIXTURES / "tey1048_unmatched.json")
        assert len(rows) == 1

    def test_buy_date_is_none(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.buy_date is None

    def test_buy_cycle_id_is_none(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.buy_cycle_id is None

    def test_buy_received_date_is_none(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.buy_received_date is None

    def test_buy_paid_date_is_none(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.buy_paid_date is None

    def test_sell_side_fields_populated(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.stock_id == "TEY1048"
        assert row.sell_date == date(2026, 4, 25)
        assert row.account == "RES"


# ─── Multi-payment Purchase (TEY1080-style) ──────────────────────────


class TestMultiPaymentPurchase:
    def test_buy_paid_date_is_minimum(self):
        row = transform_jsonl(FIXTURES / "tey1080_multi_payment.json")[0]
        # payments: 2026-04-15, 2026-03-29, 2026-04-10 -> min is 2026-03-29
        assert row.buy_paid_date == date(2026, 3, 29)

    def test_buy_date_from_purchase_created_at(self):
        row = transform_jsonl(FIXTURES / "tey1080_multi_payment.json")[0]
        assert row.buy_date == date(2026, 3, 28)

    def test_buy_received_date(self):
        row = transform_jsonl(FIXTURES / "tey1080_multi_payment.json")[0]
        assert row.buy_received_date == date(2026, 4, 1)

    def test_buy_cycle_id(self):
        row = transform_jsonl(FIXTURES / "tey1080_multi_payment.json")[0]
        # buy_date 2026-03-28 → first Monday of 2026 is 2026-01-05
        # delta = 82 days, 82 // 14 = 5, cycle = 6
        assert row.buy_cycle_id == "cycle_2026-06"


class TestEmptyPaymentsList:
    def test_buy_paid_date_none_when_no_payments(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-20",
                "line_item": {
                    "stock_id": "TEY5000",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [{
                "created_at": "2026-04-05",
                "line_item": {
                    "stock_id": "TEY5000",
                    "cost_of_item": 2750.0,
                    "delivered_date": None,
                },
                "payments": [],
            }],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        row = transform_jsonl(p)[0]
        assert row.buy_paid_date is None
        assert row.buy_date == date(2026, 4, 5)


# ─── ERPBatchInvalid: ambiguous-services cases ────────────────────────


class TestERPBatchInvalidServices:
    def test_auction_fee_raises(self):
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(FIXTURES / "tey1081_auction_fee.json")

    def test_cc_fee_only_raises(self):
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(FIXTURES / "tey1091_cc_fee_only.json")

    def test_no_services_raises(self):
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(FIXTURES / "tey1092_no_services.json")

    def test_actual_cost_none_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY9001",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": None}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(p)

    def test_unknown_fee_amount_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY9002",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 75}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(p)

    def test_error_message_names_stock_id(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY1081",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Auction Fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(ERPBatchInvalid, match="TEY1081"):
            transform_jsonl(p)


# ─── SchemaShiftDetected ─────────────────────────────────────────────


class TestSchemaShiftDetected:
    def test_missing_purchases_key_raises(self):
        with pytest.raises(SchemaShiftDetected, match="purchases"):
            transform_jsonl(FIXTURES / "missing_purchases_key.json")

    def test_missing_sales_key_raises(self, tmp_path):
        p = tmp_path / "batch.json"
        p.write_text(json.dumps({"purchases": []}))
        with pytest.raises(SchemaShiftDetected, match="sales"):
            transform_jsonl(p)

    def test_missing_stock_id_on_sale_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                    # stock_id intentionally absent
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(SchemaShiftDetected, match="stock_id"):
            transform_jsonl(p)

    def test_missing_line_item_on_sale_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                # line_item intentionally absent
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(SchemaShiftDetected, match="line_item"):
            transform_jsonl(p)

    def test_missing_created_at_on_sale_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                # created_at intentionally absent
                "line_item": {
                    "stock_id": "TEY9004",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(SchemaShiftDetected, match="created_at"):
            transform_jsonl(p)

    def test_missing_cost_of_item_on_sale_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY9005",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    # cost_of_item intentionally absent
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(SchemaShiftDetected, match="cost_of_item"):
            transform_jsonl(p)

    def test_missing_cost_of_item_on_matched_purchase_raises(self, tmp_path):
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY9003",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [{"name": "Platform fee", "actual_cost": 49}],
            }],
            "purchases": [{
                "created_at": "2026-04-05",
                "line_item": {
                    "stock_id": "TEY9003",
                    # cost_of_item intentionally absent
                    "delivered_date": None,
                },
                "payments": [],
            }],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(SchemaShiftDetected, match="cost_of_item"):
            transform_jsonl(p)


# ─── Non-Grailzee Sale filtered ──────────────────────────────────────


class TestNonGrailzeeSaleFiltered:
    def test_non_grailzee_returns_empty_list(self):
        rows = transform_jsonl(FIXTURES / "non_grailzee.json")
        assert rows == []

    def test_mixed_batch_returns_only_grailzee(self, tmp_path):
        batch = {
            "sales": [
                {
                    "platform": "eBay",
                    "created_at": "2026-04-25",
                    "line_item": {
                        "stock_id": "NOT001",
                        "brand": "Casio",
                        "reference_number": "GA-100",
                        "cost_of_item": 50.0,
                        "unit_price": 80.0,
                        "delivered_date": None,
                    },
                    "services": [],
                },
                {
                    "platform": "Grailzee",
                    "created_at": "2026-04-25",
                    "line_item": {
                        "stock_id": "TEY1104",
                        "brand": "Tudor",
                        "reference_number": "79830RB",
                        "cost_of_item": 2750.0,
                        "unit_price": 3200.0,
                        "delivered_date": None,
                    },
                    "services": [{"name": "Platform fee", "actual_cost": 49}],
                },
            ],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        rows = transform_jsonl(p)
        assert len(rows) == 1
        assert rows[0].stock_id == "TEY1104"


# ─── Cycle ID derivation ─────────────────────────────────────────────


class TestCycleIdDerivation:
    def test_sell_cycle_id_derived_from_sell_date(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        # sell_date 2026-04-25 → cycle_2026-08
        assert row.sell_cycle_id == "cycle_2026-08"

    def test_buy_cycle_id_derived_from_buy_date(self):
        row = transform_jsonl(FIXTURES / "tey1104_clean.json")[0]
        # buy_date 2026-04-10 → cycle_2026-07
        assert row.buy_cycle_id == "cycle_2026-07"

    def test_buy_cycle_id_none_when_unmatched(self):
        row = transform_jsonl(FIXTURES / "tey1048_unmatched.json")[0]
        assert row.buy_cycle_id is None


# ─── OTEL span ───────────────────────────────────────────────────────


class TestOTELSpanAttributes:
    def test_rows_emitted_set_on_span_when_exception_fires(self, span_exporter, tmp_path):
        """rows_emitted is set in a finally block inside _transform_jsonl_inner.
        Confirms the attribute lands on the span even when ERPBatchInvalid fires
        mid-loop. Closes Phase 1 carry-forward from 1.2 OTEL corrective gate.
        """
        batch = {
            "sales": [{
                "platform": "Grailzee",
                "created_at": "2026-04-25",
                "line_item": {
                    "stock_id": "TEY9001",
                    "brand": "Tudor",
                    "reference_number": "79830RB",
                    "cost_of_item": 2750.0,
                    "unit_price": 3200.0,
                    "delivered_date": None,
                },
                "services": [],  # triggers ERPBatchInvalid before any row appended
            }],
            "purchases": [],
        }
        p = tmp_path / "batch.json"
        p.write_text(json.dumps(batch))
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(p)
        spans = span_exporter.get_finished_spans()
        tx_span = next(
            (s for s in spans if s.name == "ingest_sales.transform_jsonl"), None
        )
        assert tx_span is not None, "ingest_sales.transform_jsonl span not captured"
        assert "rows_emitted" in tx_span.attributes
        assert tx_span.attributes["rows_emitted"] == 0


class TestOTELSpan:
    def test_transform_jsonl_works_under_no_op_tracer(self, monkeypatch):
        """Span wrapper does not interfere with function results.

        The no-op tracer (active when OTEL_EXPORTER_OTLP_ENDPOINT is unset)
        must be transparent to callers. Matches the pattern from
        test_grailzee_common.py::TestGetTracer.
        """
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        rows = transform_jsonl(FIXTURES / "tey1104_clean.json")
        assert len(rows) == 1
        assert rows[0].stock_id == "TEY1104"

    def test_transform_jsonl_span_does_not_suppress_erp_invalid(self, monkeypatch):
        """Span wrapper must not catch or swallow ERPBatchInvalid."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        with pytest.raises(ERPBatchInvalid):
            transform_jsonl(FIXTURES / "tey1092_no_services.json")

    def test_transform_jsonl_span_does_not_suppress_schema_shift(self, monkeypatch):
        """Span wrapper must not catch or swallow SchemaShiftDetected."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        with pytest.raises(SchemaShiftDetected):
            transform_jsonl(FIXTURES / "missing_purchases_key.json")
