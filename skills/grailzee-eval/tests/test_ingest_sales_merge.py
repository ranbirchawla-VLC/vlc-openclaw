"""Tests for ingest_sales.merge_rows — sub-step 1.4.

Rule Y dedup-and-update per design v1 §8. Pure Python; no I/O, no plugin,
no Telegram, no MCP. All row objects constructed inline.
"""
from __future__ import annotations

from datetime import date

import pytest

from scripts.ingest_sales import (
    ERPBatchInvalid,
    LedgerRow,
    MergeCounts,
    merge_rows,
)


# ─── Shared row fixtures ──────────────────────────────────────────────

_A = LedgerRow(
    stock_id="TEY1104",
    sell_date=date(2026, 4, 25),
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.0,
    sell_price=3200.0,
    buy_date=date(2026, 4, 10),
    buy_cycle_id="cycle_2026-07",
)

# A_PRIME: same stock_id as A, sell_price differs
_A_PRIME = LedgerRow(
    stock_id="TEY1104",
    sell_date=date(2026, 4, 25),
    sell_cycle_id="cycle_2026-08",
    brand="Tudor",
    reference="79830RB",
    account="NR",
    buy_price=2750.0,
    sell_price=3300.0,
    buy_date=date(2026, 4, 10),
    buy_cycle_id="cycle_2026-07",
)

_B = LedgerRow(
    stock_id="TEY1048",
    sell_date=date(2026, 4, 20),
    sell_cycle_id="cycle_2026-08",
    brand="Rolex",
    reference="126300",
    account="RES",
    buy_price=8200.0,
    sell_price=9400.0,
)

# B_PRIME: same stock_id as B, buy_price differs
_B_PRIME = LedgerRow(
    stock_id="TEY1048",
    sell_date=date(2026, 4, 20),
    sell_cycle_id="cycle_2026-08",
    brand="Rolex",
    reference="126300",
    account="RES",
    buy_price=8100.0,
    sell_price=9400.0,
)

_C = LedgerRow(
    stock_id="TEY1080",
    sell_date=date(2026, 4, 15),
    sell_cycle_id="cycle_2026-07",
    brand="Omega",
    reference="311.30.42.30.01.006",
    account="NR",
    buy_price=4500.0,
    sell_price=5200.0,
)

_D = LedgerRow(
    stock_id="TEY9001",
    sell_date=date(2026, 4, 22),
    sell_cycle_id="cycle_2026-08",
    brand="IWC",
    reference="IW356001",
    account="NR",
    buy_price=3100.0,
    sell_price=3600.0,
)

# D_PRIME: same stock_id as D, sell_price differs
_D_PRIME = LedgerRow(
    stock_id="TEY9001",
    sell_date=date(2026, 4, 22),
    sell_cycle_id="cycle_2026-08",
    brand="IWC",
    reference="IW356001",
    account="NR",
    buy_price=3100.0,
    sell_price=3700.0,
)


# ─── Pure add ────────────────────────────────────────────────────────


class TestPureAdd:
    def test_empty_existing_adds_row(self):
        result, counts = merge_rows([], [_A])
        assert result == [_A]
        assert counts == MergeCounts(added=1, updated=0, unchanged=0)

    def test_nonempty_existing_appends_at_end(self):
        result, counts = merge_rows([_A], [_B])
        assert result == [_A, _B]
        assert counts == MergeCounts(added=1, updated=0, unchanged=0)

    def test_added_row_is_at_last_position(self):
        result, _ = merge_rows([_A], [_B])
        assert result[-1] == _B

    def test_empty_existing_empty_new_returns_empty(self):
        result, counts = merge_rows([], [])
        assert result == []
        assert counts == MergeCounts(added=0, updated=0, unchanged=0)


# ─── Skip unchanged ───────────────────────────────────────────────────


class TestSkipUnchanged:
    def test_identical_row_skipped(self):
        result, counts = merge_rows([_A], [_A])
        assert result == [_A]
        assert counts == MergeCounts(added=0, updated=0, unchanged=1)

    def test_result_list_length_unchanged(self):
        result, _ = merge_rows([_A], [_A])
        assert len(result) == 1


# ─── In-place update ──────────────────────────────────────────────────


class TestUpdate:
    def test_divergent_field_updates_row(self):
        result, counts = merge_rows([_A], [_A_PRIME])
        assert counts == MergeCounts(added=0, updated=1, unchanged=0)

    def test_updated_row_at_position_zero(self):
        result, _ = merge_rows([_A], [_A_PRIME])
        assert result[0] == _A_PRIME

    def test_result_length_unchanged_after_update(self):
        result, _ = merge_rows([_A], [_A_PRIME])
        assert len(result) == 1

    def test_old_row_not_present_after_update(self):
        result, _ = merge_rows([_A], [_A_PRIME])
        assert _A not in result


# ─── All three outcomes in one batch ─────────────────────────────────


class TestAllThreeOutcomes:
    def test_counts_correct(self):
        # existing=[A,B,C], new=[A (unchanged), B' (update), D (add)]
        _, counts = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert counts == MergeCounts(added=1, updated=1, unchanged=1)

    def test_result_length(self):
        result, _ = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert len(result) == 4

    def test_a_unchanged_at_position_0(self):
        result, _ = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert result[0] == _A

    def test_b_prime_at_position_1(self):
        result, _ = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert result[1] == _B_PRIME

    def test_c_preserved_at_position_2(self):
        result, _ = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert result[2] == _C

    def test_d_appended_at_position_3(self):
        result, _ = merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        assert result[3] == _D


# ─── Order preservation ───────────────────────────────────────────────


class TestOrderPreservation:
    def test_update_preserves_existing_position(self):
        # existing=[A,B,C,D], update D at position 3
        result, _ = merge_rows([_A, _B, _C, _D], [_D_PRIME])
        assert result[3] == _D_PRIME

    def test_preceding_rows_untouched(self):
        result, _ = merge_rows([_A, _B, _C, _D], [_D_PRIME])
        assert result[0] == _A
        assert result[1] == _B
        assert result[2] == _C

    def test_result_length_unchanged_for_update(self):
        result, _ = merge_rows([_A, _B, _C, _D], [_D_PRIME])
        assert len(result) == 4


# ─── Mutation safety ──────────────────────────────────────────────────


class TestMutationSafety:
    # Verifies result is a fresh list; mutating result must not affect
    # existing or new inputs.

    def test_existing_list_not_mutated_on_update(self):
        existing = [_A, _B]
        result, _ = merge_rows(existing, [_A_PRIME])
        result[0] = _C  # mutate return value
        assert existing[0] == _A  # original unchanged

    def test_new_list_not_mutated(self):
        new = [_D]
        result, _ = merge_rows([_A], new)
        result.append(_C)  # mutate return value
        assert len(new) == 1

    def test_existing_list_not_mutated_on_add(self):
        existing = [_A]
        result, _ = merge_rows(existing, [_B])
        assert len(existing) == 1


# ─── Duplicate stock_id in new batch (Position 3) ────────────────────


class TestDuplicateInBatch:
    def test_duplicate_raises_erp_batch_invalid(self):
        with pytest.raises(ERPBatchInvalid):
            merge_rows([], [_A, _A_PRIME])

    def test_error_names_the_colliding_stock_id(self):
        with pytest.raises(ERPBatchInvalid, match="TEY1104"):
            merge_rows([], [_A, _A_PRIME])

    def test_duplicate_in_new_batch_with_nonempty_existing(self):
        # Duplicate in new batch is caught regardless of existing contents.
        with pytest.raises(ERPBatchInvalid):
            merge_rows([_A], [_A, _A_PRIME])

    def test_existing_unmodified_after_erp_batch_invalid(self):
        # ADR-0001 §Position 3: raise fires "before any modification."
        # Confirm the existing list contents are untouched after the exception.
        existing = [_A, _B]
        snapshot = existing[:]
        with pytest.raises(ERPBatchInvalid):
            merge_rows(existing, [_A, _A_PRIME])
        assert existing == snapshot


# ─── Corrupt existing (ADR-0001 §"Corrupt-existing posture") ─────────


class TestCorruptExisting:
    def test_last_occurrence_wins_in_corrupt_existing(self):
        """ADR-0001 §"Corrupt-existing posture": when existing has two rows
        with the same stock_id, _merge_rows_inner builds the index last-
        occurrence-wins (Python dict iteration overwrites earlier values).
        The merge updates the last-occurrence slot; the first-occurrence
        row is left untouched. Behavior is deterministic, not spec-correct.
        A corrupt ledger must be repaired before ingest, not during.
        """
        dup_first = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3100.0,  # stale/corrupt first entry
        )
        dup_last = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3200.0,  # second occurrence (index captures this slot)
        )
        new_row = LedgerRow(
            stock_id="TEY1104",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=2750.0,
            sell_price=3300.0,  # new truth — differs from both
        )
        result, counts = merge_rows([dup_first, dup_last], [new_row])
        # Index built last-occurrence-wins: existing_index["TEY1104"] = 1.
        # new_row differs from dup_last → update at slot 1.
        assert counts.updated == 1
        assert counts.added == 0
        assert result[1] == new_row      # last slot updated
        assert result[0] == dup_first    # first slot untouched (documented behavior)
        assert len(result) == 2          # corrupt shape preserved


# ─── Legacy collision (Position 2) ────────────────────────────────────


class TestLegacyCollision:
    def test_legacy_row_updated_by_new_truth(self):
        legacy = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2025, 1, 10),
            sell_cycle_id="cycle_2025-01",
            brand="Unknown",
            reference="UNKNOWN",
            account="NR",
            buy_price=0.0,
            sell_price=0.0,
        )
        full = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2025, 1, 10),
            sell_cycle_id="cycle_2025-01",
            brand="Rolex",
            reference="126300",
            account="NR",
            buy_price=7800.0,
            sell_price=8900.0,
        )
        result, counts = merge_rows([legacy], [full])
        assert counts == MergeCounts(added=0, updated=1, unchanged=0)
        assert result == [full]

    def test_legacy_not_preserved_when_new_diverges(self):
        legacy = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2025, 1, 10),
            sell_cycle_id="cycle_2025-01",
            brand="Unknown",
            reference="UNKNOWN",
            account="NR",
            buy_price=0.0,
            sell_price=0.0,
        )
        full = LedgerRow(
            stock_id="TEY9999",
            sell_date=date(2025, 1, 10),
            sell_cycle_id="cycle_2025-01",
            brand="Rolex",
            reference="126300",
            account="NR",
            buy_price=7800.0,
            sell_price=8900.0,
        )
        result, _ = merge_rows([legacy], [full])
        assert legacy not in result


# ─── Float equality ───────────────────────────────────────────────────


class TestFloatEquality:
    def test_identical_float_price_is_unchanged(self):
        row_existing = LedgerRow(
            stock_id="FLOAT001",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=1234.50,
            sell_price=1500.00,
        )
        row_new = LedgerRow(
            stock_id="FLOAT001",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=1234.50,
            sell_price=1500.00,
        )
        _, counts = merge_rows([row_existing], [row_new])
        assert counts == MergeCounts(added=0, updated=0, unchanged=1)

    def test_different_float_price_is_update(self):
        row_existing = LedgerRow(
            stock_id="FLOAT001",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=1234.50,
            sell_price=1500.00,
        )
        row_new = LedgerRow(
            stock_id="FLOAT001",
            sell_date=date(2026, 4, 25),
            sell_cycle_id="cycle_2026-08",
            brand="Tudor",
            reference="79830RB",
            account="NR",
            buy_price=1234.51,
            sell_price=1500.00,
        )
        _, counts = merge_rows([row_existing], [row_new])
        assert counts == MergeCounts(added=0, updated=1, unchanged=0)


# ─── OTEL span ────────────────────────────────────────────────────────


class TestOTELSpan:
    def test_merge_rows_works_under_no_op_tracer(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        result, counts = merge_rows([_A], [_B])
        assert counts == MergeCounts(added=1, updated=0, unchanged=0)
        assert _B in result

    def test_span_does_not_suppress_erp_batch_invalid(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        with pytest.raises(ERPBatchInvalid):
            merge_rows([], [_A, _A_PRIME])


class TestOTELSpanAttributes:
    def test_merge_rows_span_attributes_all_three_outcomes(self, span_exporter):
        """All five merge_rows span attributes land with correct values.

        Drives existing=[A,B,C], new=[A (unchanged), B' (update), D (add)]
        so all three outcome buckets are non-zero and each attribute is
        independently verifiable.
        """
        merge_rows([_A, _B, _C], [_A, _B_PRIME, _D])
        spans = span_exporter.get_finished_spans()
        span = next(
            (s for s in spans if s.name == "ingest_sales.merge_rows"), None
        )
        assert span is not None, "ingest_sales.merge_rows span not captured"
        attrs = span.attributes
        assert attrs["existing_count"] == 3
        assert attrs["new_count"] == 3
        assert attrs["added"] == 1
        assert attrs["updated"] == 1
        assert attrs["unchanged"] == 1

    def test_merge_rows_span_attributes_add_only(self, span_exporter):
        """Span attributes correct for a pure-add merge (no existing rows)."""
        merge_rows([], [_A, _B])
        spans = span_exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "ingest_sales.merge_rows")
        attrs = span.attributes
        assert attrs["existing_count"] == 0
        assert attrs["new_count"] == 2
        assert attrs["added"] == 2
        assert attrs["updated"] == 0
        assert attrs["unchanged"] == 0
